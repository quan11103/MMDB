"""
Đặc trưng âm học được thiết kế thủ công (Handcrafted Acoustic Features) — vector H 126 chiều.

  Miền thời gian            :  9  (RMS x4, ZCR x4, Silence Ratio)
  Cao độ & chất lượng giọng :  7  (F0 Mean/Std/Min/Max, Jitter local, Shimmer local, HNR)
  Phổ                       : 20  (Centroid, Bandwidth, Roll-off, Flux, Flatness; mỗi cái x4)
  Formant                   : 12  (F1, F2, F3; mỗi cái x4)
  MFCC + Delta + Delta-Delta: 78  (39 hệ số x Mean/Std)
  -------------------------------
  Tổng                      : 126

Vector H được tính cho TỪNG ĐOẠN (segmenting.audio_bounds): các khung 25 ms nằm trong đoạn được
tổng hợp thành 126 giá trị của đoạn đó -> mỗi file là một ma trận (số đoạn x 126).

Thống kê x4 = Mean, Std, Min, Max theo thời gian (Std dùng 1/M như công thức trong báo cáo).
"""
import numpy as np
import librosa
import parselmouth
from parselmouth.praat import call

import config

STATS = ("mean", "std", "min", "max")
EPS = 1e-10


# ------------------------------------------------------------------
# Tiện ích
# ------------------------------------------------------------------
def _stats4(x: np.ndarray) -> list:
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return [np.nan] * 4
    return [x.mean(), x.std(), x.min(), x.max()]


def _frames(y: np.ndarray) -> np.ndarray:
    """Chia khung 25 ms / bước 10 ms, không đệm biên. Trả về (T, FRAME_LENGTH)."""
    if y.size < config.FRAME_LENGTH:
        y = np.pad(y, (0, config.FRAME_LENGTH - y.size))
    return librosa.util.frame(y, frame_length=config.FRAME_LENGTH,
                              hop_length=config.HOP_LENGTH, axis=0)


def _delta(c: np.ndarray, n: int) -> np.ndarray:
    """d_t = sum_{k=1..N} k (c_{t+k} - c_{t-k}) / (2 sum k^2); c có dạng (D, T).
    Biên được xử lý bằng cách lặp lại khung đầu/cuối (như HTK)."""
    T = c.shape[1]
    padded = np.pad(c, ((0, 0), (n, n)), mode="edge")
    denom = 2.0 * sum(k * k for k in range(1, n + 1))
    d = np.zeros_like(c, dtype=np.float64)
    for k in range(1, n + 1):
        d += k * (padded[:, n + k:n + k + T] - padded[:, n - k:n - k + T])
    return d / denom


# ------------------------------------------------------------------
# 1. Miền thời gian (9)
# ------------------------------------------------------------------
def time_domain(frames: np.ndarray) -> dict:
    # RMS = sqrt(1/N sum x_n^2)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))

    # ZCR = N_changes / (N - 1): tỉ lệ cặp mẫu liên tiếp đổi dấu trong khung
    signs = np.signbit(frames)
    n_changes = np.count_nonzero(signs[:, 1:] != signs[:, :-1], axis=1)
    zcr = n_changes / (frames.shape[1] - 1)

    # Silence Ratio = N_silent / N_total, khung im lặng: RMS < RMS_max - 40 dB
    rms_db = 20.0 * np.log10(rms + EPS)
    silent = rms_db < (rms_db.max() - config.SILENCE_DB_BELOW_MAX)
    sr_ratio = float(np.count_nonzero(silent)) / len(rms)

    out = {}
    for name, series in (("rms", rms), ("zcr", zcr)):
        for s, v in zip(STATS, _stats4(series)):
            out[f"{name}_{s}"] = v
    out["silence_ratio"] = sr_ratio
    return out


