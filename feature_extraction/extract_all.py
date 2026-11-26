"""
Trích rút toàn bộ đặc trưng cho các dataset item trong metadata.csv.

Các bước (chọn bằng --steps, mặc định chạy tất cả):
  syllable    : đo thời lượng TB 1 âm tiết trên dataset -> độ dài đoạn (syllable_stats.json)
  handcrafted : vector H 126 chiều cho TỪNG ĐOẠN audio (librosa + parselmouth)
  ecapa       : speaker embedding ECAPA-TDNN cho TỪNG ĐOẠN audio
  text        : vector nhúng ngữ nghĩa cho TỪNG CHUNK văn bản + NER + ứng viên từ khóa (mức file)
  keywords    : xây từ điển từ khóa chung toàn dataset + TF-IDF từng file
  aggregate   : gộp kết quả, chuẩn hóa min-max [-1, 1] vector H (fit trên mọi đoạn), ghi summary.json

Kết quả từng file được lưu trong <out>/cache/<bước>/<item_id>.* nên có thể dừng và chạy tiếp;
file đã có kết quả sẽ được bỏ qua (dùng --force để tính lại).

Ví dụ:
  python extract_all.py --metadata D:/dataset/metadata.csv --out features
  python extract_all.py --metadata metadata.csv --out features --steps handcrafted --limit 5
"""
import argparse
import csv
import json
import os
import time
import traceback
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
from tqdm import tqdm

import config

STEPS = ("syllable", "handcrafted", "ecapa", "text", "keywords", "aggregate")
CACHE = {"handcrafted": "handcrafted_seg", "ecapa": "ecapa_seg", "text_seg": "text_seg", "text": "text"}


# ------------------------------------------------------------------
# Tiện ích
# ------------------------------------------------------------------
def _json_default(o):
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=_json_default)
    os.replace(tmp, path)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Logger:
    def __init__(self, path):
        self.path = path
        new = not os.path.exists(path)
        self.f = open(path, "a", encoding="utf-8", newline="")
        self.w = csv.writer(self.f)
        self.errors = 0
        if new:
            self.w.writerow(["timestamp", "item_id", "step", "status", "seconds", "message"])

    def log(self, item_id, step, status, seconds=0.0, message=""):
        self.errors += status == "error"
        self.w.writerow([datetime.now().isoformat(timespec="seconds"), item_id, step, status,
                         f"{seconds:.3f}", message.replace("\n", " | ")[:500]])
        self.f.flush()


def _key(path):
    """Khóa so khớp đường dẫn: NFKC (gộp NFC/NFD, ký tự toàn độ rộng như '｜' -> '|'),
    dấu '/' thống nhất, không phân biệt hoa thường, gộp khoảng trắng."""
    p = unicodedata.normalize("NFKC", str(path)).replace("\\", "/").casefold()
    return "/".join(" ".join(part.split()) for part in p.split("/") if part)


class PathResolver:
    """Tìm file thật trên đĩa cho đường dẫn trong metadata, kể cả khi tên file/thư mục
    khác dạng Unicode (NFC/NFD) hoặc bị yt-dlp thay ký tự (| -> ｜, ? -> ？...)."""

    def __init__(self, root):
        self.root = root
        self.index = None

    def _build(self):
        self.index = {}
        for dirpath, _, files in os.walk(self.root):
            for f in files:
                full = os.path.join(dirpath, f)
                self.index.setdefault(_key(os.path.relpath(full, self.root)), full)

    def __call__(self, path):
        path = str(path)
        full = path if os.path.isabs(path) else os.path.join(self.root, path)
        if os.path.exists(full):
            return full
        for form in ("NFC", "NFD"):
            alt = unicodedata.normalize(form, full)
            if os.path.exists(alt):
                return alt
        if self.index is None:
            self._build()
        rel = os.path.relpath(full, self.root) if os.path.isabs(path) else path
        found = self.index.get(_key(rel))
        if found is None:
            raise FileNotFoundError(f"Không tìm thấy file: {full}")
        return found


def pick_device(arg):
    if arg != "auto":
        return arg
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


