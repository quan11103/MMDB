"""
Nạp toàn bộ đặc trưng vào PostgreSQL (mô hình đối tượng-quan hệ + kiểu vector của pgvector).

Đầu vào: thư mục kết quả trích rút (features_seg) + metadata_final.csv (+ thư mục dataset nếu muốn
lưu cả nội dung transcript vào CSDL). File âm thanh KHÔNG được nạp vào CSDL: CSDL chỉ giữ đường dẫn.

  python load_db.py --features D:/BTL/features_seg --metadata D:/BTL/features_seg/metadata_final.csv \
                    --dataset D:/BTL/dataset --dsn postgresql://postgres:btl24@localhost:5432/btl --reset

  --reset        xóa các bảng cũ rồi tạo lại (nạp lại từ đầu)
  --print-schema chỉ in câu lệnh tạo bảng (để đưa vào báo cáo), không kết nối CSDL
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata

import numpy as np
import pandas as pd

TABLES = ["system_param", "feature_def", "item_entity", "named_entity", "item_keyword",
          "keyword_member", "keyword_group", "text_segment", "audio_segment", "item", "video"]


# ------------------------------------------------------------------
# Lược đồ
# ------------------------------------------------------------------
def schema_sql(dim_h: int, dim_e: int, dim_t: int) -> str:
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;

-- Video nguồn trên YouTube
CREATE TABLE video (
    video_id      TEXT PRIMARY KEY,
    video_title   TEXT,
    channel_id    TEXT,
    channel_name  TEXT
);

-- Dataset item = một chapter (một file âm thanh + transcript)
CREATE TABLE item (
    item_id          TEXT PRIMARY KEY,
    video_id         TEXT REFERENCES video(video_id),
    chapter_index    INTEGER,
    chapter_title    TEXT,
    start_time       REAL,                 -- mốc chapter trong video gốc (giây)
    end_time         REAL,
    duration_sec     REAL,                 -- thời lượng file chapter (giây)
    n_words          INTEGER,              -- số âm tiết của transcript
    n_audio_segments INTEGER,
    n_text_segments  INTEGER,
    audio_path       TEXT NOT NULL,        -- file âm thanh nằm ngoài CSDL
    transcript_path  TEXT NOT NULL,
    transcript       TEXT
);

-- Đoạn audio 40 âm tiết: thuộc tính giọng nói theo đoạn
CREATE TABLE audio_segment (
    item_id          TEXT REFERENCES item(item_id) ON DELETE CASCADE,
    seg_index        INTEGER,
    start_sec        REAL NOT NULL,
    end_sec          REAL NOT NULL,
    n_voiced_frames  INTEGER,
    h_raw            vector({dim_h}) NOT NULL,   -- đặc trưng âm học thủ công, giá trị thô
    h_norm           vector({dim_h}) NOT NULL,   -- đã chuẩn hóa min-max [0, 1]
    ecapa            vector({dim_e}) NOT NULL,   -- speaker embedding, đã chuẩn hóa L2
    PRIMARY KEY (item_id, seg_index)
);

-- Chunk văn bản 40 âm tiết: vector nhúng ngữ nghĩa theo đoạn
CREATE TABLE text_segment (
    item_id     TEXT REFERENCES item(item_id) ON DELETE CASCADE,
    seg_index   INTEGER,
    word_start  INTEGER NOT NULL,              -- vị trí âm tiết bắt đầu trong transcript
    embedding   vector({dim_t}) NOT NULL,      -- đã chuẩn hóa L2
    PRIMARY KEY (item_id, seg_index)
);

-- Từ điển từ khóa chung: mỗi nhóm đồng nghĩa/gần nghĩa có một từ đại diện
CREATE TABLE keyword_group (
    group_id   INTEGER PRIMARY KEY,
    keyword    TEXT NOT NULL,                  -- từ khóa đại diện
    df         INTEGER NOT NULL,
    idf        REAL NOT NULL,
    centroid   vector({dim_t}) NOT NULL
);

CREATE TABLE keyword_member (
    term      TEXT PRIMARY KEY,                -- biến thể (từ/cụm từ)
    group_id  INTEGER NOT NULL REFERENCES keyword_group(group_id),
    freq      INTEGER NOT NULL                 -- tần suất trên toàn CSDL
);

CREATE TABLE item_keyword (
    item_id   TEXT REFERENCES item(item_id) ON DELETE CASCADE,
    group_id  INTEGER REFERENCES keyword_group(group_id),
    tf        INTEGER NOT NULL,
    tfidf     REAL NOT NULL,
    PRIMARY KEY (item_id, group_id)
);

-- Thực thể có tên riêng
CREATE TABLE named_entity (
    entity_id  SERIAL PRIMARY KEY,
    text       TEXT NOT NULL,
    text_norm  TEXT NOT NULL,                  -- chữ thường, để gộp các cách viết
    label      TEXT NOT NULL CHECK (label IN ('PER', 'ORG', 'LOC')),
    UNIQUE (text_norm, label)
);

CREATE TABLE item_entity (
    item_id    TEXT REFERENCES item(item_id) ON DELETE CASCADE,
    entity_id  INTEGER REFERENCES named_entity(entity_id),
    count      INTEGER NOT NULL,
    PRIMARY KEY (item_id, entity_id)
);

-- Định nghĩa 126 đặc trưng thủ công + tham số min-max (dùng để chuẩn hóa file truy vấn)
CREATE TABLE feature_def (
    feature_index  INTEGER PRIMARY KEY,
    feature_name   TEXT NOT NULL UNIQUE,
    feature_group  TEXT NOT NULL,
    mean           DOUBLE PRECISION NOT NULL,   -- dùng để thay giá trị thiếu
    min_val        DOUBLE PRECISION NOT NULL,
    max_val        DOUBLE PRECISION NOT NULL
);

-- Tham số hệ thống: độ dài đoạn, thời lượng âm tiết, mô hình, ngưỡng từ khóa...
CREATE TABLE system_param (
    key    TEXT PRIMARY KEY,
    value  JSONB NOT NULL
);

CREATE INDEX ON item (video_id);
CREATE INDEX ON keyword_member (group_id);
CREATE INDEX ON item_keyword (group_id);
CREATE INDEX ON item_entity (entity_id);
"""


