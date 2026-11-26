import csv
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Reverse Chapter Splitter"
CHAPTERS_NAME = "chapters"
REPORT_NAME = "reverse_chapter_split_report.csv"


class ReverseChapterSplitter:
    """
    Chuyển ngược chapter từ thư mục TEST về DATASET cũ.

    Cấu trúc TEST:
        test/
        ├── Video A/
        │   └── chapters/
        │       ├── 01 - ABC.mp3
        │       └── 01 - ABC.txt
        └── Video B/
            └── chapters/
                └── ...

    Kết quả:
        dataset_cu/
        ├── Video A/
        │   └── chapters/
        │       ├── 01 - ABC.mp3
        │       └── 01 - ABC.txt
        └── ...
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x650")
        self.root.minsize(800, 560)

        self.running = False

        self.test_var = tk.StringVar()
        self.dataset_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Sẵn sàng.")
        self.progress_var = tk.DoubleVar(value=0)

        self.build_ui()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="Chuyển ngược chapter từ TEST về dataset cũ",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", pady=(0, 14))

        self.make_folder_row(
            main,
            "1. Thư mục TEST:",
            self.test_var,
            self.choose_test,
        )

        self.make_folder_row(
            main,
            "2. Thư mục dataset cũ:",
            self.dataset_var,
            self.choose_dataset,
        )

        # Khu vực chạy thay cho phần "Quy tắc xử lý"
        run_frame = ttk.Frame(main)
        run_frame.pack(fill="x", pady=(0, 12))

        self.start_btn = tk.Button(
            run_frame,
            text="▶  CHẠY",
            command=self.start,
            font=("Segoe UI", 13, "bold"),
            padx=40,
            pady=12,
            cursor="hand2",
            relief="raised",
            bd=2,
        )
        self.start_btn.pack(fill="x")

        ttk.Progressbar(
            main,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        ).pack(fill="x", pady=(0, 8))

        ttk.Label(
            main,
            textvariable=self.status_var,
        ).pack(anchor="w", pady=(0, 6))

        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            wrap="none",
            font=("Consolas", 9),
            height=20,
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview,
        )
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(12, 0))

        ttk.Button(
            buttons,
            text="Xóa log",
            command=self.clear_log,
        ).pack(side="left")

        ttk.Button(
            buttons,
            text="Thoát",
            command=self.root.destroy,
        ).pack(side="right")

    @staticmethod
    def make_folder_row(parent, label, variable, command):
        ttk.Label(parent, text=label).pack(anchor="w")

        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 12))

        ttk.Entry(
            row,
            textvariable=variable,
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            row,
            text="Chọn thư mục...",
            command=command,
        ).pack(side="left", padx=(8, 0))

    def choose_test(self):
        path = filedialog.askdirectory(
            title="Chọn thư mục TEST",
        )
        if path:
            self.test_var.set(path)

    def choose_dataset(self):
        path = filedialog.askdirectory(
            title="Chọn thư mục dataset cũ",
        )
        if path:
            self.dataset_var.set(path)

    def clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def log(self, text):
        self.root.after(
            0,
            lambda: (
                self.log_text.insert(tk.END, text + "\n"),
                self.log_text.see(tk.END),
            ),
        )

    def set_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def set_progress(self, value):
        self.root.after(0, lambda: self.progress_var.set(value))

    def set_running(self, running):
        self.running = running
        self.root.after(
            0,
            lambda: self.start_btn.config(
                state="disabled" if running else "normal"
            ),
        )

    @staticmethod
    def find_chapters_dir(video_dir: Path):
        for p in video_dir.iterdir():
            if p.is_dir() and p.name.casefold() == CHAPTERS_NAME.casefold():
                return p
        return None

    @classmethod
    def find_test_chapters(cls, video_dir: Path):
        """
        Trả về:
            valid_pairs: [(mp3_path, txt_path), ...]
            diagnostics: chi tiết file bị thiếu / không ghép được.
        """
        diagnostics = []

        chapters_dir = cls.find_chapters_dir(video_dir)

        if chapters_dir is None:
            diagnostics.append("Không tìm thấy thư mục 'chapters'.")
            return [], diagnostics

        mp3_by_stem = {}
        txt_by_stem = {}

        for p in chapters_dir.iterdir():
            if not p.is_file():
                continue

            stem = p.stem.casefold()

            if p.suffix.casefold() == ".mp3":
                mp3_by_stem[stem] = p
            elif p.suffix.casefold() == ".txt":
                txt_by_stem[stem] = p

        common = sorted(set(mp3_by_stem) & set(txt_by_stem))
        valid_pairs = [(mp3_by_stem[k], txt_by_stem[k]) for k in common]

        mp3_only = sorted(set(mp3_by_stem) - set(txt_by_stem))
        txt_only = sorted(set(txt_by_stem) - set(mp3_by_stem))

        if mp3_only:
            names = ", ".join(mp3_by_stem[k].name for k in mp3_only[:5])
            suffix = " ..." if len(mp3_only) > 5 else ""
            diagnostics.append(
                f"MP3 không có TXT tương ứng ({len(mp3_only)}): {names}{suffix}"
            )

        if txt_only:
            names = ", ".join(txt_by_stem[k].name for k in txt_only[:5])
            suffix = " ..." if len(txt_only) > 5 else ""
            diagnostics.append(
                f"TXT không có MP3 tương ứng ({len(txt_only)}): {names}{suffix}"
            )

        if not valid_pairs and not diagnostics:
            diagnostics.append(
                "Thư mục 'chapters' không có cặp MP3 + TXT hợp lệ."
            )

        return valid_pairs, diagnostics

    def start(self):
        if self.running:
            return

        test_dir = Path(self.test_var.get().strip())
        dataset_dir = Path(self.dataset_var.get().strip())

        if not test_dir.is_dir():
            messagebox.showerror(
                APP_TITLE,
                "Thư mục TEST không tồn tại hoặc không hợp lệ.",
            )
            return

        if not dataset_dir.is_dir():
            messagebox.showerror(
                APP_TITLE,
                "Thư mục dataset cũ không tồn tại hoặc không hợp lệ.",
            )
            return

        if test_dir.resolve() == dataset_dir.resolve():
            messagebox.showerror(
                APP_TITLE,
                "Thư mục TEST và dataset cũ không được giống nhau.",
            )
            return

        # Không cho dataset cũ nằm bên trong TEST.
        try:
            dataset_dir.resolve().relative_to(test_dir.resolve())
            dataset_inside_test = True
        except ValueError:
            dataset_inside_test = False

        if dataset_inside_test:
            messagebox.showerror(
                APP_TITLE,
                "Thư mục dataset cũ không được nằm bên trong thư mục TEST. "
                "Hãy chọn dataset cũ ở bên ngoài TEST.",
            )
            return

        video_dirs = sorted(
            (p for p in test_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name.casefold(),
        )

        if not video_dirs:
            messagebox.showinfo(
                APP_TITLE,
                "Không tìm thấy thư mục video nào trong TEST.",
            )
            return

        confirm = messagebox.askyesno(
            APP_TITLE,
            f"Tìm thấy {len(video_dirs)} video trong TEST.\n\n"
            "Tool sẽ DI CHUYỂN các cặp MP3 + TXT từ TEST "
            "về đúng thư mục video/chapters trong dataset cũ.\n\n"
            "Không ghi đè file đã tồn tại ở dataset cũ.\n\n"
            "Tiếp tục?",
        )

        if not confirm:
            return

        self.clear_log()
        self.set_running(True)
        self.set_progress(0)
        self.set_status("Đang xử lý...")

        threading.Thread(
            target=self.process,
            args=(test_dir, dataset_dir, video_dirs),
            daemon=True,
        ).start()

    def process(self, test_dir: Path, dataset_dir: Path, video_dirs):
        total = len(video_dirs)

        moved_pairs = 0
        skipped_exists = 0
        no_valid = 0
        errors = 0
        videos_done = 0

        report = []
        detailed_no_valid = []

        self.log(f"TEST:        {test_dir}")
        self.log(f"DATASET CŨ:  {dataset_dir}")
        self.log(f"Số video:    {total}")
        self.log("-" * 110)

        for i, video_dir in enumerate(video_dirs, 1):
            self.set_status(f"[{i}/{total}] {video_dir.name}")
            self.set_progress((i - 1) / total * 100)

            valid, diagnostics = self.find_test_chapters(video_dir)

            if not valid:
                no_valid += 1

                self.log(
                    f"[{i}/{total}] SKIP | Không có chapter hợp lệ: "
                    f"{video_dir.name}"
                )

                for detail in diagnostics:
                    self.log(f"             └─ {detail}")

                detailed_no_valid.append(
                    (video_dir.name, diagnostics)
                )

                report.append(
                    [
                        video_dir.name,
                        "",
                        "",
                        "NO_VALID_CHAPTER",
                        " ".join(diagnostics),
                    ]
                )
                continue

            destination_chapters = (
                dataset_dir / video_dir.name / CHAPTERS_NAME
            )

            destination_chapters.mkdir(
                parents=True,
                exist_ok=True,
            )

            video_moved = 0
            video_failed = False

            for mp3_src, txt_src in valid:
                mp3_dst = destination_chapters / mp3_src.name
                txt_dst = destination_chapters / txt_src.name

                if mp3_dst.exists() or txt_dst.exists():
                    skipped_exists += 1
                    self.log(
                        f"[{i}/{total}] SKIP | File đích đã tồn tại: "
                        f"{video_dir.name}/{CHAPTERS_NAME}/"
                        f"{mp3_src.name}"
                    )
                    report.append(
                        [
                            video_dir.name,
                            mp3_src.name,
                            txt_src.name,
                            "DEST_EXISTS",
                            "MP3 hoặc TXT đã tồn tại ở dataset cũ",
                        ]
                    )
                    continue

                try:
                    shutil.move(str(mp3_src), str(mp3_dst))

                    try:
                        shutil.move(str(txt_src), str(txt_dst))
                    except Exception:
                        # Rollback MP3 nếu TXT không chuyển được.
                        if mp3_dst.exists() and not mp3_src.exists():
                            shutil.move(str(mp3_dst), str(mp3_src))
                        raise

                    moved_pairs += 1
                    video_moved += 1

                    self.log(
                        f"[{i}/{total}] OK   | {video_dir.name} -> "
                        f"{mp3_src.name} + {txt_src.name}"
                    )

                    report.append(
                        [
                            video_dir.name,
                            mp3_src.name,
                            txt_src.name,
                            "MOVED",
                            "",
                        ]
                    )

                except Exception as exc:
                    errors += 1
                    video_failed = True

                    self.log(
                        f"[{i}/{total}] ERROR| {video_dir.name} | {exc}"
                    )

                    report.append(
                        [
                            video_dir.name,
                            mp3_src.name,
                            txt_src.name,
                            "ERROR",
                            str(exc),
                        ]
                    )

            if video_moved > 0 and not video_failed:
                videos_done += 1

        report_path = test_dir / REPORT_NAME

        try:
            with report_path.open(
                "w",
                newline="",
                encoding="utf-8-sig",
            ) as f:
                writer = csv.writer(f)

                writer.writerow(
                    [
                        "video_folder",
                        "chapter_mp3",
                        "chapter_txt",
                        "status",
                        "message",
                    ]
                )

                writer.writerows(report)

        except Exception as exc:
            self.log(f"Không thể lưu report: {exc}")

        self.set_progress(100)
        self.set_status("Hoàn thành.")
        self.set_running(False)

        summary = (
            f"Hoàn thành.\n\n"
            f"Video trong TEST: {total}\n"
            f"Video đã chuyển chapter: {videos_done}\n"
            f"Cặp MP3 + TXT đã chuyển: {moved_pairs}\n"
            f"Chapter bị bỏ qua vì file đích đã tồn tại: {skipped_exists}\n"
            f"Video không có chapter hợp lệ: {no_valid}\n"
            f"Lỗi: {errors}\n\n"
            f"Report: {report_path}"
        )

        if detailed_no_valid:
            summary += "\n\n--- VIDEO KHÔNG CÓ CHAPTER HỢP LỆ ---"

            for video_name, reasons in detailed_no_valid:
                summary += f"\n\n• {video_name}"

                if reasons:
                    for reason in reasons:
                        summary += f"\n  └─ {reason}"

        self.log("-" * 110)
        self.log(summary)

        self.root.after(
            0,
            lambda: messagebox.showinfo(
                APP_TITLE,
                summary,
            ),
        )


def main():
    root = tk.Tk()

    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass

    ReverseChapterSplitter(root)
    root.mainloop()


if __name__ == "__main__":
    main()
