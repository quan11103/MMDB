import os
import threading
import tempfile
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd
from mutagen.mp3 import MP3

# ============================================================
# FFmpeg shared build
# ============================================================
# TorchCodec on Windows needs FFmpeg shared DLLs to be visible
# to the Python process. Keep the handle alive for the lifetime
# of the application.
FFMPEG_BIN = r"D:\Documents\Downloads\ffmpeg-9.0.1-full_build-shared\ffmpeg-9.0.1-full_build-shared\bin"

if not os.path.isdir(FFMPEG_BIN):
    raise RuntimeError(
        "Không tìm thấy thư mục FFmpeg shared bin:\n"
        f"{FFMPEG_BIN}"
    )

_FFMPEG_DLL_DIR_HANDLE = os.add_dll_directory(FFMPEG_BIN)
FFMPEG_EXE = os.path.join(FFMPEG_BIN, "ffmpeg.exe")

if not os.path.isfile(FFMPEG_EXE):
    raise RuntimeError(f"Không tìm thấy ffmpeg.exe: {FFMPEG_EXE}")

from pyannote.audio import Pipeline


PIPELINE_NAME = "pyannote/speaker-diarization-3.1"


def format_duration(seconds):
    seconds = int(round(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours} giờ {minutes:02d} phút {secs:02d} giây"
    return f"{minutes} phút {secs:02d} giây"


def scan_mp3_files(folder):
    """Quét đệ quy, chỉ lấy MP3 và bỏ qua source.mp3."""
    mp3_files = []

    for root, dirs, files in os.walk(folder):
        for file in files:
            if file.lower() == "source.mp3":
                continue
            if not file.lower().endswith(".mp3"):
                continue

            mp3_files.append(os.path.join(root, file))

    return sorted(mp3_files, key=lambda p: p.lower())


def get_audio_info(file_path):
    """Đọc duration, sample rate và số channel từ MP3."""
    try:
        audio = MP3(file_path)
        duration = float(audio.info.length or 0)
        sample_rate = getattr(audio.info, "sample_rate", 0) or 0
        channels = getattr(audio.info, "channels", 0) or 0
        return duration, sample_rate, channels, ""
    except Exception as e:
        return 0, 0, 0, str(e)


def create_pipeline(huggingface_token):
    """
    Khởi tạo pipeline theo thuật toán người dùng cung cấp.
    """
    return Pipeline.from_pretrained(
        PIPELINE_NAME,
        token=huggingface_token.strip()
    )


def convert_mp3_to_wav(mp3_path):
    """
    Chuyển MP3 sang WAV PCM tạm thời trước khi đưa vào pyannote.

    Lý do:
    MP3 có thể tạo sai lệch số sample ở các boundary khi TorchCodec
    đọc trực tiếp. WAV PCM giúp pyannote xử lý các đoạn thời gian
    ổn định hơn.

    Returns:
        temp_wav_path: đường dẫn WAV tạm thời.
    """
    fd, temp_wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    command = [
        FFMPEG_EXE,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", mp3_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        temp_wav_path,
    ]

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if completed.returncode != 0:
            error_message = completed.stderr.strip()
            raise RuntimeError(
                "FFmpeg không thể chuyển MP3 sang WAV"
                + (f": {error_message}" if error_message else "")
            )

        if not os.path.isfile(temp_wav_path) or os.path.getsize(temp_wav_path) == 0:
            raise RuntimeError("FFmpeg tạo WAV rỗng hoặc không tạo được file.")

        return temp_wav_path

    except Exception:
        try:
            os.remove(temp_wav_path)
        except OSError:
            pass
        raise


def count_speakers(pipeline, file_path):
    """
    Chạy speaker diarization và đếm speaker duy nhất.

    Tương thích với pyannote.audio 4.x:
        result = pipeline(file_path)
        diarization = result.speaker_diarization
        labels = list(diarization.labels())

    MP3 được chuyển sang WAV PCM tạm thời trước khi phân tích
    để tránh lỗi boundary/sample count khi TorchCodec decode MP3.
    """
    temp_wav_path = None

    try:
        temp_wav_path = convert_mp3_to_wav(file_path)

        result = pipeline(temp_wav_path)

        # pyannote.audio 4.x trả về DiarizeOutput.
        diarization = result.speaker_diarization

        labels = list(diarization.labels())
        num_speakers = len(labels)

        return num_speakers, labels

    finally:
        if temp_wav_path and os.path.isfile(temp_wav_path):
            try:
                os.remove(temp_wav_path)
            except OSError:
                pass


class SpeakerCountApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Speaker Count Analyzer - Pyannote")
        self.root.geometry("1050x760")
        self.root.minsize(900, 650)

        self.selected_folder = ""
        self.results = []
        self.worker_thread = None
        self.stop_requested = False

        self.folder_var = tk.StringVar()
        self.token_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Chưa bắt đầu")
        self.progress_var = tk.DoubleVar(value=0)

        self.build_gui()

    def build_gui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="Xác định số người nói trong toàn bộ file MP3",
            font=("Arial", 18, "bold")
        ).pack(pady=(0, 14))

        ttk.Label(
            main,
            text=(
                "Quét đệ quy • bỏ qua source.mp3 • "
                "pyannote/speaker-diarization-3.1 • MP3 → WAV • xuất CSV"
            ),
            font=("Arial", 10)
        ).pack(pady=(0, 12))

        # Thư mục
        folder_frame = ttk.LabelFrame(main, text="Thư mục audio", padding=10)
        folder_frame.pack(fill="x", pady=6)

        ttk.Entry(
            folder_frame,
            textvariable=self.folder_var
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ttk.Button(
            folder_frame,
            text="CHỌN THƯ MỤC",
            command=self.choose_folder
        ).pack(side="right")

        # Hugging Face token
        token_frame = ttk.LabelFrame(
            main,
            text="Hugging Face Access Token",
            padding=10
        )
        token_frame.pack(fill="x", pady=6)

        ttk.Entry(
            token_frame,
            textvariable=self.token_var,
            show="*"
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ttk.Label(
            token_frame,
            text="Dùng để tải model pyannote"
        ).pack(side="right")

        # Điều khiển
        control_frame = ttk.Frame(main)
        control_frame.pack(fill="x", pady=12)

        self.start_button = ttk.Button(
            control_frame,
            text="BẮT ĐẦU PHÂN TÍCH",
            command=self.start_analysis
        )
        self.start_button.pack(side="left")

        self.stop_button = ttk.Button(
            control_frame,
            text="DỪNG",
            command=self.request_stop,
            state="disabled"
        )
        self.stop_button.pack(side="left", padx=8)

        self.save_button = ttk.Button(
            control_frame,
            text="LƯU CSV",
            command=self.save_csv,
            state="disabled"
        )
        self.save_button.pack(side="left")

        # Progress
        progress_frame = ttk.LabelFrame(main, text="Tiến trình", padding=10)
        progress_frame.pack(fill="x", pady=6)

        ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate"
        ).pack(fill="x", pady=(0, 8))

        self.progress_label = ttk.Label(progress_frame, text="0 / 0")
        self.progress_label.pack(anchor="w")

        ttk.Label(
            progress_frame,
            textvariable=self.status_var
        ).pack(anchor="w", pady=(6, 0))

        # Summary
        summary_frame = ttk.LabelFrame(main, text="Tổng hợp", padding=10)
        summary_frame.pack(fill="x", pady=6)

        self.total_label = ttk.Label(summary_frame, text="Tổng file MP3: 0")
        self.total_label.grid(row=0, column=0, sticky="w", padx=12, pady=4)

        self.processed_label = ttk.Label(summary_frame, text="Đã xử lý: 0")
        self.processed_label.grid(row=0, column=1, sticky="w", padx=12, pady=4)

        self.single_label = ttk.Label(summary_frame, text="1 speaker: 0")
        self.single_label.grid(row=1, column=0, sticky="w", padx=12, pady=4)

        self.multi_label = ttk.Label(
            summary_frame,
            text="Multiple speakers: 0"
        )
        self.multi_label.grid(row=1, column=1, sticky="w", padx=12, pady=4)

        self.zero_label = ttk.Label(summary_frame, text="0 speaker: 0")
        self.zero_label.grid(row=2, column=0, sticky="w", padx=12, pady=4)

        self.error_label = ttk.Label(summary_frame, text="Lỗi: 0")
        self.error_label.grid(row=2, column=1, sticky="w", padx=12, pady=4)

        # Log
        log_frame = ttk.LabelFrame(main, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True, pady=(10, 0))

        log_container = ttk.Frame(log_frame)
        log_container.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_container,
            wrap="none",
            font=("Consolas", 10),
            padx=8,
            pady=8
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(
            log_container,
            orient="vertical",
            command=self.log_text.yview
        )
        scrollbar.pack(side="right", fill="y", padx=(8, 0))

        self.log_text.configure(yscrollcommand=scrollbar.set)

    def log(self, message):
        def append():
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")

        self.root.after(0, append)

    def choose_folder(self):
        folder = filedialog.askdirectory(
            title="Chọn thư mục chứa dataset MP3"
        )

        if not folder:
            return

        self.selected_folder = folder
        self.folder_var.set(folder)

        try:
            files = scan_mp3_files(folder)
            self.total_label.config(text=f"Tổng file MP3: {len(files)}")
            self.status_var.set(
                f"Đã tìm thấy {len(files)} file MP3."
            )
            self.log(f"[SCAN] Tìm thấy {len(files)} file MP3.")
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def update_summary(self):
        processed = len(self.results)

        single = sum(
            1 for r in self.results
            if r["classification"] == "1 speaker"
        )
        multi = sum(
            1 for r in self.results
            if r["classification"] == "multiple speakers"
        )
        zero = sum(
            1 for r in self.results
            if r["classification"] == "0 speaker"
        )
        errors = sum(
            1 for r in self.results
            if r["status"] == "error"
        )

        self.processed_label.config(text=f"Đã xử lý: {processed}")
        self.single_label.config(text=f"1 speaker: {single}")
        self.multi_label.config(
            text=f"Multiple speakers: {multi}"
        )
        self.zero_label.config(text=f"0 speaker: {zero}")
        self.error_label.config(text=f"Lỗi: {errors}")

    def start_analysis(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return

        folder = self.selected_folder.strip() or self.folder_var.get().strip()
        token = self.token_var.get().strip()

        if not folder:
            messagebox.showwarning(
                "Thiếu thư mục",
                "Vui lòng chọn thư mục audio."
            )
            return

        if not os.path.isdir(folder):
            messagebox.showerror(
                "Lỗi",
                "Thư mục không tồn tại."
            )
            return

        if not token:
            messagebox.showwarning(
                "Thiếu token",
                "Vui lòng nhập Hugging Face Access Token."
            )
            return

        self.selected_folder = folder
        self.results = []
        self.stop_requested = False

        self.progress_var.set(0)
        self.progress_label.config(text="0 / 0")
        self.status_var.set("Đang chuẩn bị...")

        self.log_text.delete("1.0", "end")
        self.log("[START] Bắt đầu phân tích.")
        self.log(f"[FOLDER] {folder}")
        self.log(f"[MODEL] {PIPELINE_NAME}")
        self.log(f"[FFMPEG] {FFMPEG_EXE}")
        self.log("[AUDIO] MP3 -> WAV PCM 16 kHz mono trước khi diarization.")

        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.save_button.config(state="disabled")

        self.worker_thread = threading.Thread(
            target=self.run_analysis,
            args=(folder, token),
            daemon=True
        )
        self.worker_thread.start()

    def request_stop(self):
        self.stop_requested = True
        self.status_var.set("Đang yêu cầu dừng...")
        self.log(
            "[STOP] Đã gửi yêu cầu dừng. "
            "File đang chạy có thể vẫn cần hoàn tất."
        )

    def run_analysis(self, folder, token):
        try:
            mp3_files = scan_mp3_files(folder)
            total = len(mp3_files)

            self.root.after(
                0,
                lambda: self.total_label.config(
                    text=f"Tổng file MP3: {total}"
                )
            )

            if total == 0:
                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Kết quả",
                        "Không tìm thấy file MP3 hợp lệ."
                    )
                )
                return

            self.log(f"[SCAN] Tổng cộng: {total} file.")
            self.log("[MODEL] Đang tải pipeline...")

            self.root.after(
                0,
                lambda: self.status_var.set(
                    "Đang tải pipeline pyannote..."
                )
            )

            pipeline = create_pipeline(token)

            self.log("[MODEL] Tải pipeline thành công.")
            self.log("[MODEL] pyannote.audio 4.x: dùng result.speaker_diarization.labels()")

            for index, file_path in enumerate(mp3_files, start=1):
                if self.stop_requested:
                    self.log("[STOP] Đã dừng bởi người dùng.")
                    break

                relative_path = os.path.relpath(file_path, folder)

                self.root.after(
                    0,
                    lambda i=index, t=total, rp=relative_path: (
                        self.progress_label.config(text=f"{i} / {t}"),
                        self.status_var.config(
                            text=f"Đang xử lý: {rp}"
                        ),
                        self.progress_var.set((i - 1) / t * 100)
                    )
                )

                self.log(f"[{index}/{total}] {relative_path}")

                duration, sample_rate, channels, metadata_error = (
                    get_audio_info(file_path)
                )

                try:
                    num_speakers, labels = count_speakers(
                        pipeline,
                        file_path
                    )

                    if num_speakers == 0:
                        classification = "0 speaker"
                    elif num_speakers == 1:
                        classification = "1 speaker"
                    else:
                        classification = "multiple speakers"

                    result = {
                        "file_name": os.path.basename(file_path),
                        "file_path": file_path,
                        "relative_path": relative_path,
                        "num_speakers": num_speakers,
                        "speakers": ", ".join(labels),
                        "classification": classification,
                        "duration_sec": round(duration, 3),
                        "duration": format_duration(duration),
                        "sample_rate": sample_rate,
                        "channels": channels,
                        "status": "success",
                        "message": (
                            metadata_error if metadata_error else ""
                        )
                    }

                    self.results.append(result)

                    self.log(
                        f"    -> {classification} | "
                        f"{num_speakers} speaker(s)"
                    )

                except Exception as e:
                    self.results.append({
                        "file_name": os.path.basename(file_path),
                        "file_path": file_path,
                        "relative_path": relative_path,
                        "num_speakers": "",
                        "speakers": "",
                        "classification": "error",
                        "duration_sec": round(duration, 3),
                        "duration": format_duration(duration),
                        "sample_rate": sample_rate,
                        "channels": channels,
                        "status": "error",
                        "message": str(e)
                    })

                    self.log(f"    -> ERROR: {type(e).__name__}: {e}")

                self.root.after(0, self.update_summary)
                self.root.after(
                    0,
                    lambda i=index, t=total: self.progress_var.set(
                        i / t * 100
                    )
                )

            self.root.after(
                0,
                lambda: self.status_var.set(
                    "Hoàn tất."
                    if not self.stop_requested
                    else "Đã dừng."
                )
            )

            self.log("[END] Hoàn tất quá trình phân tích.")

            if self.results:
                self.root.after(
                    0,
                    lambda: self.save_button.config(state="normal")
                )
                self.root.after(0, self.auto_save_csv)

        except Exception as e:
            self.log(f"[FATAL] {e}")
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Lỗi nghiêm trọng",
                    str(e)
                )
            )
            self.root.after(
                0,
                lambda: self.status_var.set("Có lỗi xảy ra.")
            )
        finally:
            self.root.after(
                0,
                lambda: (
                    self.start_button.config(state="normal"),
                    self.stop_button.config(state="disabled")
                )
            )

    def make_dataframe(self):
        columns = [
            "file_name",
            "file_path",
            "relative_path",
            "num_speakers",
            "speakers",
            "classification",
            "duration_sec",
            "duration",
            "sample_rate",
            "channels",
            "status",
            "message"
        ]

        return pd.DataFrame(self.results, columns=columns)

    def auto_save_csv(self):
        if not self.results:
            return

        output_path = os.path.join(
            self.selected_folder,
            "speaker_counts.csv"
        )

        try:
            self.make_dataframe().to_csv(
                output_path,
                index=False,
                encoding="utf-8-sig"
            )
            self.log(f"[CSV] Đã tự động lưu: {output_path}")
        except Exception as e:
            self.log(f"[CSV] Không thể tự động lưu: {e}")

    def save_csv(self):
        if not self.results:
            messagebox.showwarning(
                "Không có dữ liệu",
                "Chưa có kết quả để lưu."
            )
            return

        output_path = filedialog.asksaveasfilename(
            title="Lưu kết quả speaker count",
            initialdir=self.selected_folder or os.getcwd(),
            initialfile="speaker_counts.csv",
            defaultextension=".csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )

        if not output_path:
            return

        try:
            self.make_dataframe().to_csv(
                output_path,
                index=False,
                encoding="utf-8-sig"
            )

            self.log(f"[CSV] Đã lưu: {output_path}")

            messagebox.showinfo(
                "Thành công",
                f"Đã lưu kết quả:\n{output_path}"
            )
        except Exception as e:
            messagebox.showerror(
                "Lỗi lưu CSV",
                str(e)
            )


if __name__ == "__main__":
    root = tk.Tk()
    app = SpeakerCountApp(root)
    root.mainloop()