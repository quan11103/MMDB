"""
Chia đoạn theo âm tiết và so khớp bằng cửa sổ trượt (theo yêu cầu của giảng viên).

- Độ dài 1 đoạn = SEGMENT_SYLLABLES âm tiết.
    audio: SEGMENT_SYLLABLES x thời lượng trung bình 1 âm tiết (đo trên dataset, bước 'syllable')
    text : SEGMENT_SYLLABLES từ (mỗi từ cách nhau bởi khoảng trắng = 1 âm tiết tiếng Việt)
- File trong CSDL và file truy vấn được chia thành các đoạn CÙNG độ dài; phần dư cuối file
  (ngắn hơn 1 đoạn) bị bỏ, trừ khi cả file ngắn hơn 1 đoạn (khi đó cả file là 1 đoạn).
- So khớp: cửa sổ dài bằng số đoạn của file ngắn hơn, trượt từng đoạn trên file dài hơn;
  điểm tại mỗi vị trí = trung bình cosine giữa các cặp đoạn thẳng hàng; điểm của cặp file = max.
"""
import json
import os
import subprocess

import numpy as np

import config

STATS_FILE = "syllable_stats.json"


# ------------------------------------------------------------------
# Thời lượng âm tiết và độ dài đoạn
# ------------------------------------------------------------------
def audio_duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe lỗi: {out.stderr.decode(errors='ignore')}")
    return float(out.stdout.decode().strip())


def syllable_stats(durations: list, n_words: list) -> dict:
    d, w = np.asarray(durations, float), np.asarray(n_words, float)
    syl = float(d.sum() / w.sum())                      # giây / âm tiết trên toàn dataset
    rate = w / d                                        # âm tiết / giây của từng file
    return {
        "n_items": int(len(d)),
        "total_duration_sec": float(d.sum()), "total_syllables": int(w.sum()),
        "syllable_sec": syl,
        "syllables_per_sec_median": float(np.median(rate)),
        "syllables_per_sec_min": float(rate.min()), "syllables_per_sec_max": float(rate.max()),
        "segment_syllables": config.SEGMENT_SYLLABLES,
        "segment_sec_exact": config.SEGMENT_SYLLABLES * syl,
        "segment_rounded": bool(config.SEGMENT_ROUND_SEC),
        "segment_sec": float(round(config.SEGMENT_SYLLABLES * syl)) if config.SEGMENT_ROUND_SEC
                       else config.SEGMENT_SYLLABLES * syl,
    }


def load_segment_sec(out_dir: str) -> float:
    """Độ dài đoạn audio (giây) đã đo; dùng cho cả file CSDL và file truy vấn."""
    p = os.path.join(out_dir, STATS_FILE)
    if not os.path.exists(p):
        raise RuntimeError(f"Chưa có {p}: chạy bước 'syllable' trước")
    with open(p, encoding="utf-8") as f:
        s = json.load(f)
    if s["segment_syllables"] != config.SEGMENT_SYLLABLES or \
            s.get("segment_rounded", False) != bool(config.SEGMENT_ROUND_SEC):
        raise RuntimeError(f"{STATS_FILE} được tính với SEGMENT_SYLLABLES = {s['segment_syllables']}, "
                           f"(làm tròn = {s.get('segment_rounded', False)}), khác config hiện tại: "
                           f"chạy lại bước 'syllable'")
    return float(s["segment_sec"])


# ------------------------------------------------------------------
# Chia đoạn
# ------------------------------------------------------------------
def audio_bounds(n_samples: int, segment_sec: float, sr: int = config.SAMPLE_RATE) -> list:
    """[(start, end)] theo mẫu, các đoạn liên tiếp không chồng lấn, cùng độ dài."""
    L = int(round(segment_sec * sr))
    n = n_samples // L
    if n == 0:
        return [(0, n_samples)]
    return [(i * L, (i + 1) * L) for i in range(n)]


def text_chunks(words: list, k: int = None) -> list:
    """[(vị trí từ bắt đầu, chuỗi k từ)], cùng độ dài k từ, không chồng lấn."""
    k = k or config.SEGMENT_SYLLABLES
    n = len(words) // k
    if n == 0:
        return [(0, " ".join(words))] if words else []
    return [(i * k, " ".join(words[i * k:(i + 1) * k])) for i in range(n)]


# ------------------------------------------------------------------
# So khớp bằng cửa sổ trượt (dùng ở nội dung 4)
# ------------------------------------------------------------------
def _unit(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float64)
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-12)


def sliding_scores(Q: np.ndarray, D: np.ndarray) -> np.ndarray:
    """Q: (m, d) các đoạn của file truy vấn; D: (n, d) các đoạn của một file trong CSDL.
    Cửa sổ dài min(m, n) đoạn trượt từng đoạn trên file dài hơn.
    Trả về S(p), p = 0 .. |m - n|: trung bình cosine giữa các cặp đoạn thẳng hàng tại vị trí p."""
    Q, D = _unit(Q), _unit(D)
    short, long_ = (Q, D) if len(Q) <= len(D) else (D, Q)
    m, n = len(short), len(long_)
    C = short @ long_.T                                  # (m, n): cosine mọi cặp đoạn
    return np.array([np.trace(C[:, p:p + m]) / m for p in range(n - m + 1)])


def sliding_similarity(Q: np.ndarray, D: np.ndarray) -> tuple:
    """(điểm tương đồng = max S(p), vị trí p tốt nhất)."""
    s = sliding_scores(Q, D)
    p = int(np.argmax(s))
    return float(s[p]), p
