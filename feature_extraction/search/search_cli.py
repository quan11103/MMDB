"""
Tìm kiếm với một file truy vấn, in top 3 và lưu toàn bộ kết quả trung gian (cho mục 4b).

  python search_cli.py D:/BTL/queries/q01.mp3 --dsn postgresql://postgres:btl24@localhost:5434/btl
  python search_cli.py q01.mp3 --transcript q01.txt --alpha 0.5 --beta 0.7 --out ket_qua/q01

Kết quả lưu trong --out:
  query_info.json       thời lượng, các đoạn, transcript, từ khóa đại diện, thực thể
  query_features.csv    126 đặc trưng thô + đã chuẩn hóa min-max của từng đoạn 10 s
  ranking_speaker.csv   xếp hạng giọng nói (S_H, S_E, S_speaker, vị trí cửa sổ) — 20 file đầu
  ranking_content.csv   xếp hạng nội dung (S_text, S_kw, S_content, vị trí cửa sổ) — 20 file đầu
  result.json           top 3 mỗi loại
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

from search_engine import DEFAULT_ALPHA, DEFAULT_BETA, SearchEngine, config

SHOW = ["f0_mean", "f0_std", "jitter_local_pct", "shimmer_local_pct", "hnr_db",
        "spec_centroid_mean", "zcr_mean", "silence_ratio", "f1_mean", "f2_mean"]


def fmt_sec(s):
    return f"{int(s // 60)}:{s % 60:04.1f}"


def where_audio(t):
    """Vị trí cửa sổ khớp: cửa sổ dài bằng file ngắn hơn, trượt trên file dài hơn."""
    a, b = t["db_window_sec"]
    qa, qb = t["query_window_sec"]
    if t["query_shorter"]:
        return f"toàn bộ truy vấn khớp đoạn {fmt_sec(a)}–{fmt_sec(b)} của file [{t['item_id']}]"
    return (f"toàn bộ file [{t['item_id']}] ({t['window_segments']} đoạn, {fmt_sec(b)}) "
            f"khớp đoạn {fmt_sec(qa)}–{fmt_sec(qb)} của truy vấn")


def where_text(t):
    a, b = t["db_window_syllables"]
    qa, qb = t["query_window_syllables"]
    if t["query_shorter"]:
        return f"toàn bộ transcript truy vấn khớp âm tiết {a}–{b} của file [{t['item_id']}]"
    return (f"toàn bộ transcript file [{t['item_id']}] ({t['window_chunks']} chunk, {b} âm tiết) "
            f"khớp âm tiết {qa}–{qb} của truy vấn")


def save(out, q, r, names, top_k=20):
    os.makedirs(out, exist_ok=True)
    rows = []
    for k, ((a, b), v) in enumerate(zip(q["segments"], q["n_voiced_frames"])):
        rows.append({"seg_index": k, "start_sec": a, "end_sec": b, "n_voiced_frames": v,
                     **{n: q["H_raw"][k, j] for j, n in enumerate(names)},
                     **{f"norm_{n}": q["H_n"][k, j] for j, n in enumerate(names)}})
    pd.DataFrame(rows).to_csv(os.path.join(out, "query_features.csv"), index=False, encoding="utf-8-sig")
    info = {k: q[k] for k in ("audio_path", "duration_sec", "segment_sec", "segments", "transcript",
                              "transcript_source", "n_words", "word_start", "ner")}
    info.update(n_audio_segments=len(q["segments"]), n_text_segments=len(q["word_start"]),
                ecapa_dim=int(q["E"].shape[1]), text_dim=int(q["T"].shape[1]),
                keywords=q["keywords"][:30])
    with open(os.path.join(out, "query_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1, default=float)
    for kind in ("speaker", "content"):
        pd.DataFrame(r[kind][:top_k]).to_csv(os.path.join(out, f"ranking_{kind}.csv"), index=False,
                                             encoding="utf-8-sig")
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"alpha": r["alpha"], "beta": r["beta"], "top3_content": r["content"][:3],
                   "top3_speaker": r["speaker"][:3]}, f, ensure_ascii=False, indent=1, default=float)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("--transcript", default=None, help="file .txt transcript (bỏ qua Whisper)")
    ap.add_argument("--dsn", default="postgresql://postgres:btl24@localhost:5432/btl")
    ap.add_argument("--alpha", type=float, default=DEFAULT_ALPHA, help="trọng số vector H trong điểm giọng nói")
    ap.add_argument("--beta", type=float, default=DEFAULT_BETA, help="trọng số vector ngữ nghĩa trong điểm nội dung")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default=None, help="thư mục lưu kết quả trung gian")
    args = ap.parse_args()

    eng = SearchEngine(args.dsn, args.device)
    print(f"CSDL: {len(eng.ids)} file | đoạn audio {eng.segment_sec:g} s")
    transcript = None
    if args.transcript:
        with open(args.transcript, encoding="utf-8-sig") as f:
            transcript = f.read()
    q, r, top = eng.search(args.audio, transcript, args.alpha, args.beta)

    print(f"\n=== File truy vấn: {os.path.basename(args.audio)}")
    print(f"Thời lượng {fmt_sec(q['duration_sec'])} | {len(q['segments'])} đoạn audio | "
          f"{q['n_words']} âm tiết, {len(q['word_start'])} chunk | transcript: {q['transcript_source']}")
    print("Transcript:", q["transcript"][:200] + ("…" if len(q["transcript"]) > 200 else ""))
    idx = [eng.feature_names.index(n) for n in SHOW]
    print("Đặc trưng âm học (trung bình các đoạn):",
          ", ".join(f"{n}={np.mean(q['H_raw'][:, j]):.3g}" for n, j in zip(SHOW, idx)))
    print("Từ khóa đại diện:", ", ".join(f"{k['keyword']}({k['tfidf']:.1f})" for k in q["keywords"][:10]))
    print("Thực thể:", ", ".join(f"{e['text']}/{e['label']}" for e in q["ner"][:10]) or "—")

    print(f"\n=== 3 file có NỘI DUNG giống nhất  (S_content = {args.beta}·S_text + {1 - args.beta:.2g}·S_kw)")
    for t in top["content"]:
        print(f"{t['rank']}. [{t['item_id']}] {t['chapter_title']} — {t['video_title']}")
        print(f"   S_content={t['score']:.4f}  S_text={t['S_text']:.4f}  S_kw={t['S_kw']:.4f}")
        print(f"   {where_text(t)}")
    print(f"\n=== 3 file có GIỌNG NÓI giống nhất  (S_speaker = {args.alpha}·S_H + {1 - args.alpha:.2g}·S_E)")
    for t in top["speaker"]:
        print(f"{t['rank']}. [{t['item_id']}] {t['channel_name']} — {t['chapter_title']}")
        print(f"   S_speaker={t['score']:.4f}  S_H={t['S_H']:.4f}  S_E={t['S_E']:.4f}")
        print(f"   {where_audio(t)}")

    if args.out:
        save(args.out, q, r, eng.feature_names)
        print(f"\nĐã lưu kết quả trung gian vào {args.out}")


if __name__ == "__main__":
    main()
