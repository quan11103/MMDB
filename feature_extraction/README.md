# Trích rút đặc trưng — Nhóm 24

Bộ script trích rút toàn bộ đặc trưng (nội dung 3, ý 1) cho các dataset item trong `metadata.csv`.

Theo yêu cầu của giảng viên, các đặc trưng dạng vector được tính **theo từng đoạn cùng độ dài**,
không gộp thành một vector cho cả file:
- **Độ dài đoạn** = `SEGMENT_SYLLABLES` âm tiết (mặc định 40):
  - audio: 40 × thời lượng trung bình của 1 âm tiết (đo trên chính dataset), làm tròn tới giây
    (`SEGMENT_ROUND_SEC`): 40 × 0,249 s = 9,97 s → 10 s;
  - văn bản: 40 từ (mỗi từ cách nhau bởi khoảng trắng là 1 âm tiết).
- **Áp dụng như nhau** cho file trong CSDL và file truy vấn. Phần dư cuối file ngắn hơn 1 đoạn bị bỏ,
  trừ khi cả file ngắn hơn 1 đoạn.
- **So khớp (nội dung 4):** cửa sổ dài bằng số đoạn của file ngắn hơn, trượt từng đoạn trên file dài hơn
  (`segmenting.sliding_similarity`).
- **Từ khóa và NER** vẫn ở mức file.

| File | Chức năng |
|---|---|
| `config.py` | Toàn bộ tham số đã chốt (sửa ở đây, không sửa trong code) |
| `segmenting.py` | Đo thời lượng âm tiết, chia đoạn audio/văn bản, so khớp bằng cửa sổ trượt |
| `audio_io.py` | Đọc audio bằng FFmpeg → 16 kHz mono float32 |
| `voice_handcrafted.py` | Vector H 126 chiều cho từng đoạn (librosa + parselmouth/Praat) |
| `voice_ecapa.py` | Speaker embedding ECAPA-TDNN cho từng đoạn (SpeechBrain) |
| `content_text.py` | Làm sạch transcript, vector ngữ nghĩa từng chunk, NER, ứng viên từ khóa |
| `keywords.py` | Từ điển từ khóa chung toàn dataset, TF-IDF, ánh xạ file truy vấn |
| `extract_all.py` | Chạy hàng loạt, ghi log, có thể dừng/chạy tiếp |
| `tune_keywords.py` | Thử nhiều ngưỡng gom nhóm từ khóa để chọn bằng thực nghiệm |

## 1. Cài đặt

Nên dùng **môi trường ảo riêng**, không dùng chung với môi trường pyannote. Trên Colab không cần venv và không cài lại torch:
```bash
pip install praat-parselmouth underthesea speechbrain sentence-transformers
```
- Cần có `ffmpeg` và `ffprobe` trong PATH. Colab có sẵn cả hai.
- Lần chạy đầu, SpeechBrain và Sentence Transformers tự tải model từ Hugging Face.

## 2. Chạy

```bash
python extract_all.py --metadata <...>/metadata_final.csv --root <thư mục dataset> --out features_seg
```
Mặc định chạy đủ 6 bước:

| Bước | Làm gì |
|---|---|
| `syllable` | Đo thời lượng TB 1 âm tiết = tổng thời lượng / tổng số âm tiết của **toàn bộ metadata**, rồi ghi `syllable_stats.json` (độ dài đoạn). Mất khoảng 1–2 phút |
| `handcrafted` | Vector H của từng đoạn audio |
| `ecapa` | Embedding ECAPA của từng đoạn audio |
| `text` | Vector ngữ nghĩa của từng chunk; NER và ứng viên từ khóa ở mức file |
| `keywords` | Từ điển từ khóa chung, TF-IDF |
| `aggregate` | Gộp kết quả, chuẩn hóa min-max [-1, 1] vector H (fit trên mọi đoạn), ghi `summary.json` |

- Kết quả từng item được lưu ngay vào `cache/`. Chạy lại đúng lệnh thì item đã xong được bỏ qua.
- `--force` tính lại tất cả; `--ids 001,045` chạy riêng vài item; `--limit 3` chạy thử 3 item. Bước `syllable` vẫn đo trên toàn bộ metadata.
- **Đổi độ dài đoạn** (`SEGMENT_SYLLABLES` hoặc `SEGMENT_ROUND_SEC`): chạy lại `syllable,handcrafted,ecapa,aggregate`.
  Kết quả audio tính với độ dài đoạn khác được tự nhận ra và tính lại; bước aggregate từ chối gộp nếu còn lẫn kết quả cũ.

### Chuyển từ bản cũ (vector toàn file) sang bản mới
Dùng thư mục kết quả **mới** (`features_seg`) để không lẫn với kết quả cũ. NER và ứng viên từ khóa không đổi,
nên có thể chép lại để khỏi tính lại:
```bash
mkdir -p features_seg/cache && cp -r features/cache/text features_seg/cache/text
```
Bước `text` khi đó chỉ tính vector ngữ nghĩa từng chunk.

