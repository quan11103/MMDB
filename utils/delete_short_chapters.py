import os
import tkinter as tk
from tkinter import filedialog, messagebox
from mutagen.mp3 import MP3


# =========================
# Cấu hình thời lượng
# =========================

MIN_DURATION_SECONDS = 60       # < 1 phút
MAX_DURATION_SECONDS = 15 * 60  # > 15 phút


def format_duration(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def find_invalid_chapters(folder):
    """
    Tìm các chapter:
    - Ngắn hơn 1 phút
    - Dài hơn 15 phút

    Bỏ qua source.mp3.
    """

    invalid_chapters = []
    unreadable_files = []

    for root, dirs, files in os.walk(folder):

        for file_name in files:

            # Bỏ qua source.mp3
            if file_name.lower() == "source.mp3":
                continue

            # Chỉ xử lý file MP3
            if not file_name.lower().endswith(".mp3"):
                continue

            mp3_path = os.path.join(root, file_name)

            try:
                duration = MP3(mp3_path).info.length

                # Chapter quá ngắn
                if duration < MIN_DURATION_SECONDS:
                    duration_type = "NGẮN"

                # Chapter quá dài
                elif duration > MAX_DURATION_SECONDS:
                    duration_type = "DÀI"

                # Chapter hợp lệ
                else:
                    continue

                txt_path = os.path.splitext(mp3_path)[0] + ".txt"

                invalid_chapters.append({
                    "mp3_path": mp3_path,
                    "txt_path": txt_path,
                    "duration": duration,
                    "duration_type": duration_type,
                    "txt_exists": os.path.isfile(txt_path),
                })

            except Exception as e:

                unreadable_files.append({
                    "path": mp3_path,
                    "error": str(e)
                })

    invalid_chapters.sort(
        key=lambda item: item["mp3_path"].lower()
    )

    return invalid_chapters, unreadable_files


def choose_folder():

    folder = filedialog.askdirectory(
        title="Chọn thư mục dataset"
    )

    if not folder:
        return

    result_text.delete("1.0", tk.END)

    status_label.config(
        text="Đang quét..."
    )

    root.invalid_chapters_to_delete = []

    delete_button.config(
        state=tk.DISABLED
    )

    try:

        invalid_chapters, unreadable_files = find_invalid_chapters(
            folder
        )

        # =========================
        # Thống kê
        # =========================

        short_chapters = [
            item
            for item in invalid_chapters
            if item["duration_type"] == "NGẮN"
        ]

        long_chapters = [
            item
            for item in invalid_chapters
            if item["duration_type"] == "DÀI"
        ]

        total_invalid = len(invalid_chapters)

        short_count = len(short_chapters)
        long_count = len(long_chapters)

        transcript_exists = sum(
            1
            for item in invalid_chapters
            if item["txt_exists"]
        )

        transcript_missing = (
            total_invalid - transcript_exists
        )

        count_label.config(
            text=(
                f"Chapter < 1:00: {short_count}    |    "
                f"Chapter > 15:00: {long_count}    |    "
                f"Tổng: {total_invalid}"
            )
        )

        # =========================
        # Hiển thị danh sách
        # =========================

        if invalid_chapters:

            result_text.insert(
                tk.END,
                "CÁC CHAPTER SẼ BỊ XÓA\n"
                + "=" * 110
                + "\n"
            )

            # -------------------------
            # Chapter ngắn
            # -------------------------

            if short_chapters:

                result_text.insert(
                    tk.END,
                    f"\n[NGẮN HƠN 1:00] - {short_count} chapter\n"
                    + "-" * 110
                    + "\n"
                )

                for index, item in enumerate(
                    short_chapters,
                    start=1
                ):

                    result_text.insert(
                        tk.END,
                        f"{index:>4}. "
                        f"{format_duration(item['duration'])} | "
                        f"{item['mp3_path']}\n"
                    )

                    if item["txt_exists"]:

                        result_text.insert(
                            tk.END,
                            f"       + TXT: "
                            f"{item['txt_path']}\n"
                        )

                    else:

                        result_text.insert(
                            tk.END,
                            "       + TXT: Không tồn tại\n"
                        )

            # -------------------------
            # Chapter dài
            # -------------------------

            if long_chapters:

                result_text.insert(
                    tk.END,
                    f"\n[DÀI HƠN 15:00] - {long_count} chapter\n"
                    + "-" * 110
                    + "\n"
                )

                for index, item in enumerate(
                    long_chapters,
                    start=1
                ):

                    result_text.insert(
                        tk.END,
                        f"{index:>4}. "
                        f"{format_duration(item['duration'])} | "
                        f"{item['mp3_path']}\n"
                    )

                    if item["txt_exists"]:

                        result_text.insert(
                            tk.END,
                            f"       + TXT: "
                            f"{item['txt_path']}\n"
                        )

                    else:

                        result_text.insert(
                            tk.END,
                            "       + TXT: Không tồn tại\n"
                        )

            result_text.insert(
                tk.END,
                "\n"
                + "=" * 110
                + "\n"
                "Chỉ khi bấm 'XÓA CÁC CHAPTER KHÔNG HỢP LỆ' "
                "thì file mới bị xóa.\n"
            )

            status_label.config(
                text=(
                    f"Tìm thấy {total_invalid} chapter không hợp lệ: "
                    f"{short_count} chapter ngắn + "
                    f"{long_count} chapter dài."
                )
            )

            delete_button.config(
                state=tk.NORMAL
            )

            root.invalid_chapters_to_delete = (
                invalid_chapters
            )

        else:

            result_text.insert(
                tk.END,
                "Không tìm thấy chapter nào:\n\n"
                "- Ngắn hơn 1 phút\n"
                "- Dài hơn 15 phút"
            )

            status_label.config(
                text="Không có chapter cần xóa."
            )

        # =========================
        # Cảnh báo file lỗi
        # =========================

        if unreadable_files:

            warning_label.config(
                text=(
                    f"Cảnh báo: {len(unreadable_files)} "
                    f"file MP3 không đọc được thông tin audio."
                )
            )

        else:

            warning_label.config(
                text=(
                    "Tất cả MP3 được quét đều đọc được thời lượng."
                )
            )

    except Exception as e:

        messagebox.showerror(
            "Lỗi",
            str(e)
        )

        status_label.config(
            text="Có lỗi xảy ra khi quét."
        )


def delete_invalid_chapters():

    items = getattr(
        root,
        "invalid_chapters_to_delete",
        []
    )

    if not items:

        messagebox.showinfo(
            "Thông báo",
            "Không có chapter nào để xóa."
        )

        return

    # =========================
    # Thống kê trước khi xóa
    # =========================

    short_count = sum(
        1
        for item in items
        if item["duration_type"] == "NGẮN"
    )

    long_count = sum(
        1
        for item in items
        if item["duration_type"] == "DÀI"
    )

    total_mp3 = len(items)

    total_txt = sum(
        1
        for item in items
        if item["txt_exists"]
    )

    confirmed = messagebox.askyesno(

        "Xác nhận xóa",

        (
            f"Có {total_mp3} chapter không hợp lệ.\n\n"

            f"- Chapter < 1:00: "
            f"{short_count}\n"

            f"- Chapter > 15:00: "
            f"{long_count}\n\n"

            f"Sẽ xóa:\n"

            f"- {total_mp3} file MP3\n"

            f"- {total_txt} file transcript .txt "
            f"có cùng tên\n\n"

            "source.mp3 sẽ KHÔNG bị xóa.\n\n"

            "Bạn có chắc chắn muốn tiếp tục?"
        ),

        icon="warning"
    )

    if not confirmed:
        return

    # =========================
    # Xóa file
    # =========================

    deleted_mp3 = 0
    deleted_txt = 0

    failed = []

    for item in items:

        mp3_path = item["mp3_path"]
        txt_path = item["txt_path"]

        # -------------------------
        # Xóa MP3
        # -------------------------

        try:

            if os.path.isfile(mp3_path):

                os.remove(mp3_path)

                deleted_mp3 += 1

        except Exception as e:

            failed.append(
                f"MP3: {mp3_path} -> {e}"
            )

        # -------------------------
        # Xóa TXT
        # -------------------------

        if os.path.isfile(txt_path):

            try:

                os.remove(txt_path)

                deleted_txt += 1

            except Exception as e:

                failed.append(
                    f"TXT: {txt_path} -> {e}"
                )

    # =========================
    # Hoàn tất
    # =========================

    root.invalid_chapters_to_delete = []

    delete_button.config(
        state=tk.DISABLED
    )

    result_text.delete(
        "1.0",
        tk.END
    )

    result_text.insert(
        tk.END,

        "ĐÃ HOÀN TẤT\n"
        + "=" * 70
        + "\n"

        f"Chapter < 1:00 đã xử lý: "
        f"{short_count}\n"

        f"Chapter > 15:00 đã xử lý: "
        f"{long_count}\n\n"

        f"Đã xóa MP3: "
        f"{deleted_mp3}\n"

        f"Đã xóa transcript TXT: "
        f"{deleted_txt}\n"
    )

    # =========================
    # Nếu có lỗi
    # =========================

    if failed:

        result_text.insert(
            tk.END,
            f"\nKhông xóa được: "
            f"{len(failed)} file\n\n"
        )

        for error in failed:

            result_text.insert(
                tk.END,
                error + "\n"
            )

        status_label.config(
            text=(
                "Đã xóa nhưng vẫn còn một số "
                "file gặp lỗi."
            )
        )

        warning_label.config(
            text=(
                f"Có {len(failed)} lỗi "
                "trong quá trình xóa."
            )
        )

    else:

        status_label.config(
            text=(
                "Đã xóa thành công các chapter "
                "ngắn/dài và transcript tương ứng."
            )
        )

        warning_label.config(
            text="Hoàn tất."
        )

    count_label.config(
        text=(
            "Chapter < 1:00: 0    |    "
            "Chapter > 15:00: 0    |    "
            "Tổng: 0"
        )
    )


# =========================
# GUI
# =========================

root = tk.Tk()

root.title(
    "Delete Invalid Chapters"
)

root.geometry(
    "950x700"
)

root.invalid_chapters_to_delete = []


title_label = tk.Label(

    root,

    text=(
        "XÓA CHAPTER NGẮN HƠN 1 PHÚT "
        "HOẶC DÀI HƠN 15 PHÚT"
    ),

    font=(
        "Arial",
        18,
        "bold"
    )
)

title_label.pack(
    pady=(25, 8)
)


info_label = tk.Label(

    root,

    text=(
        "Quét MP3 đệ quy | "
        "Bỏ qua source.mp3 | "
        "Xóa MP3 và transcript .txt cùng tên"
    ),

    font=(
        "Arial",
        10
    )
)

info_label.pack(
    pady=5
)


choose_button = tk.Button(

    root,

    text="CHỌN THƯ MỤC DATASET",

    font=(
        "Arial",
        11,
        "bold"
    ),

    command=choose_folder,

    width=24,

    height=2
)

choose_button.pack(
    pady=12
)


count_label = tk.Label(

    root,

    text=(
        "Chapter < 1:00: 0    |    "
        "Chapter > 15:00: 0    |    "
        "Tổng: 0"
    ),

    font=(
        "Arial",
        12,
        "bold"
    )
)

count_label.pack(
    pady=8
)


text_frame = tk.Frame(
    root
)

text_frame.pack(
    fill=tk.BOTH,
    expand=True,
    padx=20,
    pady=10
)


scrollbar = tk.Scrollbar(
    text_frame
)

scrollbar.pack(
    side=tk.RIGHT,
    fill=tk.Y
)


result_text = tk.Text(

    text_frame,

    font=(
        "Consolas",
        10
    ),

    yscrollcommand=scrollbar.set,

    wrap=tk.NONE
)

result_text.pack(
    side=tk.LEFT,
    fill=tk.BOTH,
    expand=True
)


scrollbar.config(
    command=result_text.yview
)


status_label = tk.Label(

    root,

    text="Chưa chọn thư mục.",

    font=(
        "Arial",
        10
    )
)

status_label.pack(
    pady=5
)


warning_label = tk.Label(

    root,

    text="",

    font=(
        "Arial",
        10
    )
)

warning_label.pack(
    pady=5
)


delete_button = tk.Button(

    root,

    text="XÓA CÁC CHAPTER KHÔNG HỢP LỆ",

    font=(
        "Arial",
        11,
        "bold"
    ),

    command=delete_invalid_chapters,

    width=30,

    height=2,

    state=tk.DISABLED
)

delete_button.pack(
    pady=(8, 20)
)


root.mainloop()