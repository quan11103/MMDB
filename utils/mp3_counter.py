import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from mutagen.mp3 import MP3


def format_duration(seconds):
    """
    Chuyển số giây thành dạng:
    HH giờ MM phút SS giây
    """
    seconds = int(round(seconds))

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours} giờ {minutes:02d} phút {secs:02d} giây"

    return f"{minutes} phút {secs:02d} giây"


def calculate_mp3_duration(folders):
    """
    Quét tất cả file MP3 trong nhiều thư mục.
    Quét đệ quy xuống các thư mục con.

    Bỏ qua:
    - source.mp3
    - file không phải .mp3

    Trả về thống kê chung của tất cả thư mục.
    """
    total_duration = 0
    durations = []
    skipped_files = 0
    scanned_files = set()

    for folder in folders:
        for root, dirs, files in os.walk(folder):
            for file in files:
                # Bỏ qua source.mp3
                if file.lower() == "source.mp3":
                    continue

                # Chỉ xử lý file .mp3
                if not file.lower().endswith(".mp3"):
                    continue

                file_path = os.path.abspath(os.path.join(root, file))

                # Tránh tính trùng nếu người dùng chọn
                # một thư mục nằm bên trong thư mục khác.
                if file_path in scanned_files:
                    continue

                scanned_files.add(file_path)

                try:
                    audio = MP3(file_path)
                    duration = audio.info.length

                    if duration > 0:
                        durations.append(duration)
                        total_duration += duration
                    else:
                        skipped_files += 1

                except Exception:
                    # File MP3 lỗi hoặc không đọc được
                    skipped_files += 1

    if not durations:
        return {
            "count": 0,
            "total": 0,
            "average": 0,
            "min": 0,
            "max": 0,
            "skipped": skipped_files,
        }

    average_duration = total_duration / len(durations)

    return {
        "count": len(durations),
        "total": total_duration,
        "average": average_duration,
        "min": min(durations),
        "max": max(durations),
        "skipped": skipped_files,
    }


def add_folders():
    """
    Tkinter không hỗ trợ chọn nhiều thư mục trực tiếp
    bằng askdirectory(), nên cho phép thêm nhiều thư mục
    vào danh sách trước khi chạy.
    """
    folder = filedialog.askdirectory(
        title="Chọn thư mục cần phân tích"
    )

    if not folder:
        return

    folder = os.path.abspath(folder)

    # Không thêm trùng
    existing = {
        os.path.abspath(folder_listbox.get(i))
        for i in range(folder_listbox.size())
    }

    if folder in existing:
        messagebox.showinfo(
            "Thông báo",
            "Thư mục này đã có trong danh sách."
        )
        return

    folder_listbox.insert(tk.END, folder)
    update_folder_count()


def remove_selected_folders():
    selected = list(folder_listbox.curselection())

    # Xóa từ cuối lên để index không bị thay đổi
    for index in reversed(selected):
        folder_listbox.delete(index)

    update_folder_count()


def clear_folders():
    folder_listbox.delete(0, tk.END)
    update_folder_count()
    reset_result()


def update_folder_count():
    count = folder_listbox.size()
    folder_count_label.config(
        text=f"Đã chọn: {count} thư mục"
    )


def reset_result():
    count_label.config(text="Số file MP3: 0")
    total_label.config(text="Tổng thời lượng: 0 phút 00 giây")
    average_label.config(
        text="Thời lượng trung bình: 0 phút 00 giây"
    )
    min_label.config(
        text="Thời lượng ngắn nhất (Min): 0 phút 00 giây"
    )
    max_label.config(
        text="Thời lượng dài nhất (Max): 0 phút 00 giây"
    )
    warning_label.config(text="")


def calculate():
    folders = [
        folder_listbox.get(i)
        for i in range(folder_listbox.size())
    ]

    if not folders:
        messagebox.showwarning(
            "Thiếu thư mục",
            "Hãy thêm ít nhất một thư mục trước khi phân tích."
        )
        return

    # Kiểm tra lại các thư mục
    invalid_folders = [
        folder for folder in folders
        if not os.path.isdir(folder)
    ]

    if invalid_folders:
        messagebox.showerror(
            "Lỗi",
            "Một hoặc nhiều thư mục không còn tồn tại:\n\n"
            + "\n".join(invalid_folders)
        )
        return

    try:
        result = calculate_mp3_duration(folders)

        count = result["count"]
        total = result["total"]
        average = result["average"]
        min_duration = result["min"]
        max_duration = result["max"]
        skipped = result["skipped"]

        count_label.config(
            text=f"Số file MP3: {count}"
        )

        total_label.config(
            text=f"Tổng thời lượng: {format_duration(total)}"
        )

        average_label.config(
            text=(
                f"Thời lượng trung bình: "
                f"{format_duration(average)}"
            )
        )

        min_label.config(
            text=(
                f"Thời lượng ngắn nhất (Min): "
                f"{format_duration(min_duration)}"
            )
        )

        max_label.config(
            text=(
                f"Thời lượng dài nhất (Max): "
                f"{format_duration(max_duration)}"
            )
        )

        if skipped > 0:
            warning_label.config(
                text=(
                    f"Có {skipped} file không đọc được "
                    f"thời lượng."
                )
            )
        else:
            warning_label.config(text="")

    except Exception as e:
        messagebox.showerror(
            "Lỗi",
            str(e)
        )


