import csv
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime


APP_TITLE = "Kiểm tra thư mục dataset thiếu MP3 chương"


def is_source_mp3(filename: str) -> bool:
    """Kiểm tra tên source.mp3, không phân biệt chữ hoa/thường."""
    return filename.casefold() == "source.mp3"


def scan_level1_folders(root_folder: str):
    """
    Duyệt các thư mục con cấp 1 của root_folder.
    Với mỗi thư mục cấp 1, quét đệ quy toàn bộ cây thư mục bên trong.
    Trả về các thư mục không có bất kỳ file MP3 nào ngoài source.mp3.
    """
    if not os.path.isdir(root_folder):
        raise ValueError("Thư mục dataset không tồn tại hoặc không hợp lệ.")

    results = []
    level1_folders = []

    # Chỉ lấy thư mục con trực tiếp của thư mục gốc.
    with os.scandir(root_folder) as entries:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                level1_folders.append(entry.path)

    level1_folders.sort(key=lambda p: os.path.basename(p).casefold())

    for folder_path in level1_folders:
        other_mp3_files = []
        source_mp3_files = []
        walk_errors = []

        def on_walk_error(error):
            walk_errors.append(str(error))

        for current_root, dirs, filenames in os.walk(
            folder_path,
            topdown=True,
            onerror=on_walk_error,
            followlinks=False,
        ):
            # Không đi theo thư mục liên kết (symlink) để tránh quét ra ngoài dataset.
            dirs[:] = sorted(dirs, key=str.casefold)
            for filename in filenames:
                if not filename.casefold().endswith(".mp3"):
                    continue

                full_path = os.path.join(current_root, filename)
                if is_source_mp3(filename):
                    source_mp3_files.append(full_path)
                else:
                    other_mp3_files.append(full_path)

        if not other_mp3_files:
            if walk_errors:
                status = "Không có MP3 khác source.mp3 (có lỗi khi quét một phần thư mục)"
            else:
                status = "Không có MP3 khác source.mp3"

            results.append({
                "folder_name": os.path.basename(folder_path),
                "folder_path": folder_path,
                "source_mp3_count": len(source_mp3_files),
                "source_mp3_paths": source_mp3_files,
                "other_mp3_count": len(other_mp3_files),
                "other_mp3_paths": other_mp3_files,
                "status": status,
                "scan_errors": walk_errors,
            })

    return {
        "root_folder": root_folder,
        "level1_folder_count": len(level1_folders),
        "matching_folders": results,
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def format_results(scan_result) -> str:
    folders = scan_result["matching_folders"]
    lines = [
        "KẾT QUẢ KIỂM TRA THƯ MỤC CON CẤP 1",
        "=" * 100,
        f"Thư mục dataset: {scan_result['root_folder']}",
        f"Thời điểm quét: {scan_result['scan_time']}",
        f"Tổng thư mục con cấp 1: {scan_result['level1_folder_count']}",
        f"Thư mục không có MP3 nào ngoài source.mp3: {len(folders)}",
        "-" * 100,
        "",
    ]

    if not folders:
        lines.append("Không tìm thấy thư mục nào thỏa điều kiện.")
        return "\n".join(lines)

    for index, item in enumerate(folders, start=1):
        lines.extend([
            f"{index}. {item['folder_name']}",
            f"   Đường dẫn: {item['folder_path']}",
            f"   Số file source.mp3 tìm thấy: {item['source_mp3_count']}",
            f"   Trạng thái: {item['status']}",
        ])
        if item["source_mp3_paths"]:
            lines.append("   Các file source.mp3:")
            lines.extend(f"      - {path}" for path in item["source_mp3_paths"])
        if item["scan_errors"]:
            lines.append("   Lỗi khi quét:")
            lines.extend(f"      - {error}" for error in item["scan_errors"])
        lines.append("")

    return "\n".join(lines)


def save_csv(scan_result, output_path):
    fields = [
        "folder_name",
        "folder_path",
        "source_mp3_count",
        "source_mp3_paths",
        "other_mp3_count",
        "status",
        "scan_errors",
    ]
    with open(output_path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for item in scan_result["matching_folders"]:
            writer.writerow({
                **item,
                "source_mp3_paths": " | ".join(item["source_mp3_paths"]),
                "scan_errors": " | ".join(item["scan_errors"]),
            })


# ------------------------- GUI -------------------------

root = tk.Tk()
root.title(APP_TITLE)
root.geometry("1050x720")
root.minsize(820, 560)

root_folder_var = tk.StringVar()
status_var = tk.StringVar(value="Chọn thư mục gốc của dataset rồi nhấn KIỂM TRA.")
root.scan_result = None


def choose_root_folder():
    folder = filedialog.askdirectory(title="Chọn thư mục gốc dataset")
    if folder:
        root_folder_var.set(folder)
        status_var.set("Đã chọn thư mục dataset. Nhấn KIỂM TRA để quét.")


def run_scan():
    folder = root_folder_var.get().strip().strip('"')
    if not folder:
        messagebox.showwarning("Thiếu thư mục", "Hãy chọn thư mục gốc của dataset.")
        return
    if not os.path.isdir(folder):
        messagebox.showerror("Thư mục không hợp lệ", "Không tìm thấy thư mục đã chọn.")
        return

    scan_button.config(state=tk.DISABLED)
    root.config(cursor="watch")
    status_var.set("Đang quét các thư mục con cấp 1... Vui lòng chờ.")
    root.update_idletasks()

    try:
        result = scan_level1_folders(folder)
        root.scan_result = result
        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, format_results(result))
        result_text.see("1.0")

        count = len(result["matching_folders"])
        status_var.set(
            f"Đã quét {result['level1_folder_count']} thư mục cấp 1; "
            f"tìm thấy {count} thư mục không có MP3 ngoài source.mp3."
        )
        save_txt_button.config(state=tk.NORMAL)
        save_csv_button.config(state=tk.NORMAL)
        copy_button.config(state=tk.NORMAL)
    except Exception as exc:
        root.scan_result = None
        save_txt_button.config(state=tk.DISABLED)
        save_csv_button.config(state=tk.DISABLED)
        copy_button.config(state=tk.DISABLED)
        messagebox.showerror("Lỗi khi quét", str(exc))
        status_var.set("Quét không thành công.")
    finally:
        root.config(cursor="")
        scan_button.config(state=tk.NORMAL)


def save_txt():
    result = root.scan_result
    if not result:
        return
    output_path = filedialog.asksaveasfilename(
        title="Lưu báo cáo kết quả",
        defaultextension=".txt",
        initialfile="folders_without_chapter_mp3.txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
    )
    if not output_path:
        return
    try:
        with open(output_path, "w", encoding="utf-8-sig") as file:
            file.write(format_results(result))
        messagebox.showinfo("Đã lưu", f"Đã lưu báo cáo tại:\n{output_path}")
    except Exception as exc:
        messagebox.showerror("Không thể lưu", str(exc))


def save_csv_action():
    result = root.scan_result
    if not result:
        return
    output_path = filedialog.asksaveasfilename(
        title="Lưu danh sách dưới dạng CSV",
        defaultextension=".csv",
        initialfile="folders_without_chapter_mp3.csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    if not output_path:
        return
    try:
        save_csv(result, output_path)
        messagebox.showinfo("Đã lưu", f"Đã lưu CSV tại:\n{output_path}")
    except Exception as exc:
        messagebox.showerror("Không thể lưu", str(exc))


def copy_results():
    result = root.scan_result
    if not result:
        return
    content = format_results(result)
    root.clipboard_clear()
    root.clipboard_append(content)
    root.update()
    status_var.set("Đã sao chép báo cáo vào clipboard.")


header = tk.Label(
    root,
    text="KIỂM TRA THƯ MỤC CON CẤP 1 KHÔNG CÓ FILE MP3 CHƯƠNG",
    font=("Arial", 15, "bold"),
)
header.pack(padx=20, pady=(20, 8))

info = tk.Label(
    root,
    text=(
        "Quét đệ quy toàn bộ thư mục bên trong mỗi thư mục cấp 1. "
        "Chỉ tính file .mp3 có tên khác source.mp3."
    ),
    font=("Arial", 10),
    wraplength=980,
)
info.pack(padx=20, pady=(0, 14))

folder_frame = tk.Frame(root)
folder_frame.pack(fill=tk.X, padx=22, pady=4)

tk.Label(folder_frame, text="Thư mục dataset:", width=17, anchor="w").pack(side=tk.LEFT)
tk.Entry(folder_frame, textvariable=root_folder_var).pack(
    side=tk.LEFT, fill=tk.X, expand=True, padx=6
)
tk.Button(folder_frame, text="CHỌN THƯ MỤC", command=choose_root_folder).pack(side=tk.RIGHT)

button_frame = tk.Frame(root)
button_frame.pack(pady=10)
scan_button = tk.Button(
    button_frame, text="KIỂM TRA", command=run_scan, font=("Arial", 10, "bold"), width=16, height=2
)
scan_button.pack(side=tk.LEFT, padx=5)
save_txt_button = tk.Button(button_frame, text="LƯU TXT", command=save_txt, width=12, state=tk.DISABLED)
save_txt_button.pack(side=tk.LEFT, padx=5)
save_csv_button = tk.Button(button_frame, text="LƯU CSV", command=save_csv_action, width=12, state=tk.DISABLED)
save_csv_button.pack(side=tk.LEFT, padx=5)
copy_button = tk.Button(button_frame, text="SAO CHÉP KẾT QUẢ", command=copy_results, width=20, state=tk.DISABLED)
copy_button.pack(side=tk.LEFT, padx=5)

result_frame = tk.Frame(root)
result_frame.pack(fill=tk.BOTH, expand=True, padx=22, pady=5)
scroll_y = tk.Scrollbar(result_frame)
scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
scroll_x = tk.Scrollbar(result_frame, orient=tk.HORIZONTAL)
scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
result_text = tk.Text(
    result_frame,
    wrap=tk.NONE,
    font=("Consolas", 10),
    yscrollcommand=scroll_y.set,
    xscrollcommand=scroll_x.set,
)
result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
scroll_y.config(command=result_text.yview)
scroll_x.config(command=result_text.xview)

status_label = tk.Label(root, textvariable=status_var, anchor="w", font=("Arial", 9))
status_label.pack(fill=tk.X, padx=22, pady=(6, 16))

root.mainloop()
