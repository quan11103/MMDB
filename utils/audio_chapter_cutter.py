import csv
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog


# ============================================================
# Whisper configuration
# ============================================================

# Model có thể đổi thành: tiny, base, small, medium, large
# 'small' là lựa chọn cân bằng cho tiếng Việt.
WHISPER_MODEL = "small"
WHISPER_LANGUAGE = "vi"


# ============================================================
# Dataset metadata configuration
# ============================================================

METADATA_FILENAME = "metadata.csv"
METADATA_FIELDS = [
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


# ============================================================
# Utility
# ============================================================

def sanitize_filename(name: str) -> str:
    """
    Làm sạch tên file để sử dụng được trên Windows.
    """
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.rstrip('. ')

    return name or "audio"


def run_command(command):
    """
    Chạy command và trả về stdout.
    """
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "Command failed."
        )

    return result.stdout


# ============================================================
# Get video information
# ============================================================

# ============================================================
# Metadata CSV
# ============================================================

def format_metadata_path(path: str, metadata_root: str) -> str:
    """Lưu đường dẫn tương đối từ thư mục chứa metadata.csv."""
    relative = os.path.relpath(os.path.abspath(path), os.path.abspath(metadata_root))
    return relative.replace(os.sep, "/")


def get_next_item_id(rows) -> str:
    """Tìm item_id số tiếp theo, giữ định dạng 3 chữ số."""
    max_id = 0
    for row in rows:
        try:
            max_id = max(max_id, int(str(row.get("item_id", "")).strip()))
        except (TypeError, ValueError):
            continue
    return f"{max_id + 1:03d}"


def update_metadata_csv(
    metadata_root,
    info,
    chapters,
    chapter_dir,
    transcript_files,
    log_callback,
):
    """Tạo/cập nhật metadata.csv với một dòng cho mỗi dataset item."""
    metadata_root = os.path.abspath(metadata_root)
    os.makedirs(metadata_root, exist_ok=True)
    metadata_file = os.path.join(metadata_root, METADATA_FILENAME)

    rows = []
    if os.path.exists(metadata_file):
        with open(metadata_file, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

    for row in rows:
        for field in METADATA_FIELDS:
            row.setdefault(field, "")

    current_id_number = int(get_next_item_id(rows))

    video_id = info.get("id", "") or ""
    video_title = info.get("title", "") or ""
    channel_id = info.get("channel_id", "") or ""
    channel_name = info.get("channel", "") or info.get("uploader", "") or ""

    # Chạy lại video sẽ cập nhật dòng cũ thay vì tạo bản ghi trùng.
    existing_by_key = {
        (str(row.get("video_id", "")), str(row.get("chapter_index", ""))): row
        for row in rows
    }

    added_count = 0
    updated_count = 0

    for index, chapter in enumerate(chapters, start=1):
        key = (str(video_id), str(index))
        title = chapter.get("title", "") or ""
        start_time = float(chapter["start_time"])
        end_time = float(chapter["end_time"])

        audio_file = os.path.join(
            chapter_dir,
            f"{index:02d} - {sanitize_filename(title)}.mp3",
        )
        transcript_file = (
            transcript_files[index - 1]
            if index <= len(transcript_files)
            else ""
        )

        row_data = {
            "video_id": video_id,
            "video_title": video_title,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "chapter_index": index,
            "chapter_title": title,
            "start_time": f"{start_time:.3f}",
            "end_time": f"{end_time:.3f}",
            "audio_path": format_metadata_path(audio_file, metadata_root),
            "transcript_path": format_metadata_path(transcript_file, metadata_root) if transcript_file else "",
        }

        if key in existing_by_key:
            existing_by_key[key].update(row_data)
            updated_count += 1
        else:
            row = {field: "" for field in METADATA_FIELDS}
            row["item_id"] = f"{current_id_number:03d}"
            current_id_number += 1
            row.update(row_data)
            rows.append(row)
            existing_by_key[key] = row
            added_count += 1

    with open(metadata_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=METADATA_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    log_callback(
        f"✓ metadata.csv: thêm {added_count} item, cập nhật {updated_count} item"
    )
    log_callback(f"  Metadata: {metadata_file}")
    return metadata_file


def get_video_info(url):
    """
    Lấy metadata của video bằng yt-dlp.

    Trả về:
        {
            "title": ...,
            "chapters": [...]
        }
    """

    command = [
        "yt-dlp",
        "-J",
        "--no-warnings",
        url
    ]

    output = run_command(command)

    try:
        info = json.loads(output)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Không thể đọc dữ liệu từ yt-dlp:\n{e}"
        )

    return info


# ============================================================
# Playlist detection / listing
# ============================================================

def is_playlist_url(url: str) -> bool:
    """Xác định URL có phải YouTube playlist hay không."""
    return (
        "list=" in url
        and (
            "youtube.com/playlist" in url
            or "youtube.com/watch" in url
            or "youtu.be" in url
        )
    )


def get_playlist_entries(url, log_callback):
    """
    Lấy danh sách video trong playlist bằng yt-dlp.
    Chỉ lấy metadata nhẹ ở bước này, chưa tải audio.
    """
    log_callback("URL là playlist. Đang lấy danh sách video...")

    command = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
        url
    ]

    output = run_command(command)

    try:
        playlist_info = json.loads(output)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Không thể đọc thông tin playlist:\n{e}"
        )

    entries = playlist_info.get("entries") or []

    if not entries:
        raise RuntimeError(
            "Playlist không có video hợp lệ."
        )

    result = []

    for position, entry in enumerate(entries, start=1):
        video_id = entry.get("id")

        if not video_id:
            continue

        # Với --flat-playlist, url có thể chỉ là ID.
        raw_url = entry.get("url")

        if raw_url and str(raw_url).startswith(("http://", "https://")):
            video_url = raw_url
        else:
            video_url = f"https://www.youtube.com/watch?v={video_id}"

        result.append({
            "position": position,
            "id": video_id,
            "title": entry.get("title") or f"Video {position}",
            "url": video_url
        })

    if not result:
        raise RuntimeError(
            "Không tìm thấy video nào trong playlist."
        )

    playlist_title = playlist_info.get("title") or "playlist"

    log_callback(f"Playlist: {playlist_title}")
    log_callback(f"Tìm thấy {len(result)} video.")
    log_callback("")

    return playlist_title, result