# ------------------------------------------------------------------
# Bước 'syllable': độ dài đoạn
# ------------------------------------------------------------------
def run_syllable(df, resolve, out, logger):
    import content_text
    import segmenting
    t0 = time.time()
    durs, words = [], []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Đo âm tiết"):
        durs.append(segmenting.audio_duration(resolve(row["audio_path"])))
        words.append(len(content_text.read_transcript(resolve(row["transcript_path"])).split()))
    st = segmenting.syllable_stats(durs, words)
    save_json(os.path.join(out, segmenting.STATS_FILE), st)
    msg = (f"1 âm tiết = {st['syllable_sec']:.3f} s; đoạn = {st['segment_syllables']} âm tiết "
           f"= {st['segment_sec']:.2f} s")
    logger.log("*", "syllable", "ok", time.time() - t0, msg)
    print(msg)


# ------------------------------------------------------------------
# Các bước theo từng file
# ------------------------------------------------------------------
def _same_segment(npz_path, seg_sec):
    """Kết quả đã lưu có cùng độ dài đoạn với cấu hình hiện tại không (cache cũ không có -> khác)."""
    try:
        z = np.load(npz_path)
        return "segment_sec" in z and abs(float(z["segment_sec"]) - seg_sec) < 1e-6
    except Exception:
        return False


def run_per_item(df, resolve, out, steps, force, device, logger):
    import segmenting
    cache = {k: os.path.join(out, "cache", v) for k, v in CACHE.items()}
    for d in cache.values():
        os.makedirs(d, exist_ok=True)
    seg_sec = segmenting.load_segment_sec(out)
    print(f"Độ dài đoạn audio = {seg_sec:.2f} s ({config.SEGMENT_SYLLABLES} âm tiết); "
          f"chunk văn bản = {config.SEGMENT_SYLLABLES} từ")

    encoder, stopwords = None, None
    if "text" in steps:
        import content_text
        encoder = content_text.Encoder(device)
        stopwords = content_text.load_stopwords()
        print(f"Sentence Transformer: {config.ST_MODEL}, số chiều = {encoder.dim}")

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Trích rút"):
        iid = row["item_id"]
        y, bounds = None, None

        def audio():
            nonlocal y, bounds
            if y is None:
                import audio_io
                y = audio_io.load_audio(resolve(row["audio_path"]))
                bounds = segmenting.audio_bounds(len(y), seg_sec)
            return y, bounds

        # --- handcrafted: vector H từng đoạn ---
        p = os.path.join(cache["handcrafted"], f"{iid}.npz")
        stale = os.path.exists(p) and not _same_segment(p, seg_sec)
        if "handcrafted" in steps and (force or stale or not os.path.exists(p)):
            t0 = time.time()
            try:
                import voice_handcrafted as vh
                sig, bd = audio()
                X, voiced = vh.extract_segments(sig, bd)
                sr = config.SAMPLE_RATE
                np.savez(p, X=X, voiced=voiced, start=np.array([a / sr for a, _ in bd]),
                         end=np.array([b / sr for _, b in bd]), duration=len(sig) / sr, segment_sec=seg_sec)
                n_nan = int((~np.isfinite(X)).sum())
                logger.log(iid, "handcrafted", "ok", time.time() - t0,
                           f"{len(bd)} đoạn" + (f"; {n_nan} giá trị NaN" if n_nan else ""))
            except Exception as e:
                logger.log(iid, "handcrafted", "error", time.time() - t0, f"{e!r} {traceback.format_exc(limit=2)}")

        # --- ecapa: embedding từng đoạn ---
        p = os.path.join(cache["ecapa"], f"{iid}.npy")
        p_seg = os.path.join(cache["ecapa"], f"{iid}.segment_sec")
        stale = os.path.exists(p) and not (os.path.exists(p_seg) and
                                           abs(float(open(p_seg).read()) - seg_sec) < 1e-6)
        if "ecapa" in steps and (force or stale or not os.path.exists(p)):
            t0 = time.time()
            try:
                import voice_ecapa
                sig, bd = audio()
                np.save(p, voice_ecapa.extract_segments(sig, bd, device))
                with open(p_seg, "w") as f:
                    f.write(repr(seg_sec))
                logger.log(iid, "ecapa", "ok", time.time() - t0, f"{len(bd)} đoạn")
            except Exception as e:
                logger.log(iid, "ecapa", "error", time.time() - t0, f"{e!r} {traceback.format_exc(limit=2)}")

        # --- text: vector từng chunk + NER + ứng viên từ khóa ---
        p_seg = os.path.join(cache["text_seg"], f"{iid}.npz")
        p_txt = os.path.join(cache["text"], f"{iid}.json")
        need_seg = force or not os.path.exists(p_seg)
        need_txt = force or not os.path.exists(p_txt)
        if "text" in steps and (need_seg or need_txt):
            t0 = time.time()
            try:
                import content_text
                text = content_text.read_transcript(resolve(row["transcript_path"]))
                if need_seg:
                    E, starts = content_text.segment_embeddings(text, encoder)
                    np.savez(p_seg, X=E, word_start=starts)
                if need_txt:                                   # NER, ứng viên: mức file
                    save_json(p_txt, {
                        "n_words": len(text.split()),
                        "ner": content_text.extract_ner(text),
                        "candidates": content_text.extract_candidates(text, stopwords),
                    })
                logger.log(iid, "text", "ok", time.time() - t0)
            except Exception as e:
                logger.log(iid, "text", "error", time.time() - t0, f"{e!r} {traceback.format_exc(limit=2)}")
    if logger.errors:
        print(f"\n!! {logger.errors} lỗi trong lần chạy này — xem {logger.path} (cột message)")


# ------------------------------------------------------------------
# Bước toàn dataset
# ------------------------------------------------------------------
def run_keywords(df, out, device, threshold, logger):
    import content_text
    import keywords as kw
    tdir = os.path.join(out, "cache", "text")
    item_cand = {}
    for iid in df["item_id"]:
        p = os.path.join(tdir, f"{iid}.json")
        if os.path.exists(p):
            item_cand[iid] = load_json(p)["candidates"]
    if not item_cand:
        raise RuntimeError("Chưa có item nào hoàn thành bước 'text' — xem lỗi trong extraction_log.csv")
    t0 = time.time()
    encoder = content_text.Encoder(device)
    d = kw.build_dictionary(item_cand, encoder, threshold)
    kdir = os.path.join(out, "keywords")
    os.makedirs(kdir, exist_ok=True)
    np.save(os.path.join(kdir, "group_centroids.npy"), d.pop("centroids"))
    save_json(os.path.join(kdir, "keyword_dictionary.json"), d)
    save_json(os.path.join(kdir, "item_keywords.json"),
              {iid: kw.item_keywords(c, d) for iid, c in item_cand.items()})
    multi = sum(1 for g in d["groups"] if len(g["members"]) > 1)
    msg = (f"{d['n_terms']} ứng viên -> {len(d['groups'])} nhóm ({multi} nhóm >1 thành viên), "
           f"bỏ {d['n_terms_dropped']} ứng viên do giới hạn")
    logger.log("*", "keywords", "ok", time.time() - t0, msg)
    print(msg)


def run_aggregate(df, out):
    import segmenting
    import voice_handcrafted as vh
    cache = {k: os.path.join(out, "cache", v) for k, v in CACHE.items()}
    names = vh.feature_names()
    summary = {"n_items_metadata": int(len(df)), "config": {
        k: getattr(config, k) for k in dir(config) if k.isupper()}}
    sp = os.path.join(out, segmenting.STATS_FILE)
    if os.path.exists(sp):
        summary["syllable"] = load_json(sp)
    items = {iid: {"item_id": iid} for iid in df["item_id"]}

    # --- kiểm tra: mọi kết quả audio phải cùng độ dài đoạn với cấu hình hiện tại ---
    seg_sec = segmenting.load_segment_sec(out)
    bad = [iid for iid in df["item_id"]
           if os.path.exists(os.path.join(cache["handcrafted"], f"{iid}.npz"))
           and not _same_segment(os.path.join(cache["handcrafted"], f"{iid}.npz"), seg_sec)]
    bad += [iid for iid in df["item_id"]
            if os.path.exists(os.path.join(cache["ecapa"], f"{iid}.npy"))
            and not (os.path.exists(os.path.join(cache["ecapa"], f"{iid}.segment_sec")) and
                     abs(float(open(os.path.join(cache["ecapa"], f"{iid}.segment_sec")).read()) - seg_sec) < 1e-6)]
    if bad:
        raise SystemExit(f"!! {len(set(bad))} item có kết quả audio tính với độ dài đoạn khác {seg_sec} s "
                         f"(ví dụ {sorted(set(bad))[:5]}): chạy lại bước handcrafted, ecapa")

    # --- vector H theo đoạn: thô + min-max [-1, 1] (fit trên mọi đoạn của CSDL) ---
    raw_rows, seg_ids, seg_idx = [], [], []
    for iid in df["item_id"]:
        p = os.path.join(cache["handcrafted"], f"{iid}.npz")
        if not os.path.exists(p):
            continue
        z = np.load(p)
        items[iid].update(duration_sec=float(z["duration"]), n_audio_segments=int(len(z["X"])))
        for k in range(len(z["X"])):
            raw_rows.append([iid, k, float(z["start"][k]), float(z["end"][k]), int(z["voiced"][k])]
                            + list(z["X"][k]))
            seg_ids.append(iid)
            seg_idx.append(k)
    if raw_rows:
        raw = pd.DataFrame(raw_rows, columns=["item_id", "seg_index", "start_sec", "end_sec",
                                              "n_voiced_frames"] + names)
        raw.to_csv(os.path.join(out, "handcrafted_segments_raw.csv"), index=False, encoding="utf-8")
        X = np.array(raw[names].to_numpy(dtype=np.float64), copy=True)
        X[~np.isfinite(X)] = np.nan
        nan_count = int(np.isnan(X).sum())
        mean = np.nanmean(X, axis=0)
        vmin = np.nanmin(X, axis=0)
        vmax = np.nanmax(X, axis=0)
        rng = vmax - vmin
        rng[rng == 0] = 1.0                                # đặc trưng hằng số -> tránh chia 0
        X = np.where(np.isnan(X), mean, X)                 # NaN -> trung bình cột
        Xn = 2 * (X - vmin) / rng - 1                      # min-max về [-1, 1]
        np.savez(os.path.join(out, "handcrafted_segments_norm.npz"), item_id=np.array(seg_ids),
                 seg_index=np.array(seg_idx), X=Xn.astype(np.float32))
        save_json(os.path.join(out, "handcrafted_scaler.json"),
                  {"feature_names": names, "method": "min-max [-1, 1]", "mean": mean, "min": vmin,
                   "max": vmax, "groups": vh.FEATURE_GROUPS, "fitted_on": "mọi đoạn audio của CSDL"})
        summary["handcrafted"] = {"n_items": len(set(seg_ids)), "n_segments": len(seg_ids),
                                  "dim": len(names), "nan_values_imputed": nan_count}

    # --- ECAPA theo đoạn ---
    ids_, idx_, vecs = [], [], []
    for iid in df["item_id"]:
        p = os.path.join(cache["ecapa"], f"{iid}.npy")
        if os.path.exists(p):
            E = np.load(p)
            ids_ += [iid] * len(E)
            idx_ += list(range(len(E)))
            vecs.append(E)
    if vecs:
        np.savez(os.path.join(out, "ecapa_segments.npz"), item_id=np.array(ids_),
                 seg_index=np.array(idx_), X=np.vstack(vecs))
        summary["ecapa"] = {"n_items": len(vecs), "n_segments": len(ids_), "dim": int(vecs[0].shape[1])}

    # --- vector ngữ nghĩa theo chunk ---
    ids_, idx_, starts, vecs = [], [], [], []
    for iid in df["item_id"]:
        p = os.path.join(cache["text_seg"], f"{iid}.npz")
        if os.path.exists(p):
            z = np.load(p)
            ids_ += [iid] * len(z["X"])
            idx_ += list(range(len(z["X"])))
            starts += list(z["word_start"])
            vecs.append(z["X"])
            items[iid]["n_text_segments"] = int(len(z["X"]))
    if vecs:
        np.savez(os.path.join(out, "text_segments.npz"), item_id=np.array(ids_), seg_index=np.array(idx_),
                 word_start=np.array(starts), X=np.vstack(vecs))
        summary["text_embedding"] = {"n_items": len(vecs), "n_segments": len(ids_),
                                     "dim": int(vecs[0].shape[1])}

    # --- NER ---
    ner, nw = {}, []
    for iid in df["item_id"]:
        p = os.path.join(cache["text"], f"{iid}.json")
        if os.path.exists(p):
            t = load_json(p)
            ner[iid] = t["ner"]
            nw.append(t["n_words"])
            items[iid]["n_words"] = t["n_words"]
    if ner:
        save_json(os.path.join(out, "ner.json"), ner)
        summary["ner"] = {"n_items": len(ner),
                          "n_entities_total": sum(len(v) for v in ner.values())}
        summary["transcript_words"] = {"mean": float(np.mean(nw)), "min": int(min(nw)), "max": int(max(nw))}

    # --- bảng item: thời lượng, số từ, số đoạn ---
    it = pd.DataFrame(list(items.values()))
    it.to_csv(os.path.join(out, "items.csv"), index=False, encoding="utf-8")
    for col in ("n_audio_segments", "n_text_segments"):
        if col in it:
            summary[col] = {"mean": float(it[col].mean()), "min": int(it[col].min()), "max": int(it[col].max())}

    kd = os.path.join(out, "keywords", "keyword_dictionary.json")
    if os.path.exists(kd):
        d = load_json(kd)
        summary["keywords"] = {k: d[k] for k in ("threshold", "linkage", "n_terms", "n_terms_dropped")}
        summary["keywords"]["n_groups"] = len(d["groups"])

    # --- thống kê thời gian/lỗi từ log ---
    log_path = os.path.join(out, "extraction_log.csv")
    if os.path.exists(log_path):
        lg = pd.read_csv(log_path)
        lg["item_id"] = lg["item_id"].astype(str)
        lg = lg[lg.item_id.isin(set(df["item_id"]) | {"*"})]
        lg = lg.sort_values("timestamp").drop_duplicates(["item_id", "step"], keep="last")
        summary["log"] = {
            s: {"ok": int((g.status == "ok").sum()), "error": int((g.status == "error").sum()),
                "mean_seconds": float(g.loc[g.status == "ok", "seconds"].mean() or 0),
                "total_seconds": float(g.loc[g.status == "ok", "seconds"].sum())}
            for s, g in lg.groupby("step")}

    save_json(os.path.join(out, "summary.json"), summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "config"}, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata", required=True, help="đường dẫn metadata.csv")
    ap.add_argument("--root", default=None, help="thư mục gốc cho audio_path/transcript_path tương đối "
                                                 "(mặc định: thư mục chứa metadata.csv)")
    ap.add_argument("--out", default="features", help="thư mục kết quả")
    ap.add_argument("--steps", default=",".join(STEPS), help=f"các bước, phân tách bằng dấu phẩy: {STEPS}")
    ap.add_argument("--limit", type=int, default=None, help="chỉ chạy N item đầu (chạy thử)")
    ap.add_argument("--ids", default=None, help="chỉ chạy các item_id này, phân tách bằng dấu phẩy")
    ap.add_argument("--force", action="store_true", help="tính lại cả item đã có kết quả")
    ap.add_argument("--device", default="auto", help="auto | cpu | cuda")
    ap.add_argument("--keyword-threshold", type=float, default=None,
                    help=f"ngưỡng cosine gom nhóm từ khóa (mặc định {config.KEYWORD_SIM_THRESHOLD})")
    ap.add_argument("--keyword-linkage", default=None, choices=["average", "complete"],
                    help=f"cách liên kết khi gom nhóm từ khóa (mặc định {config.KEYWORD_LINKAGE})")
    args = ap.parse_args()
    if args.keyword_linkage:
        config.KEYWORD_LINKAGE = args.keyword_linkage

    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    bad = [s for s in steps if s not in STEPS]
    if bad:
        ap.error(f"bước không hợp lệ: {bad}")

    df = pd.read_csv(args.metadata, dtype=str, keep_default_na=False)
    df["item_id"] = df["item_id"].str.strip()
    df_full = df                       # bước 'syllable' luôn đo trên toàn bộ metadata
    if args.ids:
        df = df[df["item_id"].isin(args.ids.split(","))]
    if args.limit:
        df = df.head(args.limit)
    root = args.root or os.path.dirname(os.path.abspath(args.metadata))
    os.makedirs(args.out, exist_ok=True)
    device = pick_device(args.device)
    logger = Logger(os.path.join(args.out, "extraction_log.csv"))
    print(f"{len(df)} item | thiết bị: {device} | bước: {steps}")

    resolve = PathResolver(root)
    per_item = [s for s in steps if s in ("handcrafted", "ecapa", "text")]
    if per_item or "syllable" in steps:
        # Kiểm tra trước: mọi file trong metadata phải tìm thấy trên đĩa
        missing = []
        for _, row in df.iterrows():
            for col in ("audio_path", "transcript_path"):
                try:
                    resolve(row[col])
                except FileNotFoundError:
                    missing.append(row[col])
        if missing:
            print(f"!! Không tìm thấy {len(missing)} file (root = {root}). Ví dụ:")
            for p in missing[:5]:
                print("   ", p)
            raise SystemExit("Dừng: kiểm tra lại --root và đường dẫn trong metadata.csv")
    if "syllable" in steps:
        run_syllable(df_full, resolve, args.out, logger)
    if per_item:
        run_per_item(df, resolve, args.out, per_item, args.force, device, logger)
    if "keywords" in steps:
        run_keywords(df, args.out, device, args.keyword_threshold, logger)
    if "aggregate" in steps:
        run_aggregate(df, args.out)


if __name__ == "__main__":
    main()
