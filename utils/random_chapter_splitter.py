import csv
import random
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "Random Chapter Splitter"
CHAPTERS_NAME = "chapters"


class RandomChapterSplitter:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("900x650")
        self.root.minsize(800, 560)
        self.running = False

        self.source_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Sẵn sàng.")
        self.progress_var = tk.DoubleVar(value=0)

        self.build_ui()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="Chọn ngẫu nhiên 1 chapter từ mỗi video",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", pady=(0, 14))

        self.make_folder_row(main, "1. Thư mục dataset nguồn:", self.source_var, self.choose_source)
        self.make_folder_row(main, "2. Thư mục đích:", self.dest_var, self.choose_destination)

        # Khu vực chạy: thay thế hoàn toàn cho phần "Quy tắc xử lý"
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
            main, variable=self.progress_var, maximum=100, mode="determinate"
        ).pack(fill="x", pady=(0, 8))
        ttk.Label(main, textvariable=self.status_var).pack(anchor="w", pady=(0, 6))

        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_frame, wrap="none", font=("Consolas", 9), height=20)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Xóa log", command=self.clear_log).pack(side="left")
        ttk.Button(buttons, text="Thoát", command=self.root.destroy).pack(side="right")

    @staticmethod
    def make_folder_row(parent, label, variable, command):
        ttk.Label(parent, text=label).pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 12))
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Chọn thư mục...", command=command).pack(side="left", padx=(8, 0))

    def choose_source(self):
        path = filedialog.askdirectory(title="Chọn thư mục dataset nguồn")
        if path:
            self.source_var.set(path)

    def choose_destination(self):
        path = filedialog.askdirectory(title="Chọn thư mục đích")
        if path:
            self.dest_var.set(path)

    def clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def log(self, text):
        self.root.after(0, lambda: (self.log_text.insert(tk.END, text + "\n"), self.log_text.see(tk.END)))

    def set_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def set_progress(self, value):
        self.root.after(0, lambda: self.progress_var.set(value))

    def set_running(self, running):
        self.running = running
        self.root.after(0, lambda: self.start_btn.config(state="disabled" if running else "normal"))

    @staticmethod
    def find_valid_chapters(video_dir: Path):
        """
        Trả về danh sách chapter hợp lệ và lý do chi tiết nếu không có.
        Chapter hợp lệ = một file MP3 và một file TXT có cùng tên (không tính extension).
        """
        chapters_dir = None
        for p in video_dir.iterdir():
            if p.is_dir() and p.name.casefold() == CHAPTERS_NAME.casefold():
                chapters_dir = p
                break

        if chapters_dir is None:
            return [], ["Không tìm thấy thư mục 'chapters'."]

        mp3_by_stem = {}
        txt_by_stem = {}
        for p in chapters_dir.iterdir():
            if not p.is_file():
                continue
            key = p.stem.casefold()
            if p.suffix.casefold() == ".mp3":
                mp3_by_stem[key] = p
            elif p.suffix.casefold() == ".txt":
                txt_by_stem[key] = p

        common = sorted(set(mp3_by_stem) & set(txt_by_stem))
        valid = [(mp3_by_stem[k], txt_by_stem[k]) for k in common]
        if valid:
            return valid, []

        reasons = []
        if not mp3_by_stem and not txt_by_stem:
            reasons.append("Thư mục 'chapters' không chứa file MP3 hoặc TXT.")
        elif not mp3_by_stem:
            reasons.append(f"Không có file MP3 trong 'chapters' (có {len(txt_by_stem)} file TXT).")
        elif not txt_by_stem:
            reasons.append(f"Không có file TXT trong 'chapters' (có {len(mp3_by_stem)} file MP3).")
        else:
            mp3_only = sorted(set(mp3_by_stem) - set(txt_by_stem))
            txt_only = sorted(set(txt_by_stem) - set(mp3_by_stem))
            reasons.append(
                f"Có {len(mp3_by_stem)} file MP3 và {len(txt_by_stem)} file TXT, "
                "nhưng không có cặp MP3 + TXT nào trùng tên."
            )
            if mp3_only:
                names = ", ".join(mp3_by_stem[k].name for k in mp3_only[:5])
                if len(mp3_only) > 5:
                    names += " ..."
                reasons.append(f"MP3 không có TXT tương ứng ({len(mp3_only)}): {names}")
            if txt_only:
                names = ", ".join(txt_by_stem[k].name for k in txt_only[:5])
                if len(txt_only) > 5:
                    names += " ..."
                reasons.append(f"TXT không có MP3 tương ứng ({len(txt_only)}): {names}")

        return [], reasons

    def start(self):
        if self.running:
            return

        source = Path(self.source_var.get().strip())
        destination = Path(self.dest_var.get().strip())

        if not source.is_dir():
            messagebox.showerror(APP_TITLE, "Thư mục nguồn không tồn tại hoặc không hợp lệ.")
            return
        if source.resolve() == destination.resolve():
            messagebox.showerror(APP_TITLE, "Thư mục nguồn và thư mục đích không được giống nhau.")
            return

        try:
            destination.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Không thể tạo thư mục đích:\n{exc}")
            return

        # Không cho phép thư mục đích nằm bên trong thư mục nguồn,
        # vì khi quét source sẽ vô tình xem destination như một video.
        try:
            destination.resolve().relative_to(source.resolve())
            destination_inside_source = True
        except ValueError:
            destination_inside_source = False

        if destination_inside_source:
            messagebox.showerror(
                APP_TITLE,
                "Thư mục đích không được nằm bên trong thư mục nguồn. "
                "Hãy chọn một thư mục đích ở bên ngoài dataset nguồn.",
            )
            return

        video_dirs = sorted((p for p in source.iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
        if not video_dirs:
            messagebox.showinfo(APP_TITLE, "Không tìm thấy thư mục video nào.")
            return

        if not messagebox.askyesno(
            APP_TITLE,
            f"Tìm thấy {len(video_dirs)} video.\n\n"
            "Video có từ 2 chapter hợp lệ trở lên: chọn ngẫu nhiên 1 chapter và DI CHUYỂN khỏi nguồn.\n"
            "Video chỉ có 1 chapter hợp lệ: GIỮ NGUYÊN trong dataset nguồn.\n\n"
            "Tiếp tục?",
        ):
            return

        self.clear_log()
        self.set_running(True)
        self.set_progress(0)
        self.set_status("Đang xử lý...")
        threading.Thread(
            target=self.process,
            args=(source, destination, video_dirs),
            daemon=True,
        ).start()

    def process(self, source: Path, destination: Path, video_dirs):
        total = len(video_dirs)
        moved = 0
        kept_single = 0
        no_valid = 0
        exists = 0
        errors = 0
        report = []

        self.log(f"Nguồn: {source}")
        self.log(f"Đích:  {destination}")
        self.log(f"Số video: {total}")
        self.log("-" * 100)

        for i, video_dir in enumerate(video_dirs, 1):
            self.set_status(f"[{i}/{total}] {video_dir.name}")
            self.set_progress((i - 1) / total * 100)

            valid, reasons = self.find_valid_chapters(video_dir)
            if not valid:
                no_valid += 1
                reason_text = " ".join(reasons)
                self.log(f"[{i}/{total}] SKIP | Không có chapter hợp lệ: {video_dir.name}")
                for reason in reasons:
                    self.log(f"             └─ {reason}")
                report.append([video_dir.name, "", "", "NO_VALID_CHAPTER", reason_text])
                continue

            # Nếu video chỉ có đúng 1 chapter hợp lệ, giữ nguyên chapter đó
            # trong dataset nguồn để không làm mất toàn bộ dữ liệu của video.
            if len(valid) == 1:
                mp3_src, txt_src = valid[0]
                kept_single += 1
                self.log(f"[{i}/{total}] KEEP | Chỉ có 1 chapter: {video_dir.name} -> {mp3_src.name} + {txt_src.name}")
                report.append([video_dir.name, mp3_src.name, txt_src.name, "KEEP_SINGLE", "Video chỉ có 1 chapter hợp lệ; giữ nguyên trong nguồn"])
                continue

            # Từ 2 chapter trở lên: chọn ngẫu nhiên đúng 1 chapter để chuyển sang test.
            mp3_src, txt_src = random.choice(valid)
            dest_chapters = destination / video_dir.name / CHAPTERS_NAME
            mp3_dst = dest_chapters / mp3_src.name
            txt_dst = dest_chapters / txt_src.name

            if mp3_dst.exists() or txt_dst.exists():
                exists += 1
                self.log(f"[{i}/{total}] SKIP | Đã tồn tại: {video_dir.name}/{CHAPTERS_NAME}/{mp3_src.name}")
                report.append([video_dir.name, mp3_src.name, txt_src.name, "DEST_EXISTS", "File đích đã tồn tại"])
                continue

            try:
                dest_chapters.mkdir(parents=True, exist_ok=True)
                shutil.move(str(mp3_src), str(mp3_dst))
                try:
                    shutil.move(str(txt_src), str(txt_dst))
                except Exception:
                    # Roll back MP3 when TXT cannot be moved.
                    if mp3_dst.exists() and not mp3_src.exists():
                        shutil.move(str(mp3_dst), str(mp3_src))
                    raise

                moved += 1
                self.log(f"[{i}/{total}] OK   | {video_dir.name} -> {mp3_src.name} + {txt_src.name}")
                report.append([video_dir.name, mp3_src.name, txt_src.name, "MOVED", ""])
            except Exception as exc:
                errors += 1
                self.log(f"[{i}/{total}] ERROR| {video_dir.name} | {exc}")
                report.append([video_dir.name, mp3_src.name, txt_src.name, "ERROR", str(exc)])

        report_path = destination / "random_chapter_split_report.csv"
        try:
            with report_path.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["video_folder", "chapter_mp3", "chapter_txt", "status", "message"])
                writer.writerows(report)
        except Exception as exc:
            self.log(f"Không thể lưu report: {exc}")

        self.set_progress(100)
        self.set_status("Hoàn thành.")
        summary = (
            f"Hoàn thành.\n\nVideo: {total}\n"
            f"Đã chuyển (video có >= 2 chapter): {moved}\n"
            f"Giữ nguyên (video có 1 chapter): {kept_single}\n"
            f"Không có chapter hợp lệ: {no_valid}\n"
            f"Đã bỏ qua do file đích tồn tại: {exists}\n"
            f"Lỗi: {errors}"
        )

        invalid_rows = [row for row in report if row[3] == "NO_VALID_CHAPTER"]
        if invalid_rows:
            summary += "\n\n--- VIDEO KHÔNG CÓ CHAPTER HỢP LỆ ---"
            for row in invalid_rows:
                summary += f"\n\n• {row[0]}\n  Lý do: {row[4]}"
        self.log("-" * 100)
        self.log(summary.replace("\n\n", "\n"))
        self.log(f"Report: {report_path}")
        self.set_running(False)
        self.root.after(0, lambda: messagebox.showinfo(APP_TITLE, summary))


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    RandomChapterSplitter(root)
    root.mainloop()


if __name__ == "__main__":
    main()
