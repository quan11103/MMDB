import os
import tkinter as tk
from tkinter import filedialog, messagebox
from collections import Counter

from mutagen.mp3 import MP3


def format_percentage(value, total):
    if total == 0:
        return "0.0%"
    return f"{(value / total) * 100:.1f}%"


def analyze_mp3_files(folder):
    sample_rates = Counter()
    channels = Counter()

    total_files = 0
    skipped_files = 0

    for root, dirs, files in os.walk(folder):
        for file in files:
            # Bỏ qua source.mp3
            if file.lower() == "source.mp3":
                continue

            # Chỉ xử lý file .mp3
            if not file.lower().endswith(".mp3"):
                continue

            total_files += 1
            file_path = os.path.join(root, file)

            try:
                audio = MP3(file_path)

                sample_rate = audio.info.sample_rate
                channel_count = audio.info.channels

                sample_rates[sample_rate] += 1

                if channel_count == 1:
                    channels["Mono"] += 1
                elif channel_count == 2:
                    channels["Stereo"] += 1
                else:
                    channels[f"{channel_count} kênh"] += 1

            except Exception:
                skipped_files += 1

    return {
        "total_files": total_files,
        "sample_rates": sample_rates,
        "channels": channels,
        "skipped_files": skipped_files,
    }


def choose_folder():
    folder = filedialog.askdirectory(
        title="Chọn thư mục cần kiểm tra"
    )

    if not folder:
        return

    try:
        result = analyze_mp3_files(folder)

        total_files = result["total_files"]
        sample_rates = result["sample_rates"]
        channels = result["channels"]
        skipped_files = result["skipped_files"]

        sample_rate_text.delete("1.0", tk.END)
        channel_text.delete("1.0", tk.END)

        total_label.config(
            text=f"Tổng số file MP3: {total_files}"
        )

        if sample_rates:
            sample_rate_text.insert(
                tk.END,
                "Sample Rate\n"
                "-----------------------------\n"
            )

            for rate in sorted(sample_rates):
                count = sample_rates[rate]
                percentage = format_percentage(count, total_files)

                sample_rate_text.insert(
                    tk.END,
                    f"{rate:>6} Hz: {count:>5} file ({percentage})\n"
                )
        else:
            sample_rate_text.insert(
                tk.END,
                "Không có dữ liệu."
            )

        if channels:
            channel_text.insert(
                tk.END,
                "Channels\n"
                "-----------------------------\n"
            )

            ordered_channels = []

            if "Mono" in channels:
                ordered_channels.append("Mono")

            if "Stereo" in channels:
                ordered_channels.append("Stereo")

            for channel_name in sorted(channels):
                if channel_name not in ordered_channels:
                    ordered_channels.append(channel_name)

            for channel_name in ordered_channels:
                count = channels[channel_name]
                percentage = format_percentage(count, total_files)

                channel_text.insert(
                    tk.END,
                    f"{channel_name:>10}: {count:>5} file ({percentage})\n"
                )
        else:
            channel_text.insert(
                tk.END,
                "Không có dữ liệu."
            )

        if skipped_files > 0:
            warning_label.config(
                text=f"Cảnh báo: {skipped_files} file không đọc được thông tin audio."
            )
        else:
            warning_label.config(
                text="Tất cả file MP3 đều đọc được thông tin."
            )

    except Exception as e:
        messagebox.showerror(
            "Lỗi",
            str(e)
        )


root = tk.Tk()
root.title("MP3 Audio Analyzer")
root.geometry("650x560")

title_label = tk.Label(
    root,
    text="Phân tích Sample Rate & Channels",
    font=("Arial", 18, "bold")
)
title_label.pack(pady=(25, 8))

info_label = tk.Label(
    root,
    text="Bỏ qua tất cả file có tên source.mp3",
    font=("Arial", 10)
)
info_label.pack(pady=5)

choose_button = tk.Button(
    root,
    text="CHỌN THƯ MỤC",
    font=("Arial", 11, "bold"),
    command=choose_folder,
    width=20,
    height=2
)
choose_button.pack(pady=15)

total_label = tk.Label(
    root,
    text="Tổng số file MP3: 0",
    font=("Arial", 14, "bold")
)
total_label.pack(pady=10)

sample_rate_frame = tk.Frame(root)
sample_rate_frame.pack(pady=8)

sample_rate_text = tk.Text(
    sample_rate_frame,
    width=45,
    height=7,
    font=("Consolas", 11)
)
sample_rate_text.pack()

channel_frame = tk.Frame(root)
channel_frame.pack(pady=8)

channel_text = tk.Text(
    channel_frame,
    width=45,
    height=5,
    font=("Consolas", 11)
)
channel_text.pack()

warning_label = tk.Label(
    root,
    text="",
    font=("Arial", 10)
)
warning_label.pack(pady=10)

root.mainloop()
