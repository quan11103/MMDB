"""
Hệ thống tìm kiếm âm thanh (nội dung 4).

Đầu vào: một file âm thanh mới. Đầu ra gồm 2 phần, xếp giảm dần theo độ tương đồng:
  - 3 file có NỘI DUNG giống nhất
  - 3 file có GIỌNG NÓI giống nhất

Quy trình:
  1. Trích rút đặc trưng của file truy vấn bằng ĐÚNG các hàm đã dùng cho CSDL (mục 3.1):
     audio 16 kHz mono -> chia đoạn 10 s -> vector H (chuẩn hóa min-max [-1, 1] bằng min, max của CSDL) + ECAPA;
     transcript (Whisper small) -> chunk 40 âm tiết -> vector ngữ nghĩa; ứng viên từ khóa -> từ điển chung.
  2. So khớp với từng file trong CSDL bằng cửa sổ trượt (cửa sổ dài bằng file ngắn hơn):
     Giọng nói : S_spk(p) = α·S_H(p) + (1 − α)·S_E(p),   S_speaker = max_p S_spk(p)
     Nội dung  : S_text = max_p S_T(p),  S_kw = cosine giữa 2 vector TF-IDF từ khóa đại diện
                 (vector truy vấn chỉ gồm các từ khóa có trong từ điển chung)
                 S_content = β·S_text + (1 − β)·S_kw
  3. Xếp hạng, lấy top 3 mỗi loại.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import config                      # noqa: E402
import segmenting                  # noqa: E402

DEFAULT_ALPHA = 0.5                # đã chốt: trong dải P@3 tối đa (0–0,6), H và ECAPA đóng góp ngang nhau
DEFAULT_BETA = 0.7                 # đã chốt: P@3 nội dung cao nhất trên bộ test


def _arr(v):
    return np.asarray(v, dtype=np.float32)


class SearchEngine:
    def __init__(self, dsn: str, device: str = "cpu", whisper_model: str = "small"):
        self.dsn, self.device, self.whisper_name = dsn, device, whisper_model
        self._encoder = self._whisper = self._stopwords = None
        self._load_db()

    # ------------------------------------------------------------------
    # Đọc CSDL vào bộ nhớ (512 item, khoảng 8.600 đoạn: vài chục MB)
    # ------------------------------------------------------------------
    def _load_db(self):
        import psycopg
        with psycopg.connect(self.dsn) as c:
            params = dict(c.execute("SELECT key, value FROM system_param").fetchall())
            self.segment_sec = float(params["segment_sec"])
            if int(params["segment_syllables"]) != config.SEGMENT_SYLLABLES:
                raise RuntimeError("SEGMENT_SYLLABLES trong config khác với CSDL")
            self.kw_threshold = float(params["keyword"]["threshold"])

            self.items = {}
            for r in c.execute("""SELECT i.item_id, i.video_id, v.video_title, v.channel_id, v.channel_name,
                                         i.chapter_title, i.duration_sec, i.audio_path
                                  FROM item i JOIN video v USING (video_id) ORDER BY i.item_id"""):
                self.items[r[0]] = dict(item_id=r[0], video_id=r[1], video_title=r[2], channel_id=r[3],
                                        channel_name=r[4], chapter_title=r[5], duration_sec=r[6],
                                        audio_path=r[7])
            self.ids = list(self.items)

            fd = c.execute("SELECT feature_name, mean, min_val, max_val FROM feature_def "
                           "ORDER BY feature_index").fetchall()
            self.feature_names = [r[0] for r in fd]
            self.mu = np.array([r[1] for r in fd])
            self.vmin = np.array([r[2] for r in fd])
            self.rng = np.array([r[3] for r in fd]) - self.vmin
            self.rng[self.rng == 0] = 1.0

            H, E, T = {}, {}, {}
            for iid, h, e in c.execute("""SELECT item_id, h_norm::real[], ecapa::real[] FROM audio_segment
                                           ORDER BY item_id, seg_index"""):
                H.setdefault(iid, []).append(h)
                E.setdefault(iid, []).append(e)
            for iid, t in c.execute("SELECT item_id, embedding::real[] FROM text_segment ORDER BY item_id, seg_index"):
                T.setdefault(iid, []).append(t)
            self.H = {k: _arr(v) for k, v in H.items()}
            self.E = {k: _arr(v) for k, v in E.items()}
            self.T = {k: _arr(v) for k, v in T.items()}

            groups = c.execute("SELECT group_id, keyword, df, idf, centroid::real[] FROM keyword_group "
                               "ORDER BY group_id").fetchall()
            if [g[0] for g in groups] != list(range(len(groups))):
                raise RuntimeError("group_id của keyword_group phải liên tục từ 0")
            self.kw_dict = {
                "threshold": self.kw_threshold, "n_docs": len(self.items),
                "groups": [{"group_id": g[0], "keyword": g[1], "df": g[2], "idf": g[3]} for g in groups],
                "centroids": _arr([g[4] for g in groups]),
                "term2gid": dict(c.execute("SELECT term, group_id FROM keyword_member").fetchall()),
            }
            self.kw_vec = {}
            for iid, gid, w in c.execute("SELECT item_id, group_id, tfidf FROM item_keyword"):
                self.kw_vec.setdefault(iid, {})[gid] = float(w)
            self.kw_norm = {k: float(np.sqrt(sum(w * w for w in v.values()))) for k, v in self.kw_vec.items()}

    # ------------------------------------------------------------------
    # Mô hình (nạp khi cần)
    # ------------------------------------------------------------------
    @property
    def encoder(self):
        if self._encoder is None:
            import content_text
            self._encoder = content_text.Encoder(self.device)
        return self._encoder

    @property
    def stopwords(self):
        if self._stopwords is None:
            import content_text
            self._stopwords = content_text.load_stopwords()
        return self._stopwords

    def transcribe(self, path: str) -> str:
        import whisper
        if self._whisper is None:
            self._whisper = whisper.load_model(self.whisper_name, device=self.device)
        out = self._whisper.transcribe(path, language="vi", task="transcribe",
                                       fp16=(self.device == "cuda"), verbose=False)
        return " ".join(s["text"].strip() for s in out.get("segments", []))

    # ------------------------------------------------------------------
    # Bước 1: trích rút đặc trưng của file truy vấn
    # ------------------------------------------------------------------
    def analyze(self, audio_path: str, transcript: str = None) -> dict:
        import audio_io
        import content_text
        import keywords as kw
        import voice_ecapa
        import voice_handcrafted as vh

        y = audio_io.load_audio(audio_path)
        sr = config.SAMPLE_RATE
        bounds = segmenting.audio_bounds(len(y), self.segment_sec)
        H_raw, voiced = vh.extract_segments(y, bounds)
        H_fill = np.where(np.isfinite(H_raw), H_raw, self.mu)   # giá trị thiếu -> trung bình CSDL
        H_n = 2 * (H_fill - self.vmin) / self.rng - 1            # min-max [-1, 1]; không cắt giá trị ngoài khoảng
        E = voice_ecapa.extract_segments(y, bounds, self.device)

        source = "provided"
        if transcript is None:
            transcript, source = self.transcribe(audio_path), "whisper"
        text = content_text.clean_text(transcript)
        T, word_start = content_text.segment_embeddings(text, self.encoder)
        cand = content_text.extract_candidates(text, self.stopwords)
        q_kw = kw.map_query(cand, self.kw_dict, self.encoder)
        return {
            "audio_path": audio_path, "duration_sec": len(y) / sr, "segment_sec": self.segment_sec,
            "segments": [(a / sr, b / sr) for a, b in bounds], "n_voiced_frames": voiced.tolist(),
            "H_raw": H_raw, "H_n": H_n, "E": E,
            "transcript": text, "transcript_source": source, "n_words": len(text.split()),
            "T": T, "word_start": word_start.tolist(),
            "keywords": q_kw, "ner": content_text.extract_ner(text),
        }

    # ------------------------------------------------------------------
    # Bước 2: độ tương đồng với từng file trong CSDL
    # ------------------------------------------------------------------
    def _kw_cosine(self, q_kw: list, iid: str) -> float:
        """Cosine giữa vector TF-IDF từ khóa đại diện của truy vấn và của file trong CSDL.
        Độ dài vector truy vấn chỉ tính trên các từ khóa CÓ trong từ điển chung: từ khóa mới
        (thường là lỗi nhận dạng, df = 0 nên IDF lớn nhất) không khớp file nào, nếu tính vào
        độ dài sẽ kéo S_kw của mọi file xuống một cách khác nhau giữa các truy vấn."""
        d = self.kw_vec.get(iid)
        q_norm = np.sqrt(sum(r["tfidf"] ** 2 for r in q_kw if r["group_id"] is not None))
        if not d or q_norm == 0:
            return 0.0
        dot = sum(r["tfidf"] * d.get(r["group_id"], 0.0) for r in q_kw if r["group_id"] is not None)
        return float(dot / (q_norm * self.kw_norm[iid]))

    def components(self, q: dict) -> dict:
        """Các thành phần độ tương đồng (chưa kết hợp), tính một lần cho mỗi truy vấn:
        S_H(p), S_E(p) theo vị trí cửa sổ; S_T(p); S_kw."""
        comp = {}
        for iid in self.ids:
            c = {"S_kw": self._kw_cosine(q["keywords"], iid)}
            if iid in self.H:
                c["S_H"] = segmenting.sliding_scores(q["H_n"], self.H[iid])
                c["S_E"] = segmenting.sliding_scores(q["E"], self.E[iid])
                c["audio_query_shorter"] = len(q["H_n"]) <= len(self.H[iid])
            if iid in self.T:
                c["S_T"] = segmenting.sliding_scores(q["T"], self.T[iid])
                c["text_query_shorter"] = len(q["T"]) <= len(self.T[iid])
            comp[iid] = c
        return comp

    # ------------------------------------------------------------------
    # Bước 3: kết hợp và xếp hạng
    # ------------------------------------------------------------------
    def rank(self, q: dict, comp: dict, alpha: float = DEFAULT_ALPHA, beta: float = DEFAULT_BETA) -> dict:
        L = self.segment_sec
        spk, con = [], []
        for iid, c in comp.items():
            info = self.items[iid]
            if "S_H" in c:
                s = alpha * c["S_H"] + (1 - alpha) * c["S_E"]
                p = int(np.argmax(s))
                m = min(len(q["H_n"]), len(self.H[iid]))
                win_db = (p * L, (p + m) * L) if c["audio_query_shorter"] else (0.0, m * L)
                win_q = (0.0, m * L) if c["audio_query_shorter"] else (p * L, (p + m) * L)
                spk.append(dict(item_id=iid, score=float(s[p]), S_H=float(c["S_H"][p]), S_E=float(c["S_E"][p]),
                                window_pos=p, n_positions=len(s), window_segments=m,
                                query_shorter=bool(c["audio_query_shorter"]),
                                db_window_sec=win_db, query_window_sec=win_q,
                                channel_name=info["channel_name"], video_title=info["video_title"],
                                chapter_title=info["chapter_title"], audio_path=info["audio_path"]))
            if "S_T" in c:
                p = int(np.argmax(c["S_T"]))
                s_text = float(c["S_T"][p])
                m = min(len(q["T"]), len(self.T[iid]))
                k = config.SEGMENT_SYLLABLES
                win_db = (p * k, (p + m) * k) if c["text_query_shorter"] else (0, m * k)
                win_q = (0, m * k) if c["text_query_shorter"] else (p * k, (p + m) * k)
                con.append(dict(item_id=iid, score=beta * s_text + (1 - beta) * c["S_kw"],
                                S_text=s_text, S_kw=c["S_kw"], window_pos=p, n_positions=len(c["S_T"]),
                                window_chunks=m, query_shorter=bool(c["text_query_shorter"]),
                                db_window_syllables=win_db, query_window_syllables=win_q,
                                channel_name=info["channel_name"], video_title=info["video_title"],
                                chapter_title=info["chapter_title"], audio_path=info["audio_path"]))
        spk.sort(key=lambda r: -r["score"])
        con.sort(key=lambda r: -r["score"])
        for lst in (spk, con):
            for i, r in enumerate(lst, 1):
                r["rank"] = i
        return {"alpha": alpha, "beta": beta, "speaker": spk, "content": con}

    def search(self, audio_path: str, transcript: str = None, alpha: float = DEFAULT_ALPHA,
               beta: float = DEFAULT_BETA, top_k: int = 3) -> tuple:
        q = self.analyze(audio_path, transcript)
        r = self.rank(q, self.components(q), alpha, beta)
        return q, r, {"speaker": r["speaker"][:top_k], "content": r["content"][:top_k]}
