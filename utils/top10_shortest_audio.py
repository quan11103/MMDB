from __future__ import annotations

import argparse
from pathlib import Path

from mutagen.mp3 import MP3
from mutagen import MutagenError


def format_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm."""
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}.{milliseconds:03}"


def get_audio_duration(file_path: Path) -> float | None:
    """Return MP3 duration in seconds, or None if it cannot be read."""
    try:
        audio = MP3(file_path)
        if audio.info is None or audio.info.length <= 0:
            return None
        return float(audio.info.length)
    except (MutagenError, OSError, ValueError) as exc:
        print(f"[WARN] Không đọc được '{file_path}': {exc}")
        return None


def find_shortest_items(dataset_dir: Path, limit: int) -> list[tuple[float, Path]]:
    results: list[tuple[float, Path]] = []

    for file_path in dataset_dir.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() != ".mp3":
            continue

        # source.mp3 là audio gốc của video, không phải chapter item trong dataset.
        if file_path.name.lower() == "source.mp3":
            continue

        duration = get_audio_duration(file_path)
        if duration is not None:
            results.append((duration, file_path))

    results.sort(key=lambda item: (item[0], str(item[1]).lower()))
    return results[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Liệt kê các audio item MP3 có thời lượng ngắn nhất trong dataset."
    )
    parser.add_argument(
        "dataset",
        type=Path,
        help="Đường dẫn đến thư mục dataset chứa các chapter MP3.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Số item cần hiển thị (mặc định: 10).",
    )
    args = parser.parse_args()

    dataset_dir = args.dataset.expanduser().resolve()
    if not dataset_dir.exists():
        parser.error(f"Thư mục không tồn tại: {dataset_dir}")
    if not dataset_dir.is_dir():
        parser.error(f"Đường dẫn không phải thư mục: {dataset_dir}")
    if args.top <= 0:
        parser.error("--top phải là số nguyên lớn hơn 0.")

    items = find_shortest_items(dataset_dir, args.top)

    if not items:
        print("Không tìm thấy file MP3 hợp lệ trong dataset.")
        return 0

    print(f"\n{len(items)} item có thời lượng ngắn nhất:\n")
    print(f"{'STT':<5}{'Thời lượng':<18}Đường dẫn tương đối")
    print("-" * 90)

    for index, (duration, file_path) in enumerate(items, start=1):
        relative_path = file_path.relative_to(dataset_dir)
        print(f"{index:<5}{format_duration(duration):<18}{relative_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
