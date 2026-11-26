# Nạp đặc trưng vào CSDL (nội dung 3, ý 2)

PostgreSQL + pgvector (mô hình đối tượng-quan hệ). File âm thanh không nạp vào CSDL; CSDL chỉ lưu đường dẫn.

## 1\. Chuẩn bị

* **PostgreSQL có pgvector đang chạy**, ví dụ bằng Docker:

```bash
  docker run -d --name btl-pg -e POSTGRES\_PASSWORD=btl24 -p 5434:5432 -v btl\_pgdata:/var/lib/postgresql/data pgvector/pgvector:pg17
  ```

* **Thư viện Python:** `pip install "psycopg\[binary]" numpy pandas`.
* **Tải thư mục `features\_seg` từ Drive về máy.** Cần các file sau; **không cần** thư mục `cache/`:

  * `items.csv`, `syllable\_stats.json`, `summary.json`, `metadata\_final.csv`
  * `handcrafted\_segments\_raw.csv`, `handcrafted\_segments\_z.npz`, `handcrafted\_scaler.json`
  * `ecapa\_segments.npz`, `text\_segments.npz`, `ner.json`
  * `keywords/keyword\_dictionary.json`, `keywords/group\_centroids.npy`, `keywords/item\_keywords.json`

## 2\. Nạp

```bash
python load\_db.py --features D:/BTL/features\_seg --metadata D:/BTL/features\_seg/metadata\_final.csv \\
                  --dataset D:/BTL/dataset --dsn postgresql://postgres:btl24@localhost:5434/btl --reset
```

* `--dataset`: tùy chọn. Nếu có, nội dung transcript cũng được lưu vào cột `item.transcript`.
* `--reset`: xóa các bảng cũ rồi nạp lại từ đầu. Chạy lại bao nhiêu lần cũng được.
* Nếu database `btl` chưa có, script tự tạo.
* Cuối cùng script in số bản ghi từng bảng, số chiều vector, dung lượng database.
* `python load\_db.py --print-schema` in câu lệnh tạo bảng để đưa vào báo cáo.

## 3\. Kiểm tra

Mở `sample\_queries.sql` trong TablePlus (kết nối localhost:5434, database `btl`) và chạy từng truy vấn.

