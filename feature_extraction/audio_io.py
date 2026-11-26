"""Đọc audio bằng FFmpeg -> numpy float32, 16 kHz, mono."""
import subprocess

import numpy as np

import config


def load_audio(path: str, sr: int = config.SAMPLE_RATE) -> np.ndarray:
    """Giải mã file (MP3/WAV/...) thành tín hiệu float32 trong [-1, 1].

    FFmpeg thực hiện đồng thời: chuyển mono (trung bình các kênh) và lấy mẫu lại.
    File truy vấn ở nội dung 4 cũng phải đọc bằng hàm này.
    """
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error",
        "-i", str(path),
        "-ac", "1",            # mono
        "-ar", str(sr),        # 16 kHz
        "-f", "f32le", "-acodec", "pcm_f32le",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg lỗi khi đọc {path}: {proc.stderr.decode(errors='ignore')}")
    y = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if y.size == 0:
        raise RuntimeError(f"File rỗng hoặc không giải mã được: {path}")
    return y
