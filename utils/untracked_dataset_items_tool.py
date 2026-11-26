import csv
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from typing import Optional


AUDIO_EXTENSION = ".mp3"
TRANSCRIPT_EXTENSION = ".txt"
REQUIRED_METADATA_FIELDS = {"audio_path", "transcript_path"}


@dataclass
class DatasetItem:
    key: str
    name: str
    folder: str
    audio_path: Optional[str] = None
    transcript_path: Optional[str] = None


def normalized_path(path: str) -> str:
    """Return a normalized absolute path suitable for path comparisons."""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def resolve_metadata_path(path_value: str, base_folder: str) -> Optional[str]:
    """Resolve absolute/relative paths using the selected dataset root as base."""
    if not path_value or not path_value.strip():
        return None

    value = path_value.strip().strip('"').strip("'")
    value = value.replace("/", os.sep).replace("\\", os.sep)

    if os.path.isabs(value):
        return os.path.normpath(value)
    return os.path.normpath(os.path.join(base_folder, value))


def read_metadata_references(csv_path: str, base_folder: str):
    """Read all audio_path/transcript_path references from metadata.csv."""
    audio_refs = set()
    transcript_refs = set()

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError("metadata.csv không có dòng tiêu đề (header).")

        missing = REQUIRED_METADATA_FIELDS.difference(reader.fieldnames)
        if missing:
            raise ValueError(
                "metadata.csv thiếu cột bắt buộc: " + ", ".join(sorted(missing))
            )

        for row in reader:
            audio_path = resolve_metadata_path(row.get("audio_path", ""), base_folder)
            transcript_path = resolve_metadata_path(
                row.get("transcript_path", ""), base_folder
            )
            if audio_path:
                audio_refs.add(normalized_path(audio_path))
            if transcript_path:
                transcript_refs.add(normalized_path(transcript_path))

    return audio_refs, transcript_refs


def is_source_or_auxiliary_file(filename: str) -> bool:
    """Exclude the full source audio and full-source transcript from chapter items."""
    stem = os.path.splitext(filename)[0].casefold()
    return stem == "source" or stem.startswith("source.") or stem.startswith("source_")


def scan_dataset_items(dataset_root: str):
    """Group chapter MP3/TXT files by folder and shared filename stem."""
    items = {}

    for current_folder, dirs, filenames in os.walk(dataset_root):
        # Ignore common temporary/system folders if present.
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", ".venv", "venv"}]

        for filename in filenames:
            extension = os.path.splitext(filename)[1].casefold()
            if extension not in {AUDIO_EXTENSION, TRANSCRIPT_EXTENSION}:
                continue
            if is_source_or_auxiliary_file(filename):
                continue

            full_path = os.path.normpath(os.path.join(current_folder, filename))
            stem = os.path.splitext(filename)[0]
            key = normalized_path(os.path.join(current_folder, stem))

            item = items.get(key)
            if item is None:
                item = DatasetItem(
                    key=key,
                    name=stem,
                    folder=os.path.normpath(current_folder),
                )
                items[key] = item

            if extension == AUDIO_EXTENSION:
                item.audio_path = full_path
            elif extension == TRANSCRIPT_EXTENSION:
                item.transcript_path = full_path

    return sorted(items.values(), key=lambda item: (item.folder.casefold(), item.name.casefold()))


def find_untracked_items(dataset_root: str, csv_path: str):
    """Return items not referenced by either path column and partial references."""
    audio_refs, transcript_refs = read_metadata_references(csv_path, dataset_root)
    items = scan_dataset_items(dataset_root)
    untracked = []
    partially_referenced = []

    for item in items:
        audio_referenced = bool(
            item.audio_path and normalized_path(item.audio_path) in audio_refs
        )
        transcript_referenced = bool(
            item.transcript_path
            and normalized_path(item.transcript_path) in transcript_refs
        )

        if not audio_referenced and not transcript_referenced:
            untracked.append(item)
        elif audio_referenced != transcript_referenced:
            partially_referenced.append(item)

    return untracked, partially_referenced, len(items)