# ============================================================
# Download MP3
# ============================================================

def download_audio(url, output_dir, log_callback):
    """
    Download audio MP3 bằng yt-dlp.

    Trả về đường dẫn file MP3.
    """

    os.makedirs(output_dir, exist_ok=True)

    log_callback("Đang tải audio MP3...")

    # Lưu audio tạm vào thư mục download
    output_template = os.path.join(
        output_dir,
        "source.%(ext)s"
    )

    command = [
        "yt-dlp",

        "-x",
        "--audio-format",
        "mp3",

        # Giữ nguyên sleep interval theo command ban đầu
        "--sleep-interval",
        "3",

        # Output
        "-o",
        output_template,

        url
    ]

    # Hiển thị output của yt-dlp trực tiếp vào log
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    for line in process.stdout:
        line = line.strip()

        if line:
            log_callback(line)

    return_code = process.wait()

    if return_code != 0:
        raise RuntimeError(
            "yt-dlp không thể tải audio."
        )

    mp3_file = os.path.join(
        output_dir,
        "source.mp3"
    )

    if not os.path.exists(mp3_file):
        raise RuntimeError(
            "Không tìm thấy file MP3 sau khi tải."
        )

    log_callback("✓ Tải MP3 thành công")

    return mp3_file


# ============================================================
# Download original Vietnamese transcript
# ============================================================

