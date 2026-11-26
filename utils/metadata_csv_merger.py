import csv
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


# ============================================================
# Metadata configuration
# ============================================================

METADATA_FIELDS = [
    "item_id",
    "video_id",
    "video_title",
    "channel_id",
    "channel_name",
    "chapter_index",
    "chapter_title",
    "start_time",
    "end_time",
    "audio_path",
    "transcript_path",
]


# ============================================================
# CSV utilities
# ============================================================

def read_metadata_csv(file_path):
    """
    Đọc metadata.csv và trả về danh sách row.

    Yêu cầu:
    - File phải có đầy đủ đúng 11 cột metadata.
    - Thứ tự cột có thể khác, tool sẽ chuẩn hóa về thứ tự chuẩn.
    - Các giá trị ngoài item_id được giữ nguyên.
    """
    file_path = os.path.abspath(file_path)

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Không tìm thấy file:\n{file_path}")

    try:
        with open(
            file_path,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as f:
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                raise ValueError(
                    f"File không có dòng tiêu đề:\n{file_path}"
                )

            actual_fields = [
                str(field).strip()
                for field in reader.fieldnames
                if field is not None
            ]

            missing_fields = [
                field for field in METADATA_FIELDS
                if field not in actual_fields
            ]

            extra_fields = [
                field for field in actual_fields
                if field not in METADATA_FIELDS
            ]

            if missing_fields or extra_fields:
                details = []

                if missing_fields:
                    details.append(
                        "Thiếu cột: " + ", ".join(missing_fields)
                    )

                if extra_fields:
                    details.append(
                        "Cột không hợp lệ: " + ", ".join(extra_fields)
                    )

                raise ValueError(
                    f"Schema không hợp lệ trong:\n{file_path}\n"
                    + "\n".join(details)
                    + "\n\nSchema yêu cầu:\n"
                    + ", ".join(METADATA_FIELDS)
                )

            rows = []

            for line_number, raw_row in enumerate(
                reader,
                start=2
            ):
                row = {}

                for field in METADATA_FIELDS:
                    value = raw_row.get(field, "")
                    row[field] = "" if value is None else value

                rows.append(row)

            return rows

    except UnicodeDecodeError as e:
        raise ValueError(
            f"Không thể đọc file CSV bằng UTF-8:\n{file_path}\n\n{e}"
        ) from e


def write_merged_csv(output_path, rows):
    """
    Ghi CSV với schema chuẩn và item_id đã được đánh lại.
    """
    output_path = os.path.abspath(output_path)
    output_dir = os.path.dirname(output_path)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(
        output_path,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=METADATA_FIELDS
        )

        writer.writeheader()
        writer.writerows(rows)


def reassign_item_ids(rows):
    """
    Chỉ thay đổi item_id.
    Các trường còn lại giữ nguyên hoàn toàn.
    """
    for index, row in enumerate(rows, start=1):
        row["item_id"] = f"{index:03d}"


def merge_metadata_files(source_file, append_file, output_file):
    """
    Gộp:
        source_file + append_file

    Sau đó đánh lại item_id từ 001.
    """
    source_rows = read_metadata_csv(source_file)
    append_rows = read_metadata_csv(append_file)

    merged_rows = source_rows + append_rows

    reassign_item_ids(merged_rows)
    write_merged_csv(output_file, merged_rows)

    return (
        len(source_rows),
        len(append_rows),
        len(merged_rows),
    )


# ============================================================
# GUI
# ============================================================

class MetadataMerger:
    def __init__(self, root):
        self.root = root

        root.title("Metadata CSV Merger")
        root.geometry("800x620")
        root.minsize(700, 560)

        # ----------------------------------------------------
        # File gốc
        # ----------------------------------------------------

        tk.Label(
            root,
            text="File metadata gốc",
            font=("Arial", 12, "bold")
        ).pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        source_frame = tk.Frame(root)
        source_frame.pack(
            fill="x",
            padx=15
        )

        self.source_entry = tk.Entry(
            source_frame,
            font=("Arial", 11)
        )
        self.source_entry.pack(
            side="left",
            fill="x",
            expand=True
        )

        tk.Button(
            source_frame,
            text="Chọn...",
            command=self.select_source
        ).pack(
            side="left",
            padx=(10, 0)
        )

        # ----------------------------------------------------
        # File cần thêm
        # ----------------------------------------------------

        tk.Label(
            root,
            text="File metadata cần thêm",
            font=("Arial", 12, "bold")
        ).pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        append_frame = tk.Frame(root)
        append_frame.pack(
            fill="x",
            padx=15
        )

        self.append_entry = tk.Entry(
            append_frame,
            font=("Arial", 11)
        )
        self.append_entry.pack(
            side="left",
            fill="x",
            expand=True
        )

        tk.Button(
            append_frame,
            text="Chọn...",
            command=self.select_append
        ).pack(
            side="left",
            padx=(10, 0)
        )

        # ----------------------------------------------------
        # File output
        # ----------------------------------------------------

        tk.Label(
            root,
            text="File metadata sau khi merge",
            font=("Arial", 12, "bold")
        ).pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        output_frame = tk.Frame(root)
        output_frame.pack(
            fill="x",
            padx=15
        )

        self.output_entry = tk.Entry(
            output_frame,
            font=("Arial", 11)
        )
        self.output_entry.pack(
            side="left",
            fill="x",
            expand=True
        )

        tk.Button(
            output_frame,
            text="Chọn...",
            command=self.select_output
        ).pack(
            side="left",
            padx=(10, 0)
        )

        # ----------------------------------------------------
        # Thông tin xử lý
        # ----------------------------------------------------

        info = tk.Label(
            root,
            text=(
                "Tool chỉ thay đổi item_id và giữ nguyên các trường còn lại.\n"
                "Thứ tự dữ liệu: file gốc → file cần thêm."
            ),
            justify="left",
            anchor="w"
        )
        info.pack(
            fill="x",
            padx=15,
            pady=(12, 0)
        )

        # ----------------------------------------------------
        # Log
        # ----------------------------------------------------

        tk.Label(
            root,
            text="Log",
            font=("Arial", 12, "bold")
        ).pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        self.log_text = scrolledtext.ScrolledText(
            root,
            height=18,
            wrap=tk.WORD,
            state="disabled"
        )
        self.log_text.pack(
            fill="both",
            expand=True,
            padx=15
        )

        # ----------------------------------------------------
        # Merge button
        # ----------------------------------------------------

        self.merge_button = tk.Button(
            root,
            text="GỘP METADATA",
            font=("Arial", 12, "bold"),
            height=2,
            command=self.start_merge
        )
        self.merge_button.pack(
            fill="x",
            padx=15,
            pady=15
        )

    # ========================================================
    # File selection
    # ========================================================

    def select_source(self):
        file_path = filedialog.askopenfilename(
            title="Chọn file metadata gốc",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ]
        )

        if not file_path:
            return

        self.source_entry.delete(0, tk.END)
        self.source_entry.insert(0, file_path)

        # Nếu output chưa được chọn, tự đề xuất cạnh file gốc.
        current_output = self.output_entry.get().strip()

        if not current_output:
            source_dir = os.path.dirname(file_path)
            default_output = os.path.join(
                source_dir,
                "metadata_merged.csv"
            )

            self.output_entry.insert(
                0,
                default_output
            )

    def select_append(self):
        file_path = filedialog.askopenfilename(
            title="Chọn file metadata cần thêm",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ]
        )

        if not file_path:
            return

        self.append_entry.delete(0, tk.END)
        self.append_entry.insert(0, file_path)

    def select_output(self):
        file_path = filedialog.asksaveasfilename(
            title="Chọn nơi lưu metadata sau khi merge",
            defaultextension=".csv",
            initialfile="metadata_merged.csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ]
        )

        if not file_path:
            return

        self.output_entry.delete(0, tk.END)
        self.output_entry.insert(0, file_path)

    # ========================================================
    # Log
    # ========================================================

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()

    # ========================================================
    # Merge
    # ========================================================

    def start_merge(self):
        source_file = self.source_entry.get().strip()
        append_file = self.append_entry.get().strip()
        output_file = self.output_entry.get().strip()

        if not source_file:
            messagebox.showerror(
                "Lỗi",
                "Vui lòng chọn file metadata gốc."
            )
            return

        if not append_file:
            messagebox.showerror(
                "Lỗi",
                "Vui lòng chọn file metadata cần thêm."
            )
            return

        if not output_file:
            messagebox.showerror(
                "Lỗi",
                "Vui lòng chọn file output."
            )
            return

        source_abs = os.path.abspath(source_file)
        append_abs = os.path.abspath(append_file)
        output_abs = os.path.abspath(output_file)

        if not os.path.isfile(source_abs):
            messagebox.showerror(
                "Lỗi",
                f"Không tìm thấy file gốc:\n{source_abs}"
            )
            return

        if not os.path.isfile(append_abs):
            messagebox.showerror(
                "Lỗi",
                f"Không tìm thấy file cần thêm:\n{append_abs}"
            )
            return

        # Không cho output trùng với input để tránh ghi đè dữ liệu nguồn.
        if output_abs in {source_abs, append_abs}:
            messagebox.showerror(
                "Lỗi",
                "File output không được trùng với file gốc "
                "hoặc file cần thêm."
            )
            return

        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")

        self.merge_button.config(state="disabled")

        self.log("Bắt đầu merge...")
        self.log(f"File gốc: {source_abs}")
        self.log(f"File cần thêm: {append_abs}")
        self.log(f"Output: {output_abs}")
        self.log("")

        thread = threading.Thread(
            target=self.run_merge,
            args=(
                source_abs,
                append_abs,
                output_abs,
            ),
            daemon=True
        )
        thread.start()

    def run_merge(
        self,
        source_file,
        append_file,
        output_file
    ):
        try:
            source_count, append_count, total_count = (
                merge_metadata_files(
                    source_file,
                    append_file,
                    output_file
                )
            )

            self.log(
                f"✓ File gốc: {source_count} item"
            )
            self.log(
                f"✓ File cần thêm: {append_count} item"
            )
            self.log(
                f"✓ Tổng sau merge: {total_count} item"
            )

            if total_count:
                self.log(
                    f"✓ item_id đã được đánh lại từ "
                    f"001 đến {total_count:03d}"
                )

            self.log("")
            self.log("========================================")
            self.log("✓ MERGE THÀNH CÔNG")
            self.log(f"Output: {output_file}")
            self.log("========================================")

            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Hoàn thành",
                    (
                        "Đã merge metadata.csv thành công.\n\n"
                        f"Tổng số item: {total_count}\n"
                        f"File output:\n{output_file}"
                    )
                )
            )

        except Exception as e:
            self.log("")
            self.log(f"✗ ERROR: {e}")

            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Lỗi",
                    str(e)
                )
            )

        finally:
            self.root.after(
                0,
                lambda: self.merge_button.config(
                    state="normal"
                )
            )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = MetadataMerger(root)
    root.mainloop()