class UntrackedDatasetTool:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Dataset Item Checker - Metadata")
        self.root.geometry("1180x720")
        self.root.minsize(900, 550)

        self.metadata_var = tk.StringVar()
        self.dataset_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Chọn metadata.csv và thư mục gốc dataset.")
        self.items_by_iid = {}
        self.last_partial_count = 0
        self.last_dataset_count = 0

        self._build_ui()

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            outer,
            text="LIỆT KÊ DATASET ITEM KHÔNG CÓ TRONG METADATA",
            font=("Arial", 15, "bold"),
        ).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            outer,
            text=(
                "Đối chiếu theo đường dẫn audio_path/transcript_path. "
                "Bỏ qua source.mp3 và transcript của file nguồn."
            ),
            wraplength=1080,
        ).pack(anchor="w", pady=(0, 14))

        self._path_row(outer, "metadata.csv:", self.metadata_var, self.choose_metadata)
        self._path_row(outer, "Thư mục dataset:", self.dataset_var, self.choose_dataset)

        action_frame = ttk.Frame(outer)
        action_frame.pack(fill=tk.X, pady=(10, 8))
        ttk.Button(action_frame, text="KIỂM TRA", command=self.scan).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="Chọn tất cả", command=self.select_all).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(action_frame, text="Bỏ chọn", command=self.clear_selection).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self.delete_button = ttk.Button(
            action_frame, text="XÓA ITEM ĐÃ CHỌN", command=self.delete_selected, state=tk.DISABLED
        )
        self.delete_button.pack(side=tk.RIGHT)

        table_frame = ttk.Frame(outer)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "folder", "audio", "transcript")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("name", text="Dataset item")
        self.tree.heading("folder", text="Thư mục")
        self.tree.heading("audio", text="Audio (.mp3)")
        self.tree.heading("transcript", text="Transcript (.txt)")

        self.tree.column("name", width=250, minwidth=140, anchor="w")
        self.tree.column("folder", width=380, minwidth=180, anchor="w")
        self.tree.column("audio", width=190, minwidth=100, anchor="center")
        self.tree.column("transcript", width=190, minwidth=100, anchor="center")

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        ttk.Label(
            outer,
            textvariable=self.status_var,
            wraplength=1080,
            foreground="#234f73",
        ).pack(anchor="w", pady=(9, 0))

    def _path_row(self, parent, label, variable, command):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=4)
        ttk.Label(frame, text=label, width=17).pack(side=tk.LEFT)
        ttk.Entry(frame, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(frame, text="Chọn...", command=command, width=12).pack(side=tk.RIGHT)

    def choose_metadata(self):
        path = filedialog.askopenfilename(
            title="Chọn metadata.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.metadata_var.set(path)
            if not self.dataset_var.get().strip():
                self.dataset_var.set(os.path.dirname(path))
            self.status_var.set("Đã chọn metadata.csv. Hãy chọn đúng thư mục gốc dataset rồi kiểm tra.")

    def choose_dataset(self):
        path = filedialog.askdirectory(title="Chọn thư mục gốc dataset")
        if path:
            self.dataset_var.set(path)

    def scan(self):
        csv_path = self.metadata_var.get().strip()
        dataset_root = self.dataset_var.get().strip()

        if not csv_path or not os.path.isfile(csv_path):
            messagebox.showwarning("Thiếu metadata", "Hãy chọn một file metadata.csv hợp lệ.")
            return
        if not dataset_root or not os.path.isdir(dataset_root):
            messagebox.showwarning("Thiếu dataset", "Hãy chọn thư mục gốc dataset hợp lệ.")
            return

        try:
            untracked, partial, total_count = find_untracked_items(dataset_root, csv_path)
        except Exception as exc:
            messagebox.showerror("Không thể kiểm tra", str(exc))
            return

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.items_by_iid.clear()

        for index, item in enumerate(untracked):
            iid = f"item_{index}"
            audio_label = os.path.basename(item.audio_path) if item.audio_path else "KHÔNG CÓ"
            txt_label = os.path.basename(item.transcript_path) if item.transcript_path else "KHÔNG CÓ"
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(item.name, item.folder, audio_label, txt_label),
            )
            self.items_by_iid[iid] = item

        self.last_partial_count = len(partial)
        self.last_dataset_count = total_count
        self.delete_button.configure(state=tk.NORMAL if untracked else tk.DISABLED)

        message = (
            f"Đã quét {total_count} item. Không được metadata tham chiếu: {len(untracked)} item."
        )
        if partial:
            message += (
                f" Có {len(partial)} item chỉ được tham chiếu một phần "
                "(chỉ audio hoặc chỉ transcript); các item này không được liệt kê để xóa."
            )
        self.status_var.set(message)

        if not untracked:
            messagebox.showinfo("Kết quả", "Không tìm thấy dataset item nào hoàn toàn không có trong metadata.")

    def select_all(self):
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children)

    def clear_selection(self):
        self.tree.selection_remove(self.tree.selection())

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Chưa chọn item", "Hãy chọn ít nhất một item trong danh sách.")
            return

        selected_items = [self.items_by_iid[iid] for iid in selected if iid in self.items_by_iid]
        file_count = sum(
            int(bool(item.audio_path and os.path.isfile(item.audio_path)))
            + int(bool(item.transcript_path and os.path.isfile(item.transcript_path)))
            for item in selected_items
        )

        confirm = messagebox.askyesno(
            "Xác nhận xóa",
            f"Bạn sắp xóa {len(selected_items)} dataset item ({file_count} file audio/transcript).\n\n"
            "Các file sẽ bị xóa khỏi ổ đĩa, không thể khôi phục bằng tool này.\n"
            "metadata.csv sẽ không bị chỉnh sửa.\n\nBạn có chắc chắn muốn tiếp tục?",
            icon="warning",
        )
        if not confirm:
            return

        deleted_files = 0
        failures = []
        for item in selected_items:
            for path in (item.audio_path, item.transcript_path):
                if not path or not os.path.isfile(path):
                    continue
                try:
                    os.remove(path)
                    deleted_files += 1
                except OSError as exc:
                    failures.append(f"{path}: {exc}")

        self.scan()
        if failures:
            messagebox.showwarning(
                "Đã xóa một phần",
                f"Đã xóa {deleted_files} file. Không xóa được {len(failures)} file:\n\n"
                + "\n".join(failures[:15]),
            )
        else:
            messagebox.showinfo(
                "Hoàn tất",
                f"Đã xóa {deleted_files} file thuộc {len(selected_items)} item đã chọn.\n"
                "metadata.csv được giữ nguyên.",
            )


def main():
    root = tk.Tk()
    UntrackedDatasetTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