# ------------------------------------------------------------------
# 2. Phổ (20)
# ------------------------------------------------------------------
def spectral(frames: np.ndarray) -> dict:
    sr = config.SAMPLE_RATE
    win = np.hamming(config.FRAME_LENGTH + 1)[:-1]          # Hamming tuần hoàn
    X = np.abs(np.fft.rfft(frames * win, n=config.N_FFT, axis=1))   # |X(k)|, k = 0..N/2
    f = np.arange(X.shape[1]) * sr / config.N_FFT

    total = X.sum(axis=1)
    valid = total > 1e-8                                    # bỏ khung số 0 tuyệt đối
    Xv, tv = X[valid], total[valid]

    # Spectral Centroid
    sc = (Xv * f).sum(axis=1) / tv
    # Spectral Bandwidth (độ lệch có trọng số quanh trọng tâm phổ)
    bw = np.sqrt(((f[None, :] - sc[:, None]) ** 2 * Xv).sum(axis=1) / tv)
    # Spectral Roll-off 85%: bin đầu tiên mà tổng tích lũy >= 0.85 tổng
    cum = np.cumsum(Xv, axis=1)
    k_r = np.argmax(cum >= 0.85 * tv[:, None], axis=1)
    rolloff = k_r * sr / config.N_FFT
    # Spectral Flux: sum_k (|X_t(k)| - |X_{t-1}(k)|)^2
    flux = np.sum(np.diff(X, axis=0) ** 2, axis=1)
    # Spectral Flatness: GM(P) / AM(P), P = |X|^2 + eps
    P = Xv ** 2 + EPS
    flat = np.exp(np.mean(np.log(P), axis=1)) / np.mean(P, axis=1)

    out = {}
    for name, series in (("spec_centroid", sc), ("spec_bandwidth", bw),
                         ("spec_rolloff", rolloff), ("spec_flux", flux),
                         ("spec_flatness", flat)):
        for s, v in zip(STATS, _stats4(series)):
            out[f"{name}_{s}"] = v
    return out


# ------------------------------------------------------------------
# 3. Cao độ & chất lượng giọng (7) + 4. Formant (12) — Praat
# ------------------------------------------------------------------
def praat_features(y: np.ndarray) -> dict:
    snd = parselmouth.Sound(y.astype(np.float64), sampling_frequency=config.SAMPLE_RATE)

    # F0: autocorrelation (To Pitch (ac)); chỉ giữ khung hữu thanh (f0 > 0)
    pitch = snd.to_pitch_ac(time_step=config.PITCH_TIME_STEP,
                            pitch_floor=config.PITCH_FLOOR,
                            pitch_ceiling=config.PITCH_CEILING)
    f0_all = pitch.selected_array["frequency"]
    voiced_mask = f0_all > 0
    f0 = f0_all[voiced_mask]
    voiced_times = pitch.xs()[voiced_mask]

    out = {}
    for s, v in zip(STATS, _stats4(f0)):
        out[f"f0_{s}"] = v

    # Jitter / Shimmer local (%), dựa trên chuỗi chu kỳ từ PointProcess
    pp = call(snd, "To PointProcess (periodic, cc)", config.PITCH_FLOOR, config.PITCH_CEILING)
    jitter = call(pp, "Get jitter (local)", 0, 0,
                  config.PERIOD_FLOOR, config.PERIOD_CEILING, config.MAX_PERIOD_FACTOR)
    shimmer = call([snd, pp], "Get shimmer (local)", 0, 0,
                   config.PERIOD_FLOOR, config.PERIOD_CEILING,
                   config.MAX_PERIOD_FACTOR, config.MAX_AMPLITUDE_FACTOR)
    out["jitter_local_pct"] = jitter * 100.0
    out["shimmer_local_pct"] = shimmer * 100.0

    # HNR (dB): To Harmonicity (cc) — autocorrelation; Praat bỏ qua khung vô thanh khi lấy mean
    harm = call(snd, "To Harmonicity (cc)", config.HNR_TIME_STEP, config.PITCH_FLOOR,
                config.HNR_SILENCE_THRESHOLD, config.HNR_PERIODS_PER_WINDOW)
    out["hnr_db"] = call(harm, "Get mean", 0, 0)

    # Formant F1..F3: To Formant (burg) = LPC Burg; lấy giá trị tại các khung hữu thanh
    formant = snd.to_formant_burg(time_step=config.PITCH_TIME_STEP,
                                  max_number_of_formants=config.N_FORMANTS_LPC,
                                  maximum_formant=config.MAX_FORMANT_HZ,
                                  window_length=config.FORMANT_WINDOW,
                                  pre_emphasis_from=config.FORMANT_PRE_EMPHASIS)
    for i in (1, 2, 3):
        vals = np.array([formant.get_value_at_time(i, t) for t in voiced_times], dtype=np.float64)
        for s, v in zip(STATS, _stats4(vals)):
            out[f"f{i}_{s}"] = v

    out["_n_voiced_frames"] = int(voiced_mask.sum())   # thông tin phụ, không thuộc vector H
    return out


