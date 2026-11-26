import csv
import os
import tkinter as tk
from tkinter import filedialog, messagebox


REQUIRED_FIELDS = [
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


def resolve_path(path_value, base_folder):
    """
    Resolve a path from metadata.csv.

    - Nếu là absolute path -> dùng trực tiếp.
    - Nếu là relative path -> nối với thư mục gốc được chọn.
    - Hỗ trợ cả / và \\ trong metadata.
    """
    if not path_value or not path_value.strip():
        return None

    path_value = path_value.strip().strip('"')

    normalized = path_value.replace("/", os.sep).replace("\\", os.sep)

    if os.path.isabs(normalized):
        return os.path.normpath(normalized)

    return os.path.normpath(
        os.path.join(base_folder, normalized)
    )


def read_metadata(csv_path):
    """
    Đọc metadata.csv bằng UTF-8-sig.
    """
    with open(
        csv_path,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError("metadata.csv không có header.")

        missing_fields = [
            field
            for field in REQUIRED_FIELDS
            if field not in reader.fieldnames
        ]

        if missing_fields:
            raise ValueError(
                "metadata.csv thiếu các cột bắt buộc:\n"
                + "\n".join(f"- {field}" for field in missing_fields)
            )

        rows = list(reader)

        return reader.fieldnames, rows


def clean_metadata(csv_path, base_folder):
    """
    Giữ lại các dòng có:
    - audio_path tồn tại
    - transcript_path tồn tại

    Sau đó đánh lại item_id từ 001.
    """
    fieldnames, rows = read_metadata(csv_path)

    kept_rows = []
    removed_audio = []
    removed_transcript = []
    removed_both = []

    for row_number, row in enumerate(rows, start=2):
        audio_raw = row.get("audio_path", "")
        transcript_raw = row.get("transcript_path", "")

        audio_path = resolve_path(
            audio_raw,
            base_folder
        )

        transcript_path = resolve_path(
            transcript_raw,
            base_folder
        )

        audio_exists = (
            audio_path is not None
            and os.path.isfile(audio_path)
        )

        transcript_exists = (
            transcript_path is not None
            and os.path.isfile(transcript_path)
        )

        # Giữ lại chỉ khi cả 2 file đều tồn tại
        if audio_exists and transcript_exists:
            kept_rows.append(row)
            continue

        if not audio_exists and not transcript_exists:
            removed_both.append({
                "row_number": row_number,
                "audio_path": audio_raw,
                "transcript_path": transcript_raw,
            })

        elif not audio_exists:
            removed_audio.append({
                "row_number": row_number,
                "audio_path": audio_raw,
            })

        else:
            removed_transcript.append({
                "row_number": row_number,
                "transcript_path": transcript_raw,
            })

    # Đánh lại item_id từ 001
    for index, row in enumerate(kept_rows, start=1):
        row["item_id"] = f"{index:03d}"

    return {
        "fieldnames": fieldnames,
        "original_count": len(rows),
        "kept_rows": kept_rows,
        "removed_audio": removed_audio,
        "removed_transcript": removed_transcript,
        "removed_both": removed_both,
    }


def write_metadata(output_path, fieldnames, rows):
    """
    Ghi metadata.csv mới bằng UTF-8-sig.
    """
    with open(
        output_path,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)


def show_preview(result):
    result_text.delete("1.0", tk.END)

    original_count = result["original_count"]
    kept_rows = result["kept_rows"]

    removed_audio = result["removed_audio"]
    removed_transcript = result["removed_transcript"]
    removed_both = result["removed_both"]

    removed_count = (
        len(removed_audio)
        + len(removed_transcript)
        + len(removed_both)
    )

    result_text.insert(
        tk.END,
        "KẾT QUẢ KIỂM TRA METADATA\n"
        + "=" * 100
        + "\n\n"
        f"Tổng số dòng ban đầu: {original_count}\n"
        f"Giữ lại: {len(kept_rows)}\n"
        f"Loại bỏ: {removed_count}\n\n"

        f"Thiếu audio: {len(removed_audio)}\n"
        f"Thiếu transcript: {len(removed_transcript)}\n"
        f"Thiếu cả audio + transcript: {len(removed_both)}\n\n"

        + "-" * 100
        + "\n"
    )

    if not (
        removed_audio
        or removed_transcript
        or removed_both
    ):
        result_text.insert(
            tk.END,
            "Tất cả dòng đều có đủ audio và transcript.\n"
        )
        return

    if removed_both:
        result_text.insert(
            tk.END,
            "\n[THIẾU CẢ AUDIO + TRANSCRIPT]\n"
            + "-" * 100
            + "\n"
        )

        for item in removed_both:
            result_text.insert(
                tk.END,
                f"Dòng {item['row_number']}\n"
                f"  Audio: {item['audio_path']}\n"
                f"  TXT:   {item['transcript_path']}\n\n"
            )

    if removed_audio:
        result_text.insert(
            tk.END,
            "\n[THIẾU AUDIO]\n"
            + "-" * 100
            + "\n"
        )

        for item in removed_audio:
            result_text.insert(
                tk.END,
                f"Dòng {item['row_number']} | "
                f"Audio: {item['audio_path']}\n"
            )

    if removed_transcript:
        result_text.insert(
            tk.END,
            "\n[THIẾU TRANSCRIPT]\n"
            + "-" * 100
            + "\n"
        )

        for item in removed_transcript:
            result_text.insert(
                tk.END,
                f"Dòng {item['row_number']} | "
                f"TXT: {item['transcript_path']}\n"
            )


def choose_metadata():
    csv_path = filedialog.askopenfilename(
        title="Chọn metadata.csv",
        filetypes=[
            ("CSV files", "*.csv"),
            ("All files", "*.*"),
        ]
    )

    if not csv_path:
        return

    csv_path_var.set(csv_path)

    # Mặc định chọn thư mục chứa metadata.csv làm base folder
    default_base = os.path.dirname(csv_path)

    if not base_folder_var.get():
        base_folder_var.set(default_base)

    status_label.config(
        text="Đã chọn metadata.csv."
    )


def choose_base_folder():
    folder = filedialog.askdirectory(
        title="Chọn thư mục gốc của dataset"
    )

    if folder:
        base_folder_var.set(folder)


def preview_metadata():
    csv_path = csv_path_var.get().strip()
    base_folder = base_folder_var.get().strip()

    if not csv_path:
        messagebox.showwarning(
            "Thiếu file",
            "Hãy chọn metadata.csv."
        )
        return

    if not os.path.isfile(csv_path):
        messagebox.showerror(
            "Lỗi",
            "Không tìm thấy metadata.csv."
        )
        return

    if not base_folder:
        base_folder = os.path.dirname(csv_path)
        base_folder_var.set(base_folder)

    if not os.path.isdir(base_folder):
        messagebox.showerror(
            "Lỗi",
            "Thư mục gốc dataset không tồn tại."
        )
        return

    try:
        result = clean_metadata(
            csv_path,
            base_folder
        )

        root.preview_result = result

        show_preview(result)

        kept_count = len(result["kept_rows"])

        status_label.config(
            text=(
                f"Đã kiểm tra: giữ lại {kept_count} dòng. "
                "Có thể tạo metadata mới."
            )
        )

        save_button.config(
            state=tk.NORMAL
        )

    except Exception as e:
        root.preview_result = None
        save_button.config(
            state=tk.DISABLED
        )

        messagebox.showerror(
            "Lỗi",
            str(e)
        )


def save_cleaned_metadata():
    result = getattr(
        root,
        "preview_result",
        None
    )

    if not result:
        messagebox.showwarning(
            "Chưa kiểm tra",
            "Hãy kiểm tra metadata trước."
        )
        return

    default_name = "metadata_cleaned.csv"

    output_path = filedialog.asksaveasfilename(
        title="Lưu metadata.csv đã làm sạch",
        defaultextension=".csv",
        initialfile=default_name,
        filetypes=[
            ("CSV files", "*.csv"),
            ("All files", "*.*"),
        ]
    )

    if not output_path:
        return

    try:
        write_metadata(
            output_path,
            result["fieldnames"],
            result["kept_rows"]
        )

        final_count = len(result["kept_rows"])

        if final_count > 0:
            new_first_id = result["kept_rows"][0]["item_id"]
            new_last_id = result["kept_rows"][-1]["item_id"]
        else:
            new_first_id = "-"
            new_last_id = "-"

        messagebox.showinfo(
            "Hoàn tất",
            (
                "Đã tạo metadata.csv mới.\n\n"
                f"File: {output_path}\n"
                f"Số dòng giữ lại: {final_count}\n"
                f"item_id: {new_first_id} → {new_last_id}\n\n"
                "File metadata.csv gốc không bị thay đổi."
            )
        )

        status_label.config(
            text=f"Đã lưu metadata sạch: {output_path}"
        )

    except Exception as e:
        messagebox.showerror(
            "Lỗi",
            str(e)
        )


# =========================
# GUI
# =========================

root = tk.Tk()
root.title("Metadata Cleanup & Reindex")
root.geometry("1050x760")

root.preview_result = None

csv_path_var = tk.StringVar()
base_folder_var = tk.StringVar()


title_label = tk.Label(
    root,
    text="LÀM SẠCH & ĐÁNH LẠI METADATA.CSV",
    font=("Arial", 18, "bold")
)
title_label.pack(pady=(25, 8))


info_label = tk.Label(
    root,
    text=(
        "Giữ lại dòng có đủ audio + transcript | "
        "Đánh lại item_id từ 001"
    ),
    font=("Arial", 10)
)
info_label.pack(pady=(0, 15))


# =========================
# Chọn metadata.csv
# =========================

csv_frame = tk.Frame(root)
csv_frame.pack(
    fill=tk.X,
    padx=25,
    pady=5
)

tk.Label(
    csv_frame,
    text="metadata.csv:",
    width=15,
    anchor="w",
    font=("Arial", 10, "bold")
).pack(side=tk.LEFT)

csv_entry = tk.Entry(
    csv_frame,
    textvariable=csv_path_var,
    font=("Arial", 10)
)
csv_entry.pack(
    side=tk.LEFT,
    fill=tk.X,
    expand=True,
    padx=5
)

tk.Button(
    csv_frame,
    text="CHỌN FILE",
    command=choose_metadata,
    width=12
).pack(side=tk.RIGHT)


# =========================
# Chọn thư mục gốc
# =========================

base_frame = tk.Frame(root)
base_frame.pack(
    fill=tk.X,
    padx=25,
    pady=5
)

tk.Label(
    base_frame,
    text="Thư mục gốc:",
    width=15,
    anchor="w",
    font=("Arial", 10, "bold")
).pack(side=tk.LEFT)

base_entry = tk.Entry(
    base_frame,
    textvariable=base_folder_var,
    font=("Arial", 10)
)
base_entry.pack(
    side=tk.LEFT,
    fill=tk.X,
    expand=True,
    padx=5
)

tk.Button(
    base_frame,
    text="CHỌN THƯ MỤC",
    command=choose_base_folder,
    width=12
).pack(side=tk.RIGHT)


# =========================
# Nút kiểm tra
# =========================

preview_button = tk.Button(
    root,
    text="KIỂM TRA METADATA",
    font=("Arial", 11, "bold"),
    command=preview_metadata,
    width=24,
    height=2
)
preview_button.pack(
    pady=(10, 5)
)


# =========================
# Nút lưu
# =========================

save_button = tk.Button(
    root,
    text="TẠO METADATA.CSV ĐÃ LÀM SẠCH",
    font=("Arial", 11, "bold"),
    command=save_cleaned_metadata,
    width=32,
    height=2,
    state=tk.DISABLED
)
save_button.pack(
    pady=(5, 10)
)


# =========================
# Kết quả
# =========================

text_frame = tk.Frame(root)
text_frame.pack(
    fill=tk.BOTH,
    expand=True,
    padx=25,
    pady=5
)

scrollbar_y = tk.Scrollbar(
    text_frame
)
scrollbar_y.pack(
    side=tk.RIGHT,
    fill=tk.Y
)

scrollbar_x = tk.Scrollbar(
    text_frame,
    orient=tk.HORIZONTAL
)
scrollbar_x.pack(
    side=tk.BOTTOM,
    fill=tk.X
)

result_text = tk.Text(
    text_frame,
    height=20,
    font=("Consolas", 10),
    yscrollcommand=scrollbar_y.set,
    xscrollcommand=scrollbar_x.set,
    wrap=tk.NONE
)

result_text.pack(
    side=tk.LEFT,
    fill=tk.BOTH,
    expand=True
)

scrollbar_y.config(
    command=result_text.yview
)

scrollbar_x.config(
    command=result_text.xview
)


# =========================
# Trạng thái
# =========================

status_label = tk.Label(
    root,
    text="Chưa kiểm tra metadata.",
    font=("Arial", 10)
)

status_label.pack(
    pady=(5, 15)
)


root.mainloop()