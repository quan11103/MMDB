"""
Đánh giá hệ thống tìm kiếm trên bộ file truy vấn và chọn trọng số α, β bằng thực nghiệm (mục 4c).

queries.csv (UTF-8), mỗi dòng một file truy vấn:
  query_id        mã truy vấn (q01, q02 ...)
  audio_path      đường dẫn file âm thanh truy vấn
  transcript_path (tùy chọn) transcript có sẵn; bỏ trống -> dùng Whisper
  type            A = giọng đã có, nội dung đã có   (chapter ngoài CSDL của một video có chapter trong CSDL)
                  B = giọng đã có, nội dung chưa có (video mới cùng kênh)
                  C = giọng chưa có, nội dung đã có (thành viên thu âm lại nội dung một file trong CSDL)
  video_id        A: video gốc của chapter; C: video của file được thu âm lại; B: để trống
  channel_id      B: bắt buộc (kênh của video mới); A: tự lấy theo video_id nếu để trống; C: để trống
  source_item_id  C (tùy chọn): item_id của file trong CSDL được thu âm lại
  topic           (tùy chọn) chủ đề, dùng cho đánh giá nội dung "theo chủ đề" nếu có --topics

Đáp án đúng:
  Giọng nói (A, B): file trong CSDL cùng kênh (cùng người nói) với truy vấn.
  Nội dung  (A, C): file trong CSDL cùng video với truy vấn (chặt);
                    cùng chủ đề (lỏng, nếu có --topics: video_id,topic cho các video trong CSDL).
  Với phần "chưa có" (giọng của C, nội dung của B) không có đáp án đúng: báo cáo điểm top-1 để so sánh.
  α được chọn trên A, B (giọng nói); β được chọn trên A, C (nội dung).

  python evaluate.py --queries queries.csv --dsn postgresql://postgres:btl24@localhost:5434/btl --out danh_gia
"""
import argparse
import os
import pickle

import numpy as np
import pandas as pd

from search_engine import SearchEngine