def download_subtitle(url, output_dir, log_callback):
    """
    Tải phụ đề tiếng Việt gốc từ YouTube ở định dạng WebVTT.

    Trả về:
        - Đường dẫn source.vi.vtt nếu tải được và file tồn tại.
        - None nếu video không có transcript tiếng Việt hoặc không thể tải.

    Không raise error khi thiếu transcript vì process_url sẽ chuyển sang Whisper.
    """

    os.makedirs(output_dir, exist_ok=True)

    log_callback("Đang tải transcript tiếng Việt (.vi.vtt)...")

    output_template = os.path.join(
        output_dir,
        "source.%(ext)s"
    )

    command = [
        "yt-dlp",

        # Phụ đề do người đăng cung cấp
        "--write-subs",

        # Phụ đề tự động của YouTube
        "--write-auto-subs",

        # Chỉ lấy tiếng Việt
        "--sub-langs",
        "vi",

        # Không tải video/audio ở bước này
        "--skip-download",

        # Giữ sleep interval theo workflow ban đầu
        "--sleep-interval",
        "3",

        # Tên file output
        "-o",
        output_template,

        url
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    for line in process.stdout:
        line = line.strip()

        if line:
            log_callback(line)

    return_code = process.wait()

    subtitle_file = os.path.join(
        output_dir,
        "source.vi.vtt"
    )

    if return_code != 0:
        log_callback(
            "⚠ Không tải được transcript từ YouTube. "
            "Sẽ chuyển sang Whisper."
        )
        return None

    if not os.path.exists(subtitle_file):
        log_callback(
            "⚠ Video không có transcript tiếng Việt. "
            "Sẽ chuyển sang Whisper."
        )
        return None

    # Kiểm tra VTT có thực sự có cue transcript hay không.
    try:
        cues = parse_vtt_cues(subtitle_file)
    except Exception as e:
        log_callback(
            f"⚠ Không đọc được VTT ({e}). "
            "Sẽ chuyển sang Whisper."
        )
        return None

    if not cues:
        log_callback(
            "⚠ File VTT không có nội dung transcript hợp lệ. "
            "Sẽ chuyển sang Whisper."
        )
        return None

    log_callback("✓ Tải transcript thành công")

    return subtitle_file


# ============================================================
# Process VTT transcript into chapter TXT files
# ============================================================

def vtt_time_to_seconds(value: str) -> float:
    """Convert WebVTT timestamp HH:MM:SS.mmm or MM:SS.mmm to seconds."""
    value = value.strip().replace(',', '.')
    parts = value.split(':')

    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    else:
        raise ValueError(f"Timestamp VTT không hợp lệ: {value}")

    return float(hours) * 3600 + float(minutes) * 60 + float(seconds)


def clean_vtt_text(text: str) -> str:
    """Remove YouTube/WebVTT inline timing tags and formatting tags."""
    # Remove inline timestamp + <c> markers, e.g. <00:00:28.560><c>
    text = re.sub(r'<\d{2}:\d{2}:\d{2}[.,]\d{3}>', '', text)
    text = re.sub(r'</?c(?:\.[^>]*)?>', '', text)
    text = re.sub(r'<[^>]+>', '', text)

    # Decode common WebVTT entities
    text = (
        text.replace('&amp;', '&')
            .replace('&lt;', '<')
            .replace('&gt;', '>')
            .replace('&quot;', '"')
            .replace('&#39;', "'")
    )

    return re.sub(r'\s+', ' ', text).strip()


def parse_vtt_cues(vtt_file: str):
    """
    Parse WebVTT thành danh sách cue:
        {start, end, text}

    Bỏ header, cue settings và cue rỗng.
    """
    content = Path(vtt_file).read_text(encoding='utf-8-sig', errors='replace')
    blocks = re.split(r'\n\s*\n', content.replace('\r\n', '\n').replace('\r', '\n'))

    cues = []
    timestamp_pattern = re.compile(
        r'(\d{2}:\d{2}:\d{2}[.,]\d{3}|\d{2}:\d{2}[.,]\d{3})\s*-->\s*'
        r'(\d{2}:\d{2}:\d{2}[.,]\d{3}|\d{2}:\d{3}[.,]\d{3}|\d{2}:\d{2}[.,]\d{3})'
    )

    for block in blocks:
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if not lines:
            continue

        timestamp_index = None
        match = None
        for i, line in enumerate(lines):
            match = timestamp_pattern.search(line)
            if match:
                timestamp_index = i
                break

        if timestamp_index is None:
            continue

        start = vtt_time_to_seconds(match.group(1))
        end = vtt_time_to_seconds(match.group(2))
        text_lines = lines[timestamp_index + 1:]
        cue_text = clean_vtt_text(' '.join(text_lines))

        if cue_text:
            cues.append({
                'start': start,
                'end': end,
                'text': cue_text
            })

    return cues


def deduplicate_transcript_lines(texts):
    """
    Khử kiểu caption lặp/chồng của YouTube.

    Ví dụ:
        'Bạn cầm điện thoại lên'
        'Bạn cầm điện thoại lên, bạn chỉ định'

    chỉ giữ phần mới được thêm vào.
    """
    result = []
    previous = ''

    for text in texts:
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            continue

        if not previous:
            result.append(text)
            previous = text
            continue

        # Cue hoàn toàn giống cue trước -> bỏ.
        if text == previous:
            continue

        # Cue mới bắt đầu bằng cue trước -> chỉ lấy phần mới.
        if text.lower().startswith(previous.lower()):
            suffix = text[len(previous):].strip(' ,.-')
            if suffix:
                result.append(suffix)
            previous = text
            continue

        # Tìm overlap theo từ ở cuối cue trước / đầu cue hiện tại.
        prev_words = previous.split()
        curr_words = text.split()
        max_overlap = min(12, len(prev_words), len(curr_words))
        overlap = 0

        for n in range(max_overlap, 1, -1):
            if [w.lower().strip('.,!?;:') for w in prev_words[-n:]] == [w.lower().strip('.,!?;:') for w in curr_words[:n]]:
                overlap = n
                break

        if overlap:
            new_part = ' '.join(curr_words[overlap:]).strip(' ,.-')
            if new_part:
                result.append(new_part)
        else:
            result.append(text)

        previous = text

    return ' '.join(result).strip()


def create_chapter_transcripts(vtt_file, chapters, chapter_dir, log_callback):
    """
    Từ source.vi.vtt tạo .txt tương ứng với từng chapter.
    """
    if not os.path.exists(vtt_file):
        raise RuntimeError(f"Không tìm thấy VTT: {vtt_file}")

    log_callback("Đang xử lý transcript theo chapter...")

    cues = parse_vtt_cues(vtt_file)

    if not cues:
        raise RuntimeError("Không tìm thấy nội dung transcript hợp lệ trong VTT.")

    txt_files = []

    for index, chapter in enumerate(chapters, start=1):
        chapter_start = float(chapter['start_time'])
        chapter_end = float(chapter['end_time'])
        title = sanitize_filename(chapter['title'])

        chapter_texts = []

        for cue in cues:
            # Lấy cue nếu nó giao với khoảng thời gian chapter.
            if cue['end'] > chapter_start and cue['start'] < chapter_end:
                chapter_texts.append(cue['text'])

        transcript = deduplicate_transcript_lines(chapter_texts)

        txt_file = os.path.join(
            chapter_dir,
            f"{index:02d} - {title}.txt"
        )

        Path(txt_file).write_text(
            transcript,
            encoding='utf-8'
        )

        txt_files.append(txt_file)

        if transcript:
            log_callback(
                f"    ✓ Transcript: {os.path.basename(txt_file)}"
            )
        else:
            log_callback(
                f"    ⚠ Transcript rỗng: {os.path.basename(txt_file)}"
            )

    return txt_files


# ============================================================
# Whisper fallback
# ============================================================

def transcribe_with_whisper(
    mp3_file,
    chapters,
    chapter_dir,
    log_callback
):
    """
    Dùng OpenAI Whisper khi YouTube không cung cấp transcript.

    Whisper tạo các segment:
        {
            start: float,
            end: float,
            text: str
        }

    Sau đó các segment được phân bổ vào từng chapter.
    """

    try:
        import whisper
    except ImportError:
        raise RuntimeError(
            "Chưa cài Whisper.\n\n"
            "Hãy chạy:\n"
            "pip install -U openai-whisper"
        )

    log_callback(
        f"Đang dùng Whisper model '{WHISPER_MODEL}' "
        "để tạo transcript..."
    )

    try:
        model = whisper.load_model(WHISPER_MODEL)
    except Exception as e:
        raise RuntimeError(
            f"Không thể tải Whisper model '{WHISPER_MODEL}':\n{e}"
        )

    log_callback("Đang nhận dạng tiếng Việt từ source.mp3...")

    try:
        result = model.transcribe(
            mp3_file,
            language=WHISPER_LANGUAGE,
            task="transcribe",
            fp16=False,
            verbose=False
        )
    except Exception as e:
        raise RuntimeError(
            f"Whisper không thể nhận dạng audio:\n{e}"
        )

    segments = result.get("segments", [])

    if not segments:
        raise RuntimeError(
            "Whisper không nhận dạng được nội dung từ audio."
        )

    # Chuyển về format giống parse_vtt_cues để tái sử dụng logic.
    cues = []

    for segment in segments:
        text = clean_vtt_text(
            str(segment.get("text", ""))
        )

        if not text:
            continue

        cues.append({
            "start": float(segment.get("start", 0)),
            "end": float(segment.get("end", 0)),
            "text": text
        })

    if not cues:
        raise RuntimeError(
            "Whisper trả về các segment nhưng không có text hợp lệ."
        )

    log_callback(
        f"✓ Whisper nhận dạng {len(cues)} đoạn thoại"
    )

    txt_files = []

    for index, chapter in enumerate(chapters, start=1):
        chapter_start = float(chapter["start_time"])
        chapter_end = float(chapter["end_time"])
        title = sanitize_filename(chapter["title"])

        chapter_texts = []

        for cue in cues:
            # Segment giao với khoảng thời gian của chapter.
            if cue["end"] > chapter_start and cue["start"] < chapter_end:
                chapter_texts.append(cue["text"])

        transcript = deduplicate_transcript_lines(
            chapter_texts
        )

        txt_file = os.path.join(
            chapter_dir,
            f"{index:02d} - {title}.txt"
        )

        Path(txt_file).write_text(
            transcript,
            encoding="utf-8"
        )

        txt_files.append(txt_file)

        if transcript:
            log_callback(
                f"    ✓ Whisper transcript: "
                f"{os.path.basename(txt_file)}"
            )
        else:
            log_callback(
                f"    ⚠ Whisper transcript rỗng: "
                f"{os.path.basename(txt_file)}"
            )

    # Lưu transcript Whisper đầy đủ để có dữ liệu trung gian.
    full_whisper_file = os.path.join(
        os.path.dirname(mp3_file),
        "source.whisper.txt"
    )

    full_text = deduplicate_transcript_lines(
        [cue["text"] for cue in cues]
    )

    Path(full_whisper_file).write_text(
        full_text,
        encoding="utf-8"
    )

    log_callback(
        f"✓ Đã lưu transcript Whisper: "
        f"{os.path.basename(full_whisper_file)}"
    )

    return txt_files


# ============================================================
# Cut chapters
# ============================================================

def cut_chapters(
    mp3_file,
    chapters,
    output_dir,
    log_callback
):
    """
    Cắt MP3 thành từng chapter bằng FFmpeg.
    """

    chapter_dir = os.path.join(
        output_dir,
        "chapters"
    )

    os.makedirs(chapter_dir, exist_ok=True)

    total = len(chapters)

    for index, chapter in enumerate(chapters, start=1):

        start_time = float(
            chapter["start_time"]
        )

        end_time = float(
            chapter["end_time"]
        )

        title = sanitize_filename(
            chapter["title"]
        )

        duration = end_time - start_time

        output_file = os.path.join(
            chapter_dir,
            f"{index:02d} - {title}.mp3"
        )

        log_callback(
            f"[{index}/{total}] "
            f"{title} "
            f"({start_time:.0f}s → {end_time:.0f}s)"
        )

        command = [
            "ffmpeg",

            "-y",

            # Start position
            "-ss",
            str(start_time),

            # Input
            "-i",
            mp3_file,

            # Duration
            "-t",
            str(duration),

            # Audio only
            "-vn",

            # MP3 encoder
            "-c:a",
            "libmp3lame",

            # High quality
            "-q:a",
            "2",

            output_file
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Lỗi khi cắt chapter:\n"
                f"{title}\n\n"
                f"{result.stderr}"
            )

        log_callback(
            f"    ✓ {os.path.basename(output_file)}"
        )

    return chapter_dir


# ============================================================
# Main processing
# ============================================================

def process_video_url(url, base_output_dir, log_callback):

    # --------------------------------------------------------
    # 1. Get metadata
    # --------------------------------------------------------

    log_callback("Đang lấy thông tin video...")
    info = get_video_info(url)

    title = info.get("title", "audio")
    chapters = info.get("chapters")

    if not chapters:
        raise RuntimeError("Video không có chapter.")

    log_callback(f"Tiêu đề: {title}")
    log_callback(f"Tìm thấy {len(chapters)} chapter")
    log_callback("")

    # --------------------------------------------------------
    # 2. Create output folder
    # --------------------------------------------------------

    safe_title = sanitize_filename(title)
    output_dir = os.path.join(base_output_dir, safe_title)
    os.makedirs(output_dir, exist_ok=True)

    # --------------------------------------------------------
    # 3. Download MP3
    # --------------------------------------------------------

    mp3_file = download_audio(url, output_dir, log_callback)
    log_callback("")

    # --------------------------------------------------------
    # 4. Download Vietnamese transcript
    # --------------------------------------------------------

    subtitle_file = download_subtitle(url, output_dir, log_callback)
    log_callback(f"Transcript: {subtitle_file}")
    log_callback("")

    # --------------------------------------------------------
    # 5. Cut chapters
    # --------------------------------------------------------

    chapter_dir = cut_chapters(
        mp3_file, chapters, output_dir, log_callback
    )
    log_callback("")

    # --------------------------------------------------------
    # 6. Create TXT transcript for each chapter
    # --------------------------------------------------------

    if subtitle_file:
        transcript_files = create_chapter_transcripts(
            subtitle_file, chapters, chapter_dir, log_callback
        )
    else:
        transcript_files = transcribe_with_whisper(
            mp3_file, chapters, chapter_dir, log_callback
        )

    log_callback("")

    # --------------------------------------------------------
    # 7. Create/update metadata.csv
    # --------------------------------------------------------

    update_metadata_csv(
        base_output_dir,
        info,
        chapters,
        chapter_dir,
        transcript_files,
        log_callback,
    )

    log_callback("")
    log_callback("========================================")
    log_callback("✓ HOÀN THÀNH")
    log_callback(f"Output: {chapter_dir}")
    log_callback(
        f"Metadata: {os.path.join(base_output_dir, METADATA_FILENAME)}"
    )
    log_callback("========================================")


# ============================================================
# Playlist processing
# ============================================================

def process_playlist(url, base_output_dir, log_callback):
    """
    Xử lý tuần tự toàn bộ video trong playlist.

    Một video lỗi sẽ được ghi log và bỏ qua,
    các video còn lại vẫn tiếp tục được xử lý.
    """

    playlist_title, entries = get_playlist_entries(
        url,
        log_callback
    )

    # Các video của playlist nằm trực tiếp trong thư mục output đã chọn.
    # metadata.csv dùng chung ở thư mục output gốc.
    playlist_dir = base_output_dir

    os.makedirs(
        playlist_dir,
        exist_ok=True
    )

    total = len(entries)
    success_count = 0
    failed_count = 0

    for index, entry in enumerate(entries, start=1):

        log_callback(
            "========================================"
        )
        log_callback(
            f"VIDEO {index}/{total}: {entry['title']}"
        )
        log_callback(
            f"URL: {entry['url']}"
        )
        log_callback(
            "========================================"
        )

        try:
            process_video_url(
                entry["url"],
                playlist_dir,
                log_callback
            )
            success_count += 1

        except Exception as e:
            failed_count += 1

            log_callback(
                f"✗ Bỏ qua video {index}: {e}"
            )

        log_callback("")

    log_callback(
        "========================================"
    )
    log_callback(
        "✓ PLAYLIST HOÀN THÀNH"
    )
    log_callback(
        f"Thành công: {success_count}/{total}"
    )
    log_callback(
        f"Thất bại: {failed_count}/{total}"
    )
    log_callback(
        f"Output: {playlist_dir}"
    )
    log_callback(
        "========================================"
    )


# ============================================================
# URL dispatcher
# ============================================================

def process_input_url(url, base_output_dir, log_callback):
    """
    Tự động nhận biết URL là video đơn hay playlist.
    """

    if is_playlist_url(url):
        process_playlist(
            url,
            base_output_dir,
            log_callback
        )
    else:
        process_video_url(
            url,
            base_output_dir,
            log_callback
        )


# ============================================================
# GUI
# ============================================================

class AudioChapterCutter:

    def __init__(self, root):

        self.root = root

        root.title(
            "YouTube Audio Chapter Cutter"
        )

        root.geometry(
            "800x600"
        )

        # ====================================================
        # URL
        # ====================================================

        tk.Label(
            root,
            text="YouTube URL",
            font=("Arial", 12, "bold")
        ).pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        url_frame = tk.Frame(root)

        url_frame.pack(
            fill="x",
            padx=15
        )

        self.url_entry = tk.Entry(
            url_frame,
            font=("Arial", 11)
        )

        self.url_entry.pack(
            fill="x",
            expand=True,
            side="left"
        )

        # ====================================================
        # Output directory
        # ====================================================

        tk.Label(
            root,
            text="Thư mục lưu",
            font=("Arial", 12, "bold")
        ).pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        output_frame = tk.Frame(root)

        output_frame.pack(
            fill="x",
            padx=15
        )

        self.output_entry = tk.Entry(
            output_frame,
            font=("Arial", 11)
        )

        self.output_entry.pack(
            fill="x",
            expand=True,
            side="left"
        )

        # Mặc định lưu cạnh script
        default_output = os.path.join(
            os.getcwd(),
            "output"
        )

        self.output_entry.insert(
            0,
            default_output
        )

        tk.Button(
            output_frame,
            text="Chọn",
            command=self.select_output
        ).pack(
            side="left",
            padx=(10, 0)
        )

        # ====================================================
        # Log
        # ====================================================

        tk.Label(
            root,
            text="Log",
            font=("Arial", 12, "bold")
        ).pack(
            anchor="w",
            padx=15,
            pady=(15, 5)
        )

        self.log_text = scrolledtext.ScrolledText(
            root,
            height=20,
            wrap=tk.WORD,
            state="disabled"
        )

        self.log_text.pack(
            fill="both",
            expand=True,
            padx=15
        )

        # ====================================================
        # Start button
        # ====================================================

        self.start_button = tk.Button(
            root,
            text="TẢI & CẮT AUDIO",
            font=("Arial", 12, "bold"),
            height=2,
            command=self.start
        )

        self.start_button.pack(
            fill="x",
            padx=15,
            pady=15
        )

    # ========================================================
    # Output folder
    # ========================================================

    def select_output(self):

        folder = filedialog.askdirectory(
            title="Chọn thư mục output"
        )

        if folder:

            self.output_entry.delete(
                0,
                tk.END
            )

            self.output_entry.insert(
                0,
                folder
            )

    # ========================================================
    # Log
    # ========================================================

    def log(self, message):

        self.log_text.config(
            state="normal"
        )

        self.log_text.insert(
            tk.END,
            message + "\n"
        )

        self.log_text.see(
            tk.END
        )

        self.log_text.config(
            state="disabled"
        )

        self.root.update_idletasks()

    # ========================================================
    # Start
    # ========================================================

    def start(self):

        url = self.url_entry.get().strip()

        output_dir = (
            self.output_entry.get().strip()
        )

        if not url:

            messagebox.showerror(
                "Lỗi",
                "Vui lòng nhập YouTube URL."
            )

            return

        if not output_dir:

            messagebox.showerror(
                "Lỗi",
                "Vui lòng chọn thư mục lưu."
            )

            return

        # Clear log
        self.log_text.config(
            state="normal"
        )

        self.log_text.delete(
            "1.0",
            tk.END
        )

        self.log_text.config(
            state="disabled"
        )

        self.start_button.config(
            state="disabled"
        )

        self.log(
            "Bắt đầu xử lý..."
        )

        # Chạy background thread để GUI không bị treo
        thread = threading.Thread(
            target=self.run_process,
            args=(url, output_dir),
            daemon=True
        )

        thread.start()

    # ========================================================
    # Background process
    # ========================================================

    def run_process(
        self,
        url,
        output_dir
    ):

        try:

            process_input_url(
                url,
                output_dir,
                self.log
            )

            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Hoàn thành",
                    "Đã tải và cắt toàn bộ chapter."
                )
            )

        except Exception as e:

            self.log("")
            self.log(
                f"✗ ERROR: {e}"
            )

            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Lỗi",
                    str(e)
                )
            )

        finally:

            self.root.after(
                0,
                lambda: self.start_button.config(
                    state="normal"
                )
            )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = AudioChapterCutter(root)

    root.mainloop()