# ------------------------------------------------------------------
# Tiện ích
# ------------------------------------------------------------------
def vec(x) -> str:
    """Biểu diễn văn bản của kiểu vector: '[a,b,...]'."""
    return "[" + ",".join(f"{float(v):.7g}" for v in x) + "]"


def to_seconds(v):
    """'95.3' | '01:35' | '00:01:35' -> giây; rỗng -> None."""
    if v is None or str(v).strip() == "":
        return None
    s = str(v).strip()
    try:
        return float(s)
    except ValueError:
        parts = s.split(":")
        try:
            sec = 0.0
            for p in parts:
                sec = sec * 60 + float(p)
            return sec
        except ValueError:
            return None


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def nz(path):
    if not os.path.exists(path):
        sys.exit(f"Thiếu file: {path}")
    return np.load(path)


def read_transcript(path):
    with open(path, encoding="utf-8-sig") as f:
        return unicodedata.normalize("NFC", f.read()).strip()


def ensure_database(dsn):
    """Tạo database nếu chưa có (kết nối tạm vào database 'postgres')."""
    import psycopg
    try:
        psycopg.connect(dsn).close()
        return
    except psycopg.OperationalError as e:
        if "does not exist" not in str(e):
            raise
    m = re.match(r"^(.*/)([^/?]+)(\?.*)?$", dsn)
    if not m:
        raise
    admin = m.group(1) + "postgres" + (m.group(3) or "")
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{m.group(2)}"')
    print(f"Đã tạo database {m.group(2)}")


