import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "List Subfolders"


class ListSubfoldersApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("760x560")
        self.root.minsize(650, 480)

        self.folder_var = tk.StringVar()
        self.count_var = tk.StringVar(value="Chưa có dữ liệu.")

        self.build_ui()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="Liệt kê thư mục con cấp 1",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", pady=(0, 14))

        ttk.Label(
            main,
            text="Chỉ liệt kê các thư mục nằm trực tiếp bên trong thư mục đã chọn.",
        ).pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(main)
        row.pack(fill="x", pady=(0, 12))

        ttk.Entry(
            row,
            textvariable=self.folder_var,
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            row,
            text="Chọn thư mục...",
            command=self.choose_folder,
        ).pack(side="left", padx=(8, 0))

        button_row = ttk.Frame(main)
        button_row.pack(fill="x", pady=(0, 12))

        tk.Button(
            button_row,
            text="▶  LIỆT KÊ",
            command=self.list_subfolders,
            font=("Segoe UI", 11, "bold"),
            padx=24,
            pady=8,
            cursor="hand2",
        ).pack(side="left")

        ttk.Button(
            button_row,
            text="Sao chép danh sách",
            command=self.copy_list,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_row,
            text="Lưu TXT",
            command=self.save_txt,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_row,
            text="Xóa",
            command=self.clear,
        ).pack(side="right")

        ttk.Label(main, textvariable=self.count_var).pack(
            anchor="w", pady=(0, 6)
        )

        list_frame = ttk.Frame(main)
        list_frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(
            list_frame,
            font=("Consolas", 10),
            selectmode=tk.EXTENDED,
        )
        self.listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.listbox.yview,
        )
        scrollbar.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        ttk.Label(
            main,
            text="Chỉ tính thư mục cấp 1; không bao gồm tệp và không quét các cấp sâu hơn.",
            foreground="#666666",
        ).pack(anchor="w", pady=(8, 0))

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục cần liệt kê")
        if folder:
            self.folder_var.set(folder)
            self.list_subfolders()

    def get_subfolders(self):
        folder = Path(self.folder_var.get().strip())

        if not folder.is_dir():
            raise ValueError(
                "Thư mục đã chọn không tồn tại hoặc không hợp lệ."
            )

        return sorted(
            (p for p in folder.iterdir() if p.is_dir()),
            key=lambda p: p.name.casefold(),
        )

    def list_subfolders(self):
        try:
            subfolders = self.get_subfolders()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        except PermissionError as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Không có quyền đọc thư mục:\n{exc}",
            )
            return
        except OSError as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Không thể đọc thư mục:\n{exc}",
            )
            return

        self.listbox.delete(0, tk.END)

        for folder in subfolders:
            self.listbox.insert(tk.END, folder.name)

        self.count_var.set(
            f"Tìm thấy {len(subfolders)} thư mục con cấp 1."
        )

    def get_names(self):
        return [
            self.listbox.get(i)
            for i in range(self.listbox.size())
        ]

    def copy_list(self):
        names = self.get_names()

        if not names:
            messagebox.showinfo(
                APP_TITLE,
                "Chưa có danh sách thư mục để sao chép.",
            )
            return

        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(names))
        self.root.update()

        messagebox.showinfo(
            APP_TITLE,
            f"Đã sao chép {len(names)} tên thư mục vào clipboard.",
        )

    def save_txt(self):
        names = self.get_names()

        if not names:
            messagebox.showinfo(
                APP_TITLE,
                "Chưa có danh sách thư mục để lưu.",
            )
            return

        path = filedialog.asksaveasfilename(
            title="Lưu danh sách thư mục",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile="subfolders.txt",
        )

        if not path:
            return

        try:
            Path(path).write_text(
                "\n".join(names),
                encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showerror(
                APP_TITLE,
                f"Không thể lưu file:\n{exc}",
            )
            return

        messagebox.showinfo(
            APP_TITLE,
            f"Đã lưu {len(names)} tên thư mục.",
        )

    def clear(self):
        self.listbox.delete(0, tk.END)
        self.count_var.set("Chưa có dữ liệu.")


def main():
    root = tk.Tk()

    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass

    ListSubfoldersApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