GRID = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def metrics(flags):
    """flags: danh sách đúng/sai theo thứ tự xếp hạng (toàn bộ danh sách)."""
    top3 = flags[:3]
    first = next((i + 1 for i, f in enumerate(flags) if f), None)
    return {"P@3": sum(top3) / 3, "Hit@3": float(any(top3)), "MRR": 1 / first if first else 0.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--dsn", default="postgresql://postgres:btl24@localhost:5432/btl")
    ap.add_argument("--topics", default=None, help="CSV video_id,topic của các video trong CSDL (tùy chọn)")
    ap.add_argument("--out", default="danh_gia")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--alpha", type=float, default=None,
                    help="cố định α khi xuất details.csv (mặc định: α tốt nhất theo P@3)")
    ap.add_argument("--beta", type=float, default=None,
                    help="cố định β khi xuất details.csv (mặc định: β tốt nhất theo P@3)")
    args = ap.parse_args()
    os.makedirs(os.path.join(args.out, "cache"), exist_ok=True)

    Q = pd.read_csv(args.queries, dtype=str, keep_default_na=False)
    Q["type"] = Q["type"].str.strip().str.upper()
    eng = SearchEngine(args.dsn, args.device)
    items = eng.items
    topic = {}
    if args.topics:
        tp = pd.read_csv(args.topics, dtype=str, keep_default_na=False)
        topic = dict(zip(tp["video_id"], tp["topic"]))
    ch_of_video = {it["video_id"]: it["channel_id"] for it in items.values()}

    # ---------- đặc trưng + thành phần độ tương đồng của mỗi truy vấn (lưu cache) ----------
    data = []
    for _, row in Q.iterrows():
        cp = os.path.join(args.out, "cache", f"{row['query_id']}.pkl")
        if os.path.exists(cp):
            with open(cp, "rb") as f:
                q = pickle.load(f)
        else:
            tr = None
            if row.get("transcript_path"):
                with open(row["transcript_path"], encoding="utf-8-sig") as f:
                    tr = f.read()
            print(f"Trích rút {row['query_id']} ({row['type']}) ...")
            q = eng.analyze(row["audio_path"], tr)
            with open(cp, "wb") as f:
                pickle.dump(q, f)
        ch = row.get("channel_id") or (ch_of_video.get(row.get("video_id")) if row["type"] == "A" else "")
        data.append({"row": row, "q": q, "comp": eng.components(q), "channel": ch})

    def rel_speaker(d, iid):
        return bool(d["channel"]) and items[iid]["channel_id"] == d["channel"]

    def rel_strict(d, iid):
        return items[iid]["video_id"] == d["row"]["video_id"] or iid == d["row"].get("source_item_id")

    def rel_loose(d, iid):
        t = d["row"].get("topic") or topic.get(d["row"]["video_id"], "")
        return bool(t) and topic.get(items[iid]["video_id"]) == t

    # ---------- lưới α (giọng nói) ----------
    rows_s = []
    for a in GRID:
        for d in data:
            lst = eng.rank(d["q"], d["comp"], alpha=a)["speaker"]
            r = {"alpha": a, "query_id": d["row"]["query_id"], "type": d["row"]["type"],
                 "top1_score": lst[0]["score"]}
            if d["row"]["type"] in ("A", "B"):
                r.update(metrics([rel_speaker(d, x["item_id"]) for x in lst]))
            rows_s.append(r)
    S = pd.DataFrame(rows_s)

    # ---------- lưới β (nội dung) ----------
    rows_c = []
    for b in GRID:
        for d in data:
            lst = eng.rank(d["q"], d["comp"], beta=b)["content"]
            r = {"beta": b, "query_id": d["row"]["query_id"], "type": d["row"]["type"],
                 "top1_score": lst[0]["score"]}
            if d["row"]["type"] in ("A", "C"):
                r.update({f"strict_{k}": v for k, v in metrics([rel_strict(d, x["item_id"]) for x in lst]).items()})
                if topic:
                    r.update({f"loose_{k}": v for k, v in metrics([rel_loose(d, x["item_id"]) for x in lst]).items()})
            rows_c.append(r)
    C = pd.DataFrame(rows_c)

    gs = S.groupby(["alpha", "type"]).mean(numeric_only=True).round(4)
    gc = C.groupby(["beta", "type"]).mean(numeric_only=True).round(4)
    gs.to_csv(os.path.join(args.out, "grid_speaker.csv"), encoding="utf-8-sig")
    gc.to_csv(os.path.join(args.out, "grid_content.csv"), encoding="utf-8-sig")

    known_s = S[S.type.isin(["A", "B"])].groupby("alpha")["P@3"].mean()
    key_c = "loose_P@3" if topic else "strict_P@3"
    known_c = C[C.type.isin(["A", "C"])].groupby("beta")[key_c].mean()
    best_a = float(known_s.idxmax()) if len(known_s) else 0.5
    best_b = float(known_c.idxmax()) if len(known_c) else 0.7
    use_a = best_a if args.alpha is None else args.alpha
    use_b = best_b if args.beta is None else args.beta

    # ---------- chi tiết từng truy vấn với α, β tốt nhất ----------
    det = []
    for d in data:
        r = eng.rank(d["q"], d["comp"], alpha=use_a, beta=use_b)
        row = {"query_id": d["row"]["query_id"], "type": d["row"]["type"],
               "duration_sec": round(d["q"]["duration_sec"], 1), "n_segments": len(d["q"]["segments"]),
               "transcript_source": d["q"]["transcript_source"]}
        for kind, rel in (("content", rel_strict), ("speaker", rel_speaker)):
            for i, x in enumerate(r[kind][:3], 1):
                row[f"{kind}{i}"] = x["item_id"]
                row[f"{kind}{i}_score"] = round(x["score"], 4)
                row[f"{kind}{i}_ok"] = (rel(d, x["item_id"]) if (kind == "content" and d["row"]["type"] in "AC")
                                        or (kind == "speaker" and d["row"]["type"] in "AB") else "")
        det.append(row)
    DET = pd.DataFrame(det)
    DET.to_csv(os.path.join(args.out, "details.csv"), index=False, encoding="utf-8-sig")

    # ---------- tóm tắt ----------
    # tách được từng truy vấn giọng đã có / chưa có không (tại α dùng cho details.csv)
    top1 = {d["row"]["query_id"]: eng.rank(d["q"], d["comp"], alpha=use_a)["speaker"][0]["score"] for d in data}
    known = [top1[d["row"]["query_id"]] for d in data if d["row"]["type"] in ("A", "B")]
    unknown = [top1[d["row"]["query_id"]] for d in data if d["row"]["type"] == "C"]
    pd.set_option("display.width", 160)
    print(f"\n{len(data)} truy vấn: " + ", ".join(f"{t}={n}" for t, n in Q["type"].value_counts().sort_index().items()))
    print("\n=== Giọng nói theo α (P@3 TB của A, B):")
    print(known_s.round(4).to_string())
    print(f"-> α tốt nhất theo P@3 = {best_a}; α dùng cho details.csv = {use_a}")
    if use_a in GRID:
        print(gs.xs(use_a, level="alpha").to_string())
    print(f"\n=== Nội dung theo β ({key_c} TB của A, C):")
    print(known_c.round(4).to_string())
    print(f"-> β tốt nhất theo P@3 = {best_b}; β dùng cho details.csv = {use_b}")
    if use_b in GRID:
        print(gc.xs(use_b, level="beta").to_string())
    if known and unknown:
        print(f"\nGiọng nói tại α = {use_a}: top-1 thấp nhất của A, B = {min(known):.4f}; "
              f"top-1 cao nhất của C = {max(unknown):.4f} -> "
              + ("tách được toàn bộ truy vấn" if min(known) > max(unknown) else "CÓ truy vấn bị chồng lấn"))
    print(f"\nĐã lưu grid_speaker.csv, grid_content.csv, details.csv vào {args.out}")
    print("Lưu ý: α, β được chọn trên chính bộ truy vấn này nên kết quả tại α, β tốt nhất là ước lượng lạc quan.")


if __name__ == "__main__":
    main()
