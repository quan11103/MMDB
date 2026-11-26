"""
Bộ thuộc tính nội dung (theo từng file):
  - làm sạch transcript
  - vector nhúng ngữ nghĩa của từng chunk (chunk SEGMENT_SYLLABLES từ -> Sentence Transformer -> L2)
  - NER (underthesea): PER, ORG, LOC
  - ứng viên từ khóa (tách từ + từ loại + N-gram) — gom nhóm toàn dataset nằm ở keywords.py
"""
import re
import unicodedata
from collections import Counter

import numpy as np

import config

# ------------------------------------------------------------------
# Làm sạch
# ------------------------------------------------------------------
_TAG_RE = re.compile(r"\[[^\]]{0,40}\]")        # [Âm nhạc], [Music], [Vỗ tay] ... của phụ đề YouTube
_WS_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)   # thống nhất dạng Unicode tiếng Việt
    text = _TAG_RE.sub(" ", text)
    text = text.replace(">>", " ")
    return _WS_RE.sub(" ", text).strip()


def read_transcript(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as f:
        return clean_text(f.read())


def _pieces(words: list, size: int) -> list:
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


_SENT_RE = re.compile(r"(?<=[.!?;:…])\s+")


def _sentences(text: str) -> list:
    """Tách câu theo dấu câu (transcript Whisper có dấu câu; phụ đề tự động thường không có),
    câu quá dài được cắt thành các đoạn <= NER_PIECE_WORDS từ. Ứng viên và thực thể không vượt qua ranh giới câu."""
    out = []
    for sent in _SENT_RE.split(text):
        sent = sent.strip().rstrip(".!?;:…").strip()
        if sent:
            out += _pieces(sent.split(), config.NER_PIECE_WORDS)
    return out


# ------------------------------------------------------------------
# Sentence Transformer (dùng chung cho vector ngữ nghĩa và keywords)
# ------------------------------------------------------------------
class Encoder:
    def __init__(self, device: str = "cpu"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(config.ST_MODEL, device=device)
        get_dim = getattr(self.model, "get_embedding_dimension", None) or \
            self.model.get_sentence_embedding_dimension
        self.dim = get_dim()

    def encode(self, texts: list, normalize: bool = False) -> np.ndarray:
        return self.model.encode(texts, batch_size=config.ST_BATCH, convert_to_numpy=True,
                                 normalize_embeddings=normalize, show_progress_bar=False)


# ------------------------------------------------------------------
# Vector nhúng ngữ nghĩa
# ------------------------------------------------------------------
def segment_embeddings(text: str, encoder: Encoder) -> tuple:
    """Vector nhúng ngữ nghĩa của từng chunk SEGMENT_SYLLABLES từ (segmenting.text_chunks),
    mỗi hàng đã chuẩn hóa L2. Trả về (E: (số chunk, 768), vị trí từ bắt đầu của từng chunk)."""
    import segmenting
    chunks = segmenting.text_chunks(text.split())
    if not chunks:
        raise ValueError("Transcript rỗng")
    E = encoder.encode([c for _, c in chunks])
    E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-12)
    return E.astype(np.float32), np.array([st for st, _ in chunks], dtype=np.int32)


# ------------------------------------------------------------------
# NER
# ------------------------------------------------------------------
def _ner_rows(piece: str) -> list:
    """Chuẩn hóa đầu ra underthesea.ner về [(word, tag BIO)]."""
    from underthesea import ner
    rows = ner(piece)
    out = []
    for r in rows:
        if isinstance(r, dict):                     # một số phiên bản trả về dict
            out.append((r.get("word", ""), r.get("entity", r.get("tag", "O"))))
        else:
            out.append((r[0], r[-1]))
    return out


def extract_ner(text: str) -> list:
    """Trả về [{'text', 'label', 'count'}] sắp xếp theo số lần xuất hiện."""
    counts, surface = Counter(), {}
    for piece in _sentences(text):
        cur, cur_label = [], None
        for word, tag in _ner_rows(piece) + [("", "O")]:      # phần tử cuối để đóng thực thể
            if tag.startswith("I-") and cur and tag[2:] == cur_label:
                cur.append(word)
                continue
            if cur and cur_label in config.NER_LABELS:
                ent = " ".join(cur)
                key = (ent.lower(), cur_label)
                counts[key] += 1
                surface.setdefault(key, ent)
            cur, cur_label = ([word], tag[2:]) if tag[:2] in ("B-", "I-") else ([], None)
    return [{"text": surface[k], "label": k[1], "count": c} for k, c in counts.most_common()]


# ------------------------------------------------------------------
# Ứng viên từ khóa
# ------------------------------------------------------------------
_DEFAULT_STOPWORDS = {
    # danh từ/cụm chung, ít mang nội dung
    "điều", "việc", "cái", "người", "thứ", "lúc", "khi", "lần", "cách", "chuyện", "kiểu",
    "nhiều", "phần", "mức", "loại", "chỗ", "bên", "nơi", "đây", "đó", "kia", "này", "ấy",
    "hôm nay", "bây giờ", "ngày", "năm", "tháng", "giờ", "phút", "giây", "thời gian",
    "anh", "chị", "em", "bạn", "các bạn", "mình", "chúng ta", "chúng mình", "ông", "bà",
    "video", "kênh", "clip", "phút giây", "ví dụ", "trường hợp", "vấn đề",
    "review", "ok", "like", "subscribe", "share", "comment",
    # danh từ chỉ loại / tiền tố danh từ hóa, bị gán nhãn N nhưng không mang nội dung
    "độ", "niềm", "nỗi", "dạng", "khoản", "câu", "hôm", "cú", "món", "cuộc", "sự",
}


def load_stopwords() -> set:
    sw = set(_DEFAULT_STOPWORDS)
    if config.STOPWORDS_FILE:
        with open(config.STOPWORDS_FILE, encoding="utf-8") as f:
            sw |= {unicodedata.normalize("NFC", l.strip().lower()) for l in f if l.strip()}
    return sw


def _is_acronym(word: str) -> bool:
    return word.isascii() and word.isalpha() and word.isupper() and len(word) >= 2


def _is_bad_token(word: str, stopwords: set) -> bool:
    """Từ dừng, quá ngắn hoặc không có chữ cái. Từ viết tắt viết hoa (AI, CPU...) không bị coi là
    từ dừng, kể cả khi trùng với một từ dừng tiếng Việt viết thường (ví dụ 'ai' = đại từ)."""
    w = word.lower()
    if len(w) < 2 or not any(ch.isalpha() for ch in w):
        return True
    return w in stopwords and not _is_acronym(word)


def _is_number(word: str) -> bool:
    return word.replace(".", "").replace(",", "").isdigit()


# Âm tiết tiếng Việt viết không dấu: phụ âm đầu + vần + phụ âm cuối hợp lệ.
_VI_SYLLABLE = re.compile(r"(ngh|ng|gh|gi|kh|nh|ph|qu|th|tr|ch|[bcdghklmnprstvx])?"
                          r"[aeiouy]{1,3}(ng|nh|ch|[cmnpt])?")


def _is_foreign(word: str) -> bool:
    """Từ nước ngoài (laptop, smartphone, RTX, OLED, AI...). Bộ gán từ loại của underthesea
    thường gán sai nhãn cho các từ này (ví dụ 'AI' -> P, 'smartphone' -> V), nên nhận diện riêng:
    chỉ gồm chữ Latin không dấu VÀ (viết hoa toàn bộ, hoặc có âm tiết không phải âm tiết tiếng Việt)."""
    parts = word.split()
    if not parts or not all(p.isascii() and p.isalnum() and any(c.isalpha() for c in p) for p in parts):
        return False
    if all(p.isupper() and len(p) >= 2 for p in parts):
        return True
    return any(not _VI_SYLLABLE.fullmatch(p.lower()) for p in parts)


def extract_candidates(text: str, stopwords: set) -> dict:
    """N-gram 1..3 từ: từ đầu là danh từ (hoặc từ nước ngoài), các từ sau là danh từ/tính từ/
    từ nước ngoài/số (để giữ tên model như 'rtx 5060', 'iphone 17').
    Trả về {ứng viên (chữ thường): số lần} chỉ gồm ứng viên xuất hiện >= MIN_FREQ_IN_FILE lần."""
    from underthesea import pos_tag
    counts = Counter()
    for piece in _sentences(text):
        tagged = pos_tag(piece)
        n = len(tagged)
        for i in range(n):
            w, t = tagged[i]
            if _is_bad_token(w, stopwords) or not (t in config.HEAD_POS or _is_foreign(w)):
                continue
            words = [w]
            counts[w.lower()] += 1
            for j in range(i + 1, min(i + config.NGRAM_MAX, n)):
                wj, tj = tagged[j]
                ok = _is_number(wj) or (not _is_bad_token(wj, stopwords) and
                                        (tj in config.MODIFIER_POS or _is_foreign(wj)))
                if not ok:
                    break
                words.append(wj)
                counts[" ".join(words).lower()] += 1
    return {k: v for k, v in counts.items() if v >= config.MIN_FREQ_IN_FILE}
