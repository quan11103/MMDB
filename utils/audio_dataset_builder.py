import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


def log_message(log_widget, message):
    log_widget.config(state="normal")
    log_widget.insert(tk.END, message + "\n")
    log_widget.see(tk.END)
    log_widget.config(state="disabled")
    log_widget.update_idletasks()


def find_audio_transcript_pairs(source_dir):
    """Find MP3 + TXT pairs with matching base names recursively."""
    pairs = []
    skipped = []

    for root, _, files in os.walk(source_dir):
        file_map = {name.lower(): name for name in files}

        for filename in files:
            if not filename.lower().endswith(".mp3"):
                continue

            if filename.lower() == "source.mp3":
                skipped.append((os.path.join(root, filename), "source.mp3"))
                continue

            base_name = os.path.splitext(filename)[0]
            txt_filename = base_name + ".txt"
            actual_txt = file_map.get(txt_filename.lower())

            if actual_txt is None:
                skipped.append(
                    (os.path.join(root, filename), "Không có file .txt tương ứng")
                )
                continue

            pairs.append(
                (
                    os.path.join(root, filename),
                    os.path.join(root, actual_txt),
                )
            )

    return pairs, skipped


def get_next_dataset_id(dataset_dir):
    """Get the next numeric dataset folder ID."""
    existing_ids = []

    if not os.path.isdir(dataset_dir):
        return 1

    for name in os.listdir(dataset_dir):
        path = os.path.join(dataset_dir, name)
        if os.path.isdir(path) and name.isdigit():
            existing_ids.append(int(name))

    return max(existing_ids, default=0) + 1


def create_dataset(source_dir, dataset_dir, log_widget):
    if not os.path.isdir(source_dir):
        raise ValueError("Thư mục nguồn không tồn tại.")

    source_abs = os.path.abspath(source_dir)
    dataset_abs = os.path.abspath(dataset_dir)

    if source_abs == dataset_abs:
        raise ValueError("Thư mục nguồn và thư mục dataset phải khác nhau.")

    pairs, skipped = find_audio_transcript_pairs(source_dir)

    if not pairs:
        raise RuntimeError("Không tìm thấy cặp MP3 + TXT hợp lệ.")

    os.makedirs(dataset_dir, exist_ok=True)
    next_id = get_next_dataset_id(dataset_dir)

    copied = 0
    errors = 0

    log_message(log_widget, f"Tìm thấy {len(pairs)} cặp MP3 + TXT.")

    for mp3_path, txt_path in pairs:
        item_id = f"{next_id:03d}"
        item_dir = os.path.join(dataset_dir, item_id)

        try:
            os.makedirs(item_dir, exist_ok=True)

            shutil.copy2(mp3_path, os.path.join(item_dir, "audio.mp3"))
            shutil.copy2(txt_path, os.path.join(item_dir, "transcript.txt"))

            log_message(
                log_widget,
                f"✓ {item_id}: {os.path.basename(mp3_path)}",
            )

            copied += 1
            next_id += 1

        except Exception as e:
            errors += 1
            log_message(log_widget, f"✗ Lỗi: {mp3_path}")
            log_message(log_widget, f"  {e}")

    log_message(log_widget, "")
    log_message(log_widget, "========================================")
    log_message(log_widget, "KẾT QUẢ")
    log_message(log_widget, f"Đã tạo: {copied} dataset items")
    log_message(log_widget, f"Bỏ qua: {len(skipped)} file")
    log_message(log_widget, f"Lỗi: {errors}")
    log_message(log_widget, "========================================")

    if skipped:
        log_message(log_widget, "")
        log_message(log_widget, "Các file bị bỏ qua:")
        for path, reason in skipped:
            log_message(log_widget, f"  - {path}")
            log_message(log_widget, f"    Lý do: {reason}")

    return copied, skipped, errors


class DatasetBuilder:
    def __init__(self, root):
        self.root = root
        root.title("Audio Dataset Builder")
        root.geometry("850x650")

        tk.Label(
            root,
            text="Thư mục dữ liệu nguồn",
            font=("Arial", 11, "bold"),
        ).pack(anchor="w", padx=15, pady=(15, 5))

        source_frame = tk.Frame(root)
        source_frame.pack(fill="x", padx=15)

        self.source_entry = tk.Entry(source_frame, font=("Arial", 10))
        self.source_entry.pack(side="left", fill="x", expand=True)

        tk.Button(
            source_frame,
            text="Chọn",
            command=self.select_source,
        ).pack(side="left", padx=(10, 0))

        tk.Label(
            root,
            text="Thư mục dataset",
            font=("Arial", 11, "bold"),
        ).pack(anchor="w", padx=15, pady=(15, 5))

        dataset_frame = tk.Frame(root)
        dataset_frame.pack(fill="x", padx=15)

        self.dataset_entry = tk.Entry(dataset_frame, font=("Arial", 10))
        self.dataset_entry.pack(side="left", fill="x", expand=True)

        tk.Button(
            dataset_frame,
            text="Chọn",
            command=self.select_dataset,
        ).pack(side="left", padx=(10, 0))

        tk.Label(
            root,
            text=(
                "Chỉ copy các cặp MP3 + TXT cùng tên. "
                "source.mp3 và MP3 không có TXT sẽ bị bỏ qua."
            ),
            font=("Arial", 10),
            anchor="w",
            justify="left",
        ).pack(anchor="w", padx=15, pady=(15, 5))

        tk.Label(
            root,
            text="Log",
            font=("Arial", 11, "bold"),
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.log_widget = scrolledtext.ScrolledText(
            root,
            height=23,
            wrap=tk.WORD,
            state="disabled",
        )
        self.log_widget.pack(fill="both", expand=True, padx=15)

        self.start_button = tk.Button(
            root,
            text="TẠO DATASET",
            font=("Arial", 12, "bold"),
            height=2,
            command=self.start,
        )
        self.start_button.pack(fill="x", padx=15, pady=15)

    def select_source(self):
        folder = filedialog.askdirectory(title="Chọn thư mục dữ liệu nguồn")
        if folder:
            self.source_entry.delete(0, tk.END)
            self.source_entry.insert(0, folder)

    def select_dataset(self):
        folder = filedialog.askdirectory(title="Chọn thư mục dataset")
        if folder:
            self.dataset_entry.delete(0, tk.END)
            self.dataset_entry.insert(0, folder)

    def start(self):
        source_dir = self.source_entry.get().strip()
        dataset_dir = self.dataset_entry.get().strip()

        if not source_dir:
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục nguồn.")
            return

        if not dataset_dir:
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục dataset.")
            return

        self.log_widget.config(state="normal")
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.config(state="disabled")
        self.start_button.config(state="disabled")

        try:
            copied, skipped, errors = create_dataset(
                source_dir,
                dataset_dir,
                self.log_widget,
            )

            messagebox.showinfo(
                "Hoàn thành",
                (
                    f"Đã tạo {copied} dataset items.\n"
                    f"Bỏ qua: {len(skipped)} file.\n"
                    f"Lỗi: {errors}."
                ),
            )
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
        finally:
            self.start_button.config(state="normal")


if __name__ == "__main__":
    root = tk.Tk()
    app = DatasetBuilder(root)
    root.mainloop()