# =========================
# GUI
# =========================

root = tk.Tk()
root.title("MP3 Duration Analyzer - Multiple Folders")
root.geometry("760x700")
root.minsize(700, 620)


title_label = tk.Label(
    root,
    text="Phân tích thời lượng MP3",
    font=("Arial", 18, "bold")
)
title_label.pack(pady=(20, 5))


info_label = tk.Label(
    root,
    text=(
        "Có thể thêm nhiều thư mục. Tool sẽ quét đệ quy tất cả "
        "thư mục đã chọn và bỏ qua source.mp3."
    ),
    font=("Arial", 10),
    wraplength=680,
)
info_label.pack(pady=(0, 12))


# =========================
# Chọn nhiều thư mục
# =========================

folder_frame = tk.LabelFrame(
    root,
    text="Danh sách thư mục cần phân tích",
    padx=10,
    pady=10,
)
folder_frame.pack(
    fill="both",
    expand=False,
    padx=20,
    pady=(0, 10),
)


folder_listbox = tk.Listbox(
    folder_frame,
    height=8,
    font=("Consolas", 10),
    selectmode=tk.EXTENDED,
)

folder_listbox.pack(
    side=tk.LEFT,
    fill="both",
    expand=True,
)


folder_scrollbar = tk.Scrollbar(
    folder_frame,
    orient=tk.VERTICAL,
    command=folder_listbox.yview,
)

folder_scrollbar.pack(
    side=tk.RIGHT,
    fill=tk.Y,
)

folder_listbox.config(
    yscrollcommand=folder_scrollbar.set
)


folder_buttons = tk.Frame(root)
folder_buttons.pack(
    fill="x",
    padx=20,
    pady=(0, 5),
)


add_button = tk.Button(
    folder_buttons,
    text="+ THÊM THƯ MỤC",
    font=("Arial", 10, "bold"),
    command=add_folders,
    width=18,
    height=2,
)

add_button.pack(
    side=tk.LEFT,
    padx=(0, 8),
)


remove_button = tk.Button(
    folder_buttons,
    text="XÓA ĐÃ CHỌN",
    font=("Arial", 10),
    command=remove_selected_folders,
    width=14,
    height=2,
)

remove_button.pack(
    side=tk.LEFT,
    padx=4,
)


clear_button = tk.Button(
    folder_buttons,
    text="XÓA TẤT CẢ",
    font=("Arial", 10),
    command=clear_folders,
    width=12,
    height=2,
)

clear_button.pack(
    side=tk.LEFT,
    padx=4,
)


folder_count_label = tk.Label(
    root,
    text="Đã chọn: 0 thư mục",
    font=("Arial", 10, "bold"),
)

folder_count_label.pack(
    anchor="w",
    padx=20,
    pady=(0, 10),
)


# =========================
# Nút phân tích
# =========================

analyze_button = tk.Button(
    root,
    text="▶  PHÂN TÍCH",
    font=("Arial", 11, "bold"),
    command=calculate,
    width=24,
    height=2,
)

analyze_button.pack(
    pady=(0, 18)
)


# =========================
# Kết quả
# =========================

result_frame = tk.LabelFrame(
    root,
    text="Kết quả tổng hợp",
    padx=10,
    pady=10,
)

result_frame.pack(
    fill="x",
    padx=20,
)


count_label = tk.Label(
    result_frame,
    text="Số file MP3: 0",
    font=("Arial", 13, "bold")
)

count_label.pack(pady=4)


total_label = tk.Label(
    result_frame,
    text="Tổng thời lượng: 0 phút 00 giây",
    font=("Arial", 13)
)

total_label.pack(pady=4)


average_label = tk.Label(
    result_frame,
    text="Thời lượng trung bình: 0 phút 00 giây",
    font=("Arial", 13)
)

average_label.pack(pady=4)


min_label = tk.Label(
    result_frame,
    text="Thời lượng ngắn nhất (Min): 0 phút 00 giây",
    font=("Arial", 13)
)

min_label.pack(pady=4)


max_label = tk.Label(
    result_frame,
    text="Thời lượng dài nhất (Max): 0 phút 00 giây",
    font=("Arial", 13)
)

max_label.pack(pady=4)


warning_label = tk.Label(
    root,
    text="",
    font=("Arial", 10),
)

warning_label.pack(pady=10)


root.mainloop()
