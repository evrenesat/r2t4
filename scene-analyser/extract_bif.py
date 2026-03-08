#!/usr/bin/env python3

import struct
import sys
from pathlib import Path


def extract_bif(bif_path: Path) -> Path:
    data = bif_path.read_bytes()

    if data[:8] != b"\x89BIF\r\n\x1a\n":
        raise ValueError(f"Not a valid BIF file: {bif_path}")

    version = struct.unpack_from("<I", data, 8)[0]
    count = struct.unpack_from("<I", data, 12)[0]
    multiplier = struct.unpack_from("<I", data, 16)[
        0
    ]  # milliseconds per timestamp unit

    index_offset = 64
    entries = []
    for i in range(count + 1):
        timestamp, offset = struct.unpack_from("<II", data, index_offset + i * 8)
        entries.append((timestamp, offset))

    out_dir = bif_path.parent / f"{bif_path.stem}_bif_frames"
    out_dir.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        timestamp, start = entries[i]
        _, end = entries[i + 1]
        jpg_bytes = data[start:end]

        seconds = int(timestamp * multiplier / 1000)
        out_file = out_dir / f"{i:03d}_{seconds:06d}s.jpg"
        out_file.write_bytes(jpg_bytes)

    info_file = out_dir / "info.txt"
    info_file.write_text(
        "\n".join(
            [
                f"source={bif_path}",
                f"version={version}",
                f"count={count}",
                f"multiplier_ms={multiplier}",
                f"output_dir={out_dir}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return out_dir


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} /path/to/file.bif", file=sys.stderr)
        return 1

    bif_path = Path(sys.argv[1]).expanduser().resolve()

    if not bif_path.exists():
        print(f"File does not exist: {bif_path}", file=sys.stderr)
        return 2

    if not bif_path.is_file():
        print(f"Not a file: {bif_path}", file=sys.stderr)
        return 3

    try:
        out_dir = extract_bif(bif_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 4

    print(f"Extracted thumbnails to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
