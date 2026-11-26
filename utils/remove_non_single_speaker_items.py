import os
import csv
import unicodedata
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path


def normalize_path(path):
    """
    Chuẩn hóa path để xử lý tên tiếng Việt Unicode:
    - NFC: ghép các ký tự Unicode tổ hợp về dạng chuẩn.
    - / thay cho \\.
    - casefold để không phân biệt hoa/thường.
    """
    path = unicodedata.normalize("NFC", str(path))
    path = path.replace("\\", "/")
    parts = [unicodedata.normalize("NFC", p).casefold()
             for p in path.split("/") if p]
    return "/".join(parts)


def format_size(size):
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size)

    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024


def scan_dataset(dataset_dir):
    """
    Quét toàn bộ dataset giống tool MP3 analyzer:
    - os.walk đệ quy
    - bỏ qua source.mp3
    - lập index theo relative path đã normalize
    """
    index = {}

    for root, dirs, files in os.walk(dataset_dir):
        for file_name in files:
            if file_name.lower() == "source.mp3":
                continue

            full_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(full_path, dataset_dir)

            key = normalize_path(relative_path)
            index[key] = full_path

    return index


def load_csv(csv_path):
    rows = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("CSV không có header.")

        required = {"relative_path", "status", "classification"}

        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(
                "CSV thiếu cột: " + ", ".join(sorted(missing))
            )

        for row in reader:
            rows.append(row)

    return rows


def is_one_speaker(row):
    """
    Chỉ giữ đúng các record:
      status = OK
      classification = 1 speaker

    Mọi classification khác 1 speaker sẽ là target xóa.
    """
    status = (row.get("status") or "").strip().casefold()
    classification = (row.get("classification") or "").strip().casefold()

    return status == "ok" and classification == "1 speaker"


def get_target_rows(rows):
    targets = []
    ignored_non_ok = 0

    for row in rows:
        status = (row.get("status") or "").strip().casefold()

        if status != "ok":
            ignored_non_ok += 1
            continue

        if not is_one_speaker(row):
            targets.append(row)

    return targets, ignored_non_ok


def resolve_dataset_file(file_index, relative_path):
    """
    Ghép CSV relative_path với file thực tế trong dataset.

    Quan trọng:
    Không dùng os.path.exists(dataset_dir + relative_path) trực tiếp
    vì tên tiếng Việt trong CSV có thể khác Unicode normalization.
    """
    key = normalize_path(relative_path)
    return file_index.get(key)


def get_companion_txt(mp3_path):
    """
    Transcript có cùng basename với MP3.
    Ví dụ:
      01 - Intro.mp3
      01 - Intro.txt
    """
    return os.path.splitext(mp3_path)[0] + ".txt"


def analyze(csv_path, dataset_dir):
    rows = load_csv(csv_path)

    targets, ignored_non_ok = get_target_rows(rows)

    file_index = scan_dataset(dataset_dir)

    mp3_found = []
    mp3_missing = []
    txt_missing = []

    total_size = 0
    items = []

    for row in targets:
        relative_path = (row.get("relative_path") or "").strip()

        mp3_path = resolve_dataset_file(file_index, relative_path)

        if not mp3_path or not mp3_path.lower().endswith(".mp3"):
            mp3_missing.append(relative_path)
            continue

        txt_path = get_companion_txt(mp3_path)

        mp3_size = os.path.getsize(mp3_path)

        mp3_found.append(mp3_path)
        total_size += mp3_size

        if os.path.isfile(txt_path):
            txt_size = os.path.getsize(txt_path)
            total_size += txt_size
        else:
            txt_missing.append(txt_path)

        items.append({
            "relative_path": relative_path,
            "mp3_path": mp3_path,
            "txt_path": txt_path,
            "mp3_size": mp3_size,
        })

    return {
        "rows": rows,
        "targets": targets,
        "ignored_non_ok": ignored_non_ok,
        "items": items,
        "mp3_found": mp3_found,
        "mp3_missing": mp3_missing,
        "txt_missing": txt_missing,
        "total_size": total_size,
        "file_index_count": len(file_index),
    }


