"""
Chọn ngưỡng gom nhóm từ khóa bằng thực nghiệm.

Đọc ứng viên đã trích ở bước 'text', embedding một lần, dựng cây phân cụm một lần,
rồi cắt cây ở nhiều ngưỡng. Với mỗi ngưỡng ghi ra số nhóm và các nhóm nhiều thành viên nhất
để nhóm kiểm tra thủ công (gộp đúng đồng nghĩa/gần nghĩa hay gộp nhầm).

  python tune_keywords.py --out features --thresholds 0.75,0.80,0.85,0.90
"""
import argparse
import os

import numpy as np

import config
import content_text
import keywords as kw
from extract_all import load_json, pick_device


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="features")
    ap.add_argument("--thresholds", default="0.75,0.80,0.85,0.90")
    ap.add_argument("--show", type=int, default=40, help="số nhóm hiển thị cho mỗi ngưỡng")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--linkage", default=None, help="average | complete (mặc định theo config)")
    ap.add_argument("--metadata", default=None, help="chỉ dùng các item có trong metadata này (vd. metadata_final.csv)")
    args = ap.parse_args()

    if args.linkage:
        config.KEYWORD_LINKAGE = args.linkage
    tdir = os.path.join(args.out, "cache", "text")
    keep = None
    if args.metadata:
        import pandas as pd
        keep = set(pd.read_csv(args.metadata, dtype=str, keep_default_na=False)["item_id"].str.strip())
    item_cand = {f[:-5]: load_json(os.path.join(tdir, f))["candidates"]
                 for f in os.listdir(tdir) if f.endswith(".json") and (keep is None or f[:-5] in keep)}
    terms, total, dropped = kw.collect(item_cand)
    print(f"{len(item_cand)} file, {len(terms)} ứng viên (bỏ {dropped})")

    enc = content_text.Encoder(pick_device(args.device))
    E = enc.encode(terms, normalize=True)
    Z = kw.cluster_tree(E)

    lines = [f"Linkage: {config.KEYWORD_LINKAGE}; model: {config.ST_MODEL}; {len(terms)} ứng viên\n"]
    for thr in [float(x) for x in args.thresholds.split(",")]:
        groups = kw.make_groups(terms, kw.cut(Z, len(terms), thr), total)
        multi = [g for g in groups if len(g) > 1]
        fmt = lambda g: f"  [{terms[g[0]]}] <- " + ", ".join(f"{terms[i]}({total[terms[i]]})" for i in g)
        lines.append(f"\n===== Ngưỡng cosine {thr:.2f} =====")
        lines.append(f"Số nhóm: {len(groups)} | nhóm >1 thành viên: {len(multi)} | "
                     f"nhóm lớn nhất: {max(len(g) for g in groups)} thành viên")
        lines.append("-- Các nhóm có tổng tần suất cao nhất:")
        lines += [fmt(g) for g in multi[:args.show]]
        lines.append("-- 10 nhóm nhiều thành viên nhất (kiểm tra gộp nhầm):")
        lines += [fmt(g) for g in sorted(multi, key=len, reverse=True)[:10]]
    report = "\n".join(lines)
    path = os.path.join(args.out, f"keyword_threshold_report_{config.KEYWORD_LINKAGE}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\nĐã ghi {path}")


if __name__ == "__main__":
    main()
