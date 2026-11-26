"""
Vector nhúng người nói ECAPA-TDNN (pretrained, không huấn luyện lại).

Quy trình: audio 16 kHz -> chia đoạn theo âm tiết (segmenting.audio_bounds) -> embedding từng đoạn
-> chuẩn hóa L2 từng đoạn. Mỗi file là một ma trận (số đoạn x D).
"""
import numpy as np

import config

_model = None


def _load_model(device: str = "cpu"):
    global _model
    if _model is None:
        try:
            from speechbrain.inference.speaker import EncoderClassifier   # speechbrain >= 1.0
        except ImportError:
            from speechbrain.pretrained import EncoderClassifier          # speechbrain 0.5.x
        kwargs = {}
        try:   # Windows không cho tạo symlink nếu không có quyền admin -> copy file model
            from speechbrain.utils.fetching import LocalStrategy
            kwargs["local_strategy"] = LocalStrategy.COPY
        except ImportError:
            pass
        _model = EncoderClassifier.from_hparams(
            source=config.ECAPA_SOURCE, savedir=config.ECAPA_SAVEDIR,
            run_opts={"device": device}, **kwargs,
        )
    return _model


def extract_segments(y: np.ndarray, bounds: list, device: str = "cpu") -> np.ndarray:
    """Speaker embedding của từng đoạn, mỗi hàng đã chuẩn hóa L2. Trả về (số đoạn, D)."""
    import torch

    model = _load_model(device)
    parts = [y[a:b] for a, b in bounds]
    seg_len = max(len(p) for p in parts)
    embs = []
    for k in range(0, len(parts), config.ECAPA_BATCH):
        batch = parts[k:k + config.ECAPA_BATCH]
        wav = np.zeros((len(batch), seg_len), dtype=np.float32)
        lens = np.zeros(len(batch), dtype=np.float32)
        for i, p in enumerate(batch):
            wav[i, :len(p)] = p
            lens[i] = len(p) / seg_len                     # độ dài tương đối (speechbrain)
        with torch.no_grad():
            e = model.encode_batch(torch.from_numpy(wav).to(device),
                                   torch.from_numpy(lens).to(device))
        embs.append(e.squeeze(1).cpu().numpy())
    E = np.concatenate(embs, axis=0)
    return (E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-12)).astype(np.float32)