def delete_items(result):
    deleted = []
    failed = []

    for item in result["items"]:
        mp3_path = item["mp3_path"]
        txt_path = item["txt_path"]

        # Xóa MP3
        try:
            if os.path.isfile(mp3_path):
                os.remove(mp3_path)
                deleted.append(mp3_path)
        except Exception as e:
            failed.append((mp3_path, str(e)))

        # Xóa TXT nếu tồn tại
        try:
            if os.path.isfile(txt_path):
                os.remove(txt_path)
                deleted.append(txt_path)
        except Exception as e:
            failed.append((txt_path, str(e)))

    return deleted, failed


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Xóa Dataset không phải 1 Speaker")
        self.root.geometry("1000x720")
        self.root.minsize(850, 600)

        self.csv_path = ""
        self.dataset_dir = ""
        self.result = None

        self.create_ui()

    def create_ui(self):
        title = tk.Label(
            self.root,
            text="Xóa Dataset không phải 1 Speaker",
            font=("Arial", 18, "bold")
        )
        title.pack(pady=(18, 8))

        info = tk.Label(
            self.root,
            text=(
                "Đọc speaker_counts.csv → giữ classification = "
                "'1 speaker' → xóa MP3 + TXT của các item còn lại"
            ),
            font=("Arial", 10)
        )
        info.pack(pady=(0, 15))

        frame = tk.Frame(self.root)
        frame.pack(fill="x", padx=25)

        # CSV
        tk.Label(frame, text="CSV kết quả:", font=("Arial", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=6
        )

        self.csv_label = tk.Label(
            frame,
            text="Chưa chọn",
            anchor="w"
        )
        self.csv_label.grid(row=0, column=1, sticky="ew", padx=10)

        tk.Button(
            frame,
            text="CHỌN CSV",
            command=self.choose_csv,
            width=15
        ).grid(row=0, column=2)

        # Dataset
        tk.Label(frame, text="Dataset:", font=("Arial", 10, "bold")).grid(
            row=1, column=0, sticky="w", pady=6
        )

        self.dataset_label = tk.Label(
            frame,
            text="Chưa chọn",
            anchor="w"
        )
        self.dataset_label.grid(row=1, column=1, sticky="ew", padx=10)

        tk.Button(
            frame,
            text="CHỌN DATASET",
            command=self.choose_dataset,
            width=15
        ).grid(row=1, column=2)

        frame.columnconfigure(1, weight=1)

        tk.Button(
            self.root,
            text="PHÂN TÍCH",
            font=("Arial", 11, "bold"),
            command=self.run_analysis,
            width=22,
            height=2
        ).pack(pady=15)

        # Summary
        summary = tk.LabelFrame(
            self.root,
            text="Kết quả",
            font=("Arial", 11, "bold")
        )
        summary.pack(fill="x", padx=25, pady=5)

        self.labels = {}

        names = [
            ("csv_rows", "CSV rows"),
            ("target_rows", "Target rows (không phải 1 speaker)"),
            ("ignored", "Ignored non-OK rows"),
            ("index", "File thực tế được quét"),
            ("mp3_found", "MP3 tìm thấy"),
            ("mp3_missing", "MP3 không tìm thấy"),
            ("txt_missing", "TXT không tìm thấy"),
            ("size", "Dung lượng sẽ xóa"),
        ]

        for i, (key, label) in enumerate(names):
            lbl = tk.Label(
                summary,
                text=f"{label}: 0",
                font=("Arial", 10),
                anchor="w"
            )
            lbl.grid(row=i // 2, column=i % 2, sticky="w", padx=20, pady=5)
            self.labels[key] = lbl

        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)

        # List
        list_frame = tk.LabelFrame(
            self.root,
            text="Danh sách MP3 không tìm thấy / file sẽ xóa",
            font=("Arial", 10, "bold")
        )
        list_frame.pack(fill="both", expand=True, padx=25, pady=10)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 9)
        )
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar.config(command=self.listbox.yview)

        self.delete_button = tk.Button(
            self.root,
            text="XÓA CÁC ITEM KHÔNG PHẢI 1 SPEAKER",
            font=("Arial", 11, "bold"),
            state="disabled",
            command=self.confirm_delete,
            width=36,
            height=2
        )
        self.delete_button.pack(pady=(0, 20))

    def choose_csv(self):
        path = filedialog.askopenfilename(
            title="Chọn speaker_counts.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not path:
            return

        self.csv_path = path
        self.csv_label.config(text=path)

    def choose_dataset(self):
        path = filedialog.askdirectory(
            title="Chọn thư mục gốc Dataset"
        )

        if not path:
            return

        self.dataset_dir = path
        self.dataset_label.config(text=path)

    def run_analysis(self):
        if not self.csv_path:
            messagebox.showwarning("Thiếu CSV", "Hãy chọn speaker_counts.csv.")
            return

        if not self.dataset_dir:
            messagebox.showwarning("Thiếu Dataset", "Hãy chọn thư mục Dataset.")
            return

        try:
            self.listbox.delete(0, tk.END)

            self.result = analyze(
                self.csv_path,
                self.dataset_dir
            )

            r = self.result

            self.labels["csv_rows"].config(
                text=f"CSV rows: {len(r['rows'])}"
            )
            self.labels["target_rows"].config(
                text=f"Target rows (không phải 1 speaker): {len(r['targets'])}"
            )
            self.labels["ignored"].config(
                text=f"Ignored non-OK rows: {r['ignored_non_ok']}"
            )
            self.labels["index"].config(
                text=f"File thực tế được quét: {r['file_index_count']}"
            )
            self.labels["mp3_found"].config(
                text=f"MP3 tìm thấy: {len(r['mp3_found'])}"
            )
            self.labels["mp3_missing"].config(
                text=f"MP3 không tìm thấy: {len(r['mp3_missing'])}"
            )
            self.labels["txt_missing"].config(
                text=f"TXT không tìm thấy: {len(r['txt_missing'])}"
            )
            self.labels["size"].config(
                text=f"Dung lượng sẽ xóa: {format_size(r['total_size'])}"
            )

            # Hiển thị các file không tìm thấy
            if r["mp3_missing"]:
                self.listbox.insert(
                    tk.END,
                    "=== MP3 KHÔNG TÌM THẤY ==="
                )

                for path in r["mp3_missing"]:
                    self.listbox.insert(tk.END, path)

            if r["items"]:
                self.listbox.insert(
                    tk.END,
                    ""
                )
                self.listbox.insert(
                    tk.END,
                    "=== ITEM SẼ XÓA ==="
                )

                for item in r["items"]:
                    self.listbox.insert(
                        tk.END,
                        item["relative_path"]
                    )

            self.delete_button.config(
                state="normal" if r["items"] else "disabled"
            )

        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def confirm_delete(self):
        if not self.result or not self.result["items"]:
            return

        count = len(self.result["items"])
        size = format_size(self.result["total_size"])

        answer = messagebox.askyesno(
            "Xác nhận xóa",
            (
                f"Sẽ xóa {count} dataset item.\n\n"
                f"Mỗi item gồm MP3 + TXT nếu file tồn tại.\n"
                f"Dung lượng: {size}\n\n"
                "source.mp3 sẽ KHÔNG bị xóa.\n\n"
                "Bạn có chắc chắn muốn tiếp tục?"
            )
        )

        if not answer:
            return

        try:
            deleted, failed = delete_items(self.result)

            # Report
            report_path = os.path.join(
                self.dataset_dir,
                "deleted_non_single_speaker_report.txt"
            )

            with open(report_path, "w", encoding="utf-8") as f:
                f.write("DELETE NON-SINGLE-SPEAKER DATASET REPORT\n")
                f.write("=" * 60 + "\n\n")

                f.write(f"CSV: {self.csv_path}\n")
                f.write(f"Dataset: {self.dataset_dir}\n")
                f.write(f"Target items: {len(self.result['items'])}\n")
                f.write(f"Deleted files: {len(deleted)}\n")
                f.write(f"Failed files: {len(failed)}\n\n")

                f.write("DELETED:\n")
                for path in deleted:
                    f.write(path + "\n")

                f.write("\nFAILED:\n")
                for path, error in failed:
                    f.write(f"{path} | {error}\n")

            messagebox.showinfo(
                "Hoàn tất",
                (
                    f"Đã xóa xong.\n\n"
                    f"Dataset item: {count}\n"
                    f"File đã xóa: {len(deleted)}\n"
                    f"File lỗi: {len(failed)}\n\n"
                    f"Report:\n{report_path}"
                )
            )

            self.run_analysis()

        except Exception as e:
            messagebox.showerror("Lỗi khi xóa", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