### Chọn ngưỡng từ khóa
```bash
python tune_keywords.py --out features_seg --metadata <...>/metadata_final.csv --linkage complete --thresholds 0.85,0.90
```
Ngưỡng mặc định hiện là 0,90 với complete linkage, đã chọn bằng thực nghiệm.

## 3. Kết quả (thư mục `--out`)

| File | Nội dung |
|---|---|
| `syllable_stats.json` | Thời lượng TB 1 âm tiết, tốc độ nói (trung vị, min, max), độ dài đoạn (giây) |
| `items.csv` | Mỗi item: thời lượng, số âm tiết, số đoạn audio, số chunk văn bản |
| `handcrafted_segments_raw.csv` | Mỗi đoạn: item_id, seg_index, start_sec, end_sec, số khung hữu thanh, 126 đặc trưng thô |
| `handcrafted_segments_norm.npz` | `item_id`, `seg_index`, `X` (số đoạn × 126): vector H đã chuẩn hóa min-max [-1, 1] |
| `handcrafted_scaler.json` | Tên đặc trưng, mean, min, max (fit trên mọi đoạn; dùng để chuẩn hóa file truy vấn) |
| `ecapa_segments.npz` | `item_id`, `seg_index`, `X` (số đoạn × 192), mỗi hàng đã chuẩn hóa L2 |
| `text_segments.npz` | `item_id`, `seg_index`, `word_start`, `X` (số chunk × 768), mỗi hàng đã chuẩn hóa L2 |
| `ner.json` | {item_id: [{text, label, count}]} (mức file) |
| `keywords/…` | Từ điển từ khóa, centroid các nhóm, từ khóa + TF-IDF từng file (mức file) |
| `extraction_log.csv`, `summary.json` | Log và thống kê |

Đoạn audio thứ k của một file có cùng `seg_index` trong `handcrafted_segments_*` và `ecapa_segments`.
Chunk văn bản đánh số riêng, vì số đoạn audio và số chunk văn bản của một file không nhất thiết bằng nhau.

## 4. Dùng cho file truy vấn (nội dung 4)

```python
import audio_io, segmenting, voice_handcrafted as vh, voice_ecapa, content_text
seg_sec = segmenting.load_segment_sec("features_seg")          # cùng độ dài đoạn với CSDL
y = audio_io.load_audio("query.mp3")
bounds = segmenting.audio_bounds(len(y), seg_sec)
H_q, _ = vh.extract_segments(y, bounds)                       # rồi chuẩn hóa bằng handcrafted_scaler.json
E_q = voice_ecapa.extract_segments(y, bounds)
T_q, _ = content_text.segment_embeddings(transcript_whisper, encoder)
score, pos = segmenting.sliding_similarity(T_q, T_db_item)    # điểm + vị trí cửa sổ tốt nhất
```
Kết hợp hai nhánh giọng nói tại cùng vị trí cửa sổ:
`S(p) = α · sliding_scores(H_q, H_d) + (1 − α) · sliding_scores(E_q, E_d)`, sau đó lấy max theo p.

## 5. Những điểm cần cập nhật vào báo cáo cho khớp với code

- **ZCR:** `N_changes / (N − 1)`.
- **F0:** autocorrelation của Praat (`To Pitch (ac)`), 75–500 Hz.
- **HNR:** tương quan chéo của Praat (`To Harmonicity (cc)`), không phải phương pháp phổ.
- **Formant:** Praat `To Formant (burg)`, 5 formant, tối đa 5500 Hz, lấy tại khung hữu thanh.
- **Delta:** N = 2, khung biên được lặp lại.
- **Đặc trưng theo đoạn:** H, ECAPA và vector ngữ nghĩa được tính cho từng đoạn 40 âm tiết. Không còn mean pooling cho cả file. Silence Ratio dùng RMS lớn nhất của đoạn.
- **Từ khóa:**
  - từ dừng (khoảng 1.970 từ), giữ từ viết tắt viết hoa;
  - nhận diện từ nước ngoài theo cấu trúc âm tiết;
  - complete linkage, ngưỡng 0,90;
  - quy tắc từ một âm tiết;
  - từ đại diện = tần suất cao nhất toàn CSDL.

## 6. Hạn chế đã biết

- **Chữ thường, không dấu câu:** phụ đề tự động thường viết thường và không có dấu câu, nên NER nhận diện được ít thực thể.
- **Nhạc nền:** ảnh hưởng tới đặc trưng thủ công và ECAPA.
- **Đoạn không có giọng nói:** một đoạn chỉ có nhạc sẽ không có khung hữu thanh. Khi đó F0 và Formant của đoạn bị thiếu (NaN), và được thay bằng trung bình cột trước khi chuẩn hóa. Số giá trị bị thay ghi trong `summary.json`.
- **Phần dư bị bỏ:** phần dư cuối file ngắn hơn 1 đoạn (dưới khoảng 10 s) không được dùng.
