# Nạp đặc trưng vào CSDL (nội dung 3, ý 2)

PostgreSQL + pgvector (mô hình đối tượng-quan hệ). File âm thanh không nạp vào CSDL; CSDL chỉ lưu đường dẫn.

## 1. Chuẩn bị
- **PostgreSQL có pgvector đang chạy**, ví dụ bằng Docker:
  ```bash
  docker run -d --name btl-pg -e POSTGRES_PASSWORD=btl24 -p 5432:5432 -v btl_pgdata:/var/lib/postgresql/data pgvector/pgvector:pg17
  ```
- **Thư viện Python:** `pip install "psycopg[binary]" numpy pandas`.
- **Tải thư mục `features_seg` từ Drive về máy.** Cần các file sau; **không cần** thư mục `cache/`:
  - `items.csv`, `syllable_stats.json`, `summary.json`, `metadata_final.csv`
  - `handcrafted_segments_raw.csv`, `handcrafted_segments_z.npz`, `handcrafted_scaler.json`
  - `ecapa_segments.npz`, `text_segments.npz`, `ner.json`
  - `keywords/keyword_dictionary.json`, `keywords/group_centroids.npy`, `keywords/item_keywords.json`

## 2. Nạp
```bash
python load_db.py --features D:/BTL/features_seg --metadata D:/BTL/features_seg/metadata_final.csv \
                  --dataset D:/BTL/dataset --dsn postgresql://postgres:btl24@localhost:5432/btl --reset
```
- `--dataset`: tùy chọn. Nếu có, nội dung transcript cũng được lưu vào cột `item.transcript`.
- `--reset`: xóa các bảng cũ rồi nạp lại từ đầu. Chạy lại bao nhiêu lần cũng được.
- Nếu database `btl` chưa có, script tự tạo.
- Cuối cùng script in số bản ghi từng bảng, số chiều vector, dung lượng database.
- `python load_db.py --print-schema` in câu lệnh tạo bảng để đưa vào báo cáo.

## 3. Kiểm tra
Mở `sample_queries.sql` trong TablePlus (kết nối localhost:5432, database `btl`) và chạy từng truy vấn.