# ------------------------------------------------------------------
# Nạp dữ liệu
# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--features", required=False, help="thư mục kết quả trích rút (features_seg)")
    ap.add_argument("--metadata", required=False, help="metadata_final.csv")
    ap.add_argument("--dataset", default=None, help="thư mục dataset: nếu có thì lưu cả nội dung transcript")
    ap.add_argument("--dsn", default="postgresql://postgres:btl24@localhost:5432/btl")
    ap.add_argument("--reset", action="store_true", help="xóa bảng cũ và tạo lại")
    ap.add_argument("--print-schema", action="store_true")
    args = ap.parse_args()

    if args.print_schema:
        print(schema_sql(126, 192, 768))
        return
    if not (args.features and args.metadata):
        ap.error("cần --features và --metadata")
    F = args.features
    t0 = time.time()

    # ---------- đọc toàn bộ file kết quả ----------
    meta = pd.read_csv(args.metadata, dtype=str, keep_default_na=False)
    meta["item_id"] = meta["item_id"].str.strip()
    items = pd.read_csv(os.path.join(F, "items.csv"), dtype={"item_id": str}).set_index("item_id")
    raw = pd.read_csv(os.path.join(F, "handcrafted_segments_raw.csv"), dtype={"item_id": str})
    hz = nz(os.path.join(F, "handcrafted_segments_norm.npz"))
    ec = nz(os.path.join(F, "ecapa_segments.npz"))
    tx = nz(os.path.join(F, "text_segments.npz"))
    scaler = load_json(os.path.join(F, "handcrafted_scaler.json"))
    kdict = load_json(os.path.join(F, "keywords", "keyword_dictionary.json"))
    centroids = np.load(os.path.join(F, "keywords", "group_centroids.npy"))
    item_kw = load_json(os.path.join(F, "keywords", "item_keywords.json"))
    ner = load_json(os.path.join(F, "ner.json"))
    syl = load_json(os.path.join(F, "syllable_stats.json"))
    summary = load_json(os.path.join(F, "summary.json")) if os.path.exists(os.path.join(F, "summary.json")) else {}

    names = scaler["feature_names"]
    dim_h, dim_e, dim_t = len(names), ec["X"].shape[1], tx["X"].shape[1]
    ids = set(meta["item_id"])
    print(f"{len(meta)} item | H {dim_h} chiều, ECAPA {dim_e} chiều, văn bản {dim_t} chiều")

    # Ghép vector H (thô, min-max) và ECAPA theo khóa (item_id, seg_index)
    key = lambda a, b: (str(a), int(b))
    z_map = {key(i, s): x for i, s, x in zip(hz["item_id"], hz["seg_index"], hz["X"])}
    e_map = {key(i, s): x for i, s, x in zip(ec["item_id"], ec["seg_index"], ec["X"])}

    import psycopg
    ensure_database(args.dsn)
    with psycopg.connect(args.dsn) as conn:
        cur = conn.cursor()
        if args.reset:
            for t in TABLES:
                cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        cur.execute(schema_sql(dim_h, dim_e, dim_t))

        # ---------- video, item ----------
        videos = meta.drop_duplicates("video_id")
        cur.executemany("INSERT INTO video VALUES (%s,%s,%s,%s)",
                        [(r["video_id"], r.get("video_title") or None, r.get("channel_id") or None,
                          r.get("channel_name") or None) for _, r in videos.iterrows()])
        resolve = None
        if args.dataset:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
            from extract_all import PathResolver
            resolve = PathResolver(args.dataset)
        rows = []
        for _, r in meta.iterrows():
            iid = r["item_id"]
            it = items.loc[iid] if iid in items.index else {}
            transcript = read_transcript(resolve(r["transcript_path"])) if resolve else None
            rows.append((iid, r["video_id"], to_int(r.get("chapter_index")), r.get("chapter_title") or None,
                         to_seconds(r.get("start_time")), to_seconds(r.get("end_time")),
                         float(it["duration_sec"]) if len(it) else None,
                         to_int(it.get("n_words")) if len(it) else None,
                         to_int(it.get("n_audio_segments")) if len(it) else None,
                         to_int(it.get("n_text_segments")) if len(it) else None,
                         r["audio_path"], r["transcript_path"], transcript))
        cur.executemany("INSERT INTO item VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)

        # ---------- audio_segment (COPY cho nhanh) ----------
        n_audio = 0
        with cur.copy("COPY audio_segment (item_id, seg_index, start_sec, end_sec, n_voiced_frames, "
                      "h_raw, h_norm, ecapa) FROM STDIN") as cp:
            for r in raw.itertuples(index=False):
                k = key(r.item_id, r.seg_index)
                if r.item_id not in ids:
                    continue
                cp.write_row((r.item_id, int(r.seg_index), float(r.start_sec), float(r.end_sec),
                              int(r.n_voiced_frames), vec([getattr(r, n) for n in names]),
                              vec(z_map[k]), vec(e_map[k])))
                n_audio += 1

        # ---------- text_segment ----------
        n_text = 0
        with cur.copy("COPY text_segment (item_id, seg_index, word_start, embedding) FROM STDIN") as cp:
            for i, s, w, x in zip(tx["item_id"], tx["seg_index"], tx["word_start"], tx["X"]):
                if str(i) in ids:
                    cp.write_row((str(i), int(s), int(w), vec(x)))
                    n_text += 1

        # ---------- từ khóa ----------
        with cur.copy("COPY keyword_group (group_id, keyword, df, idf, centroid) FROM STDIN") as cp:
            for g in kdict["groups"]:
                cp.write_row((g["group_id"], g["keyword"], g["df"], g["idf"], vec(centroids[g["group_id"]])))
        cur.executemany("INSERT INTO keyword_member VALUES (%s,%s,%s)",
                        [(m["term"], g["group_id"], m["freq"]) for g in kdict["groups"] for m in g["members"]])
        cur.executemany("INSERT INTO item_keyword VALUES (%s,%s,%s,%s)",
                        [(iid, k["group_id"], k["tf"], k["tfidf"])
                         for iid, lst in item_kw.items() if iid in ids for k in lst])

        # ---------- thực thể ----------
        ent_id, ent_rows, link = {}, [], []
        for iid, lst in ner.items():
            if iid not in ids:
                continue
            for e in lst:
                k = (e["text"].lower(), e["label"])
                if k not in ent_id:
                    ent_id[k] = len(ent_id) + 1
                    ent_rows.append((ent_id[k], e["text"], k[0], e["label"]))
                link.append((iid, ent_id[k], e["count"]))
        cur.executemany("INSERT INTO named_entity (entity_id, text, text_norm, label) VALUES (%s,%s,%s,%s)", ent_rows)
        cur.execute("SELECT setval('named_entity_entity_id_seq', %s)", (max(len(ent_rows), 1),))
        # một thực thể có thể xuất hiện 2 lần trong cùng item nếu khác cách viết hoa/thường -> cộng dồn
        agg = {}
        for iid, eid, c in link:
            agg[(iid, eid)] = agg.get((iid, eid), 0) + c
        cur.executemany("INSERT INTO item_entity VALUES (%s,%s,%s)", [(i, e, c) for (i, e), c in agg.items()])

        # ---------- định nghĩa đặc trưng, tham số hệ thống ----------
        group_of = {}
        for gname, (a, b) in scaler["groups"].items():
            for j in range(a, b):
                group_of[j] = gname
        cur.executemany("INSERT INTO feature_def VALUES (%s,%s,%s,%s,%s,%s)",
                        [(j, n, group_of.get(j, ""), float(scaler["mean"][j]),
                          float(scaler["min"][j]), float(scaler["max"][j]))
                         for j, n in enumerate(names)])
        cfg = summary.get("config", {})
        params = {
            "syllable": syl,
            "segment_sec": syl["segment_sec"],
            "segment_syllables": syl["segment_syllables"],
            "keyword": {"threshold": kdict["threshold"], "linkage": kdict["linkage"], "model": kdict["model"]},
            "models": {"ecapa": cfg.get("ECAPA_SOURCE"), "sentence_transformer": cfg.get("ST_MODEL")},
            "extraction_config": cfg,
        }
        cur.executemany("INSERT INTO system_param VALUES (%s,%s)",
                        [(k, json.dumps(v, ensure_ascii=False)) for k, v in params.items()])
        conn.commit()

        # ---------- kiểm tra sau khi nạp ----------
        print(f"\nNạp xong trong {time.time() - t0:.1f} s. Số bản ghi:")
        for t in reversed(TABLES):
            cur.execute(f"SELECT count(*) FROM {t}")
            print(f"  {t:<15} {cur.fetchone()[0]:>8}")
        cur.execute("""SELECT vector_dims(h_norm), vector_dims(ecapa) FROM audio_segment LIMIT 1""")
        print("  số chiều h_norm, ecapa:", cur.fetchone())
        cur.execute("""SELECT count(*) FROM item i WHERE n_audio_segments IS DISTINCT FROM
                       (SELECT count(*) FROM audio_segment a WHERE a.item_id = i.item_id)""")
        print("  item có số đoạn audio không khớp items.csv:", cur.fetchone()[0])
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        print("  dung lượng database:", cur.fetchone()[0])


if __name__ == "__main__":
    main()