# ------------------------------------------------------------------
# 5. MFCC + Delta + Delta-Delta (78)
# ------------------------------------------------------------------
def mfcc_features(y: np.ndarray) -> dict:
    mfcc = librosa.feature.mfcc(
        y=y, sr=config.SAMPLE_RATE, n_mfcc=config.N_MFCC,
        n_fft=config.N_FFT, win_length=config.FRAME_LENGTH, hop_length=config.HOP_LENGTH,
        window=config.WINDOW, center=False, n_mels=config.N_MELS,
    ).astype(np.float64)                                    # (13, T): C0..C12, DCT-II
    n = (config.DELTA_WIDTH - 1) // 2
    d1 = _delta(mfcc, n)
    d2 = _delta(d1, n)                                      # Delta của chuỗi Delta
    full = np.vstack([mfcc, d1, d2])                        # (39, T)

    names = ([f"mfcc{i}" for i in range(config.N_MFCC)] +
             [f"dmfcc{i}" for i in range(config.N_MFCC)] +
             [f"ddmfcc{i}" for i in range(config.N_MFCC)])
    out = {}
    for name, row in zip(names, full):
        out[f"{name}_mean"] = row.mean()
    for name, row in zip(names, full):
        out[f"{name}_std"] = row.std()
    return out


# ------------------------------------------------------------------
# Tổng hợp
# ------------------------------------------------------------------
def feature_names() -> list:
    names = []
    for n in ("rms", "zcr"):
        names += [f"{n}_{s}" for s in STATS]
    names += ["silence_ratio"]
    names += [f"f0_{s}" for s in STATS] + ["jitter_local_pct", "shimmer_local_pct", "hnr_db"]
    for n in ("spec_centroid", "spec_bandwidth", "spec_rolloff", "spec_flux", "spec_flatness"):
        names += [f"{n}_{s}" for s in STATS]
    for i in (1, 2, 3):
        names += [f"f{i}_{s}" for s in STATS]
    base = ([f"mfcc{i}" for i in range(config.N_MFCC)] +
            [f"dmfcc{i}" for i in range(config.N_MFCC)] +
            [f"ddmfcc{i}" for i in range(config.N_MFCC)])
    names += [f"{b}_mean" for b in base] + [f"{b}_std" for b in base]
    return names


FEATURE_GROUPS = {
    "time": (0, 9), "pitch_voice": (9, 16), "spectral": (16, 36),
    "formant": (36, 48), "mfcc": (48, 126),
}


def extract(y: np.ndarray) -> dict:
    """Trả về dict {tên đặc trưng: giá trị} (126 khóa) + khóa phụ bắt đầu bằng '_'."""
    fr = _frames(y)
    feats = {}
    feats.update(time_domain(fr))
    feats.update(praat_features(y))
    feats.update(spectral(fr))
    feats.update(mfcc_features(y))
    feats["_n_frames"] = int(fr.shape[0])
    return feats


def to_vector(feats: dict) -> np.ndarray:
    return np.array([feats[n] for n in feature_names()], dtype=np.float64)


def extract_segments(y: np.ndarray, bounds: list) -> tuple:
    """Vector H của từng đoạn. bounds = [(start, end)] theo mẫu.
    Trả về (X: (số đoạn, 126), số khung hữu thanh của từng đoạn)."""
    X, voiced = [], []
    for a, b in bounds:
        f = extract(y[a:b])
        X.append(to_vector(f))
        voiced.append(f["_n_voiced_frames"])
    return np.vstack(X), np.array(voiced, dtype=np.int32)
