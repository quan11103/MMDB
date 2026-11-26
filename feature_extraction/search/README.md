# Hệ thống tìm kiếm âm thanh (nội dung 4)

Đầu vào: một file âm thanh mới. Đầu ra: **3 file có nội dung giống nhất** và **3 file có giọng nói giống nhất**,
xếp giảm dần theo độ tương đồng. Dữ liệu đọc từ CSDL PostgreSQL đã nạp ở ý 2.

## Cách tính độ tương đồng
1. **Trích rút đặc trưng file truy vấn** bằng đúng các hàm đã dùng cho CSDL:
   - audio: đoạn 10 s, vector H (chuẩn hóa min-max [-1, 1] bằng min, max lưu trong bảng `feature_def`) và ECAPA;
   - văn bản: transcript từ Whisper small, chunk 40 âm tiết, vector ngữ nghĩa; ứng viên từ khóa được ánh xạ vào từ điển chung.
2. **So khớp bằng cửa sổ trượt** với từng file trong CSDL. Cửa sổ dài bằng file ngắn hơn, trượt từng đoạn trên file dài hơn:
   - **Giọng nói:** S_spk(p) = α·S_H(p) + (1 − α)·S_E(p), sau đó S_speaker = max theo p.
   - **Nội dung:** S_content = β·S_text + (1 − β)·S_kw, trong đó:
     - S_text = max theo p của cửa sổ trượt trên vector ngữ nghĩa;
     - S_kw = cosine giữa hai vector TF-IDF từ khóa đại diện.
3. **Xếp hạng**, lấy top 3 mỗi loại.

α và β chọn bằng `evaluate.py`. Giá trị mặc định (α = 0,5; β = 0,7) chỉ là tạm thời.

## Cài đặt (trên máy chạy CSDL)
```bash
pip install "psycopg[binary]" numpy pandas librosa praat-parselmouth underthesea torch torchaudio speechbrain sentence-transformers openai-whisper
```
- **ffmpeg** phải có trong PATH. Trên Windows: tải ffmpeg, giải nén, thêm thư mục `bin` vào PATH, rồi kiểm tra bằng `ffmpeg -version`.
- **Lần chạy đầu** tự tải các model: ECAPA khoảng 80 MB, Sentence Transformer khoảng 1 GB, Whisper small khoảng 460 MB.
- **Chạy trên CPU:** một truy vấn dài 1–3 phút mất khoảng vài chục giây đến vài phút, phần lớn thời gian là Whisper.

## Tìm kiếm một file
```bash
cd search
python search_cli.py D:/BTL/queries/q01.mp3 --dsn postgresql://postgres:btl24@localhost:5434/btl --out ket_qua/q01
```
- `--transcript q01.txt`: dùng transcript có sẵn thay cho Whisper.
- `--alpha`, `--beta`: trọng số kết hợp.
- `--out`: thư mục lưu kết quả trung gian (mục 4b):

| File | Nội dung |
|---|---|
| `query_info.json` | Thời lượng, các đoạn, transcript, từ khóa đại diện, thực thể |
| `query_features.csv` | 126 đặc trưng thô và đã chuẩn hóa của từng đoạn 10 s |
| `ranking_speaker.csv` | 20 file đầu theo giọng nói: S_H, S_E, S_speaker, vị trí cửa sổ, đoạn khớp |
| `ranking_content.csv` | 20 file đầu theo nội dung: S_text, S_kw, S_content, vị trí cửa sổ |
| `result.json` | Top 3 mỗi loại |

## Đánh giá và chọn α, β (mục 4c)
Lập `queries.csv` theo mẫu `queries_template.csv`. File truy vấn **không được nằm trong CSDL**.

| type | Ý nghĩa | Cột cần điền |
|---|---|---|
| A | Giọng đã có, nội dung đã có (chapter ngoài CSDL của một video có chapter trong CSDL) | video_id |
| B | Giọng đã có, nội dung chưa có (video mới cùng kênh) | channel_id |
| C | Giọng chưa có, nội dung đã có (thành viên thu âm lại nội dung một file trong CSDL) | video_id, source_item_id |

```bash
python evaluate.py --queries queries.csv --dsn postgresql://postgres:btl24@localhost:5434/btl --out danh_gia
```
- **`--topics topics.csv`** (tùy chọn, các cột `video_id,topic` cho các video trong CSDL): thêm đánh giá nội dung theo chủ đề.
- **Đáp án đúng:**
  - giọng nói: cùng kênh, tức cùng người nói; cần kiểm tra mỗi kênh trong dataset chỉ có một người nói;
  - nội dung: cùng video (chặt) hoặc cùng chủ đề (lỏng).
- **Độ đo:** P@3, Hit@3, MRR. Với các phần "chưa có", tức giọng của C và nội dung của B, không có đáp án đúng; script ghi điểm top-1 để so với các truy vấn "đã có".
- **Kết quả:**
  - `grid_speaker.csv`, `grid_content.csv`: độ đo theo từng α, β;
  - `details.csv`: top 3 của từng truy vấn với α, β tốt nhất.
- **Cache:** đặc trưng của mỗi truy vấn được lưu trong `danh_gia/cache/`, chạy lại không phải trích rút lại. Thêm truy vấn mới vào `queries.csv` rồi chạy lại là được.
- **Lưu ý:** α, β được chọn trên chính bộ truy vấn, nên kết quả tại α, β tốt nhất là ước lượng lạc quan. Cần ghi rõ điều này trong báo cáo.
