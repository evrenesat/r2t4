import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from frame_selector import (
    analyze_video_lowres,
    build_adaptive_chunks,
    build_diagnostics_summary,
    derive_thresholds,
    select_chunk_frames,
)
from subtitle_ingestion import SUBTITLES_DIRNAME, export_embedded_subtitles

VIDEO_PATH = "/Volumes/DEPO/r2d4-test/movies/DexterOriginalSin-S01E03-MiamiVice.mkv"
OUTPUT_DIR = "output"

PRESETS = {
    "balanced": {
        "SCENE_THRESHOLD": 0.4,
        "ANALYSIS_FPS": 2.0,
        "ANALYSIS_WIDTH": 128,
        "MIN_CHUNK_SEC": 4.0,
        "MAX_CHUNK_SEC": 15.0,
        "CUT_MERGE_SEC": 1.5,
        "MIN_FRAME_DISTANCE": 6,
        "BLACK_FRAME_LUMA_THRESHOLD": 18.0,
    },
    "high_recall": {
        "SCENE_THRESHOLD": 0.34,
        "ANALYSIS_FPS": 2.5,
        "ANALYSIS_WIDTH": 160,
        "MIN_CHUNK_SEC": 3.5,
        "MAX_CHUNK_SEC": 12.0,
        "CUT_MERGE_SEC": 1.2,
        "MIN_FRAME_DISTANCE": 5,
        "BLACK_FRAME_LUMA_THRESHOLD": 15.0,
    },
    "aggressive_reduction": {
        "SCENE_THRESHOLD": 0.45,
        "ANALYSIS_FPS": 1.5,
        "ANALYSIS_WIDTH": 112,
        "MIN_CHUNK_SEC": 5.0,
        "MAX_CHUNK_SEC": 18.0,
        "CUT_MERGE_SEC": 1.8,
        "MIN_FRAME_DISTANCE": 7,
        "BLACK_FRAME_LUMA_THRESHOLD": 20.0,
    },
}

PRESET = "balanced"
SCENE_THRESHOLD = PRESETS[PRESET]["SCENE_THRESHOLD"]
ANALYSIS_FPS = PRESETS[PRESET]["ANALYSIS_FPS"]
ANALYSIS_WIDTH = PRESETS[PRESET]["ANALYSIS_WIDTH"]
MIN_CHUNK_SEC = PRESETS[PRESET]["MIN_CHUNK_SEC"]
MAX_CHUNK_SEC = PRESETS[PRESET]["MAX_CHUNK_SEC"]
CUT_MERGE_SEC = PRESETS[PRESET]["CUT_MERGE_SEC"]
MIN_FRAME_DISTANCE = PRESETS[PRESET]["MIN_FRAME_DISTANCE"]
BLACK_FRAME_LUMA_THRESHOLD = PRESETS[PRESET]["BLACK_FRAME_LUMA_THRESHOLD"]
ENABLE_DIAGNOSTICS = True

GRID_COLS = 2
GRID_ROWS = 2
MAX_EDGE = 512
MAX_WORKERS = 4
GRIDS_DIRNAME = "grids"


def runtime_config() -> dict[str, Any]:
    return {
        "PRESET": PRESET,
        "SCENE_THRESHOLD": SCENE_THRESHOLD,
        "ANALYSIS_FPS": ANALYSIS_FPS,
        "ANALYSIS_WIDTH": ANALYSIS_WIDTH,
        "MIN_CHUNK_SEC": MIN_CHUNK_SEC,
        "MAX_CHUNK_SEC": MAX_CHUNK_SEC,
        "CUT_MERGE_SEC": CUT_MERGE_SEC,
        "MIN_FRAME_DISTANCE": MIN_FRAME_DISTANCE,
        "BLACK_FRAME_LUMA_THRESHOLD": BLACK_FRAME_LUMA_THRESHOLD,
        "ENABLE_DIAGNOSTICS": ENABLE_DIAGNOSTICS,
    }


def get_file_hash(filepath: str) -> str:
    print("Calculating file hash for caching...")
    hasher = hashlib.md5()
    with open(filepath, "rb") as handle:
        for chunk in iter(lambda: handle.read(4096 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_scene_changes(video_path: str, output_dir: str, threshold: float) -> list[float]:
    file_hash = get_file_hash(video_path)
    cache_filename = f"probe_cache_{file_hash}_thresh_{threshold}.txt"
    cache_path = os.path.join(output_dir, cache_filename)

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()

        if lines and lines[0].strip() == "NO_SCENES":
            print("Cache indicates zero scene cuts. Proceeding with single scene.")
            return []

        if lines and lines[0].strip() != "":
            print(f"Cache found. Loading scene analysis from {cache_filename}")
            return [float(line.strip()) for line in lines if line.strip()]

        print("Empty cache file detected. Re-running probe...")

    print("Detecting scene changes... This may take a few minutes.")
    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-vf",
        f"select='gt(scene,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    timestamps = [float(match) for match in re.findall(r"pts_time:([0-9.]+)", result.stderr)]

    print(f"Saving {len(timestamps)} scene changes to cache...")
    with open(cache_path, "w", encoding="utf-8") as handle:
        if timestamps:
            for timestamp in timestamps:
                handle.write(f"{timestamp}\n")
        else:
            handle.write("NO_SCENES\n")

    return timestamps


def merge_scene_cuts(scene_cuts: list[float], merge_window_sec: float) -> list[dict[str, Any]]:
    if not scene_cuts:
        return []

    regions: list[dict[str, Any]] = []
    current = {
        "start": scene_cuts[0],
        "end": scene_cuts[0],
        "cuts": [scene_cuts[0]],
    }

    for cut in scene_cuts[1:]:
        if cut - current["end"] <= merge_window_sec:
            current["end"] = cut
            current["cuts"].append(cut)
            continue
        regions.append(current)
        current = {"start": cut, "end": cut, "cuts": [cut]}

    regions.append(current)
    return regions


def get_video_duration(video_path: str) -> float:
    cmd_format = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd_format, stdout=subprocess.PIPE, text=True, check=True)
    output = result.stdout.strip()

    if not output or output == "N/A":
        cmd_stream = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        result = subprocess.run(cmd_stream, stdout=subprocess.PIPE, text=True, check=True)
        output = result.stdout.strip()

    if not output or output == "N/A":
        raise RuntimeError(f"ffprobe could not extract duration from {video_path}.")

    return float(output)


def extract_frame(video_path: str, timestamp: float, output_path: str) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(timestamp),
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        output_path,
    ]
    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    if not os.path.exists(output_path):
        raise RuntimeError(f"ffmpeg did not produce {output_path}")


def create_grid(image_paths: list[str], output_path: str) -> None:
    images = []
    for image_path in image_paths:
        image = Image.open(image_path)
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
        images.append(image.copy())
        image.close()

    frame_width, frame_height = images[0].size
    grid_width = GRID_COLS * frame_width
    grid_height = GRID_ROWS * frame_height
    grid_image = Image.new("RGB", (grid_width, grid_height))

    for index, image in enumerate(images):
        row = index // GRID_COLS
        col = index % GRID_COLS
        grid_image.paste(image, (col * frame_width, row * frame_height))

    grid_image.save(output_path)


def safe_timestamp_label(value: float) -> str:
    return f"{value:.1f}".replace(".", "_")


def ensure_output_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def make_run_output_dir(base_output_dir: str, preset: str) -> str:
    ensure_output_dir(base_output_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base_name = f"run_{preset}_{timestamp}"
    run_dir = os.path.join(base_output_dir, base_name)
    suffix = 2
    while os.path.exists(run_dir):
        run_dir = os.path.join(base_output_dir, f"{base_name}_v{suffix}")
        suffix += 1
    os.makedirs(run_dir)
    return run_dir


def write_manifest_line(handle: Any, record: dict[str, Any]) -> None:
    handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def process_video() -> None:
    ensure_output_dir(OUTPUT_DIR)
    config = runtime_config()
    run_output_dir = make_run_output_dir(OUTPUT_DIR, config["PRESET"])
    grids_output_dir = os.path.join(run_output_dir, GRIDS_DIRNAME)
    subtitles_output_dir = os.path.join(run_output_dir, SUBTITLES_DIRNAME)
    ensure_output_dir(grids_output_dir)
    ensure_output_dir(subtitles_output_dir)
    print(f"Writing run outputs to {run_output_dir}")

    phase_timings: dict[str, float] = {
        "duration_lookup": 0.0,
        "scene_cut_probe": 0.0,
        "subtitle_export": 0.0,
        "low_res_analysis": 0.0,
        "chunk_building": 0.0,
        "full_res_extraction": 0.0,
        "grid_writing": 0.0,
    }

    started = time.perf_counter()
    total_duration = get_video_duration(VIDEO_PATH)
    phase_timings["duration_lookup"] = time.perf_counter() - started

    started = time.perf_counter()
    scene_cuts = get_scene_changes(VIDEO_PATH, OUTPUT_DIR, config["SCENE_THRESHOLD"])
    cut_regions = merge_scene_cuts(scene_cuts, config["CUT_MERGE_SEC"])
    phase_timings["scene_cut_probe"] = time.perf_counter() - started

    started = time.perf_counter()
    exported_subtitles = export_embedded_subtitles(
        Path(VIDEO_PATH), Path(subtitles_output_dir)
    )
    phase_timings["subtitle_export"] = time.perf_counter() - started

    started = time.perf_counter()
    analyzed_frames = analyze_video_lowres(
        VIDEO_PATH,
        config["ANALYSIS_FPS"],
        config["ANALYSIS_WIDTH"],
        config["BLACK_FRAME_LUMA_THRESHOLD"],
    )
    thresholds = derive_thresholds(analyzed_frames, config)
    phase_timings["low_res_analysis"] = time.perf_counter() - started

    started = time.perf_counter()
    chunks = build_adaptive_chunks(
        total_duration,
        analyzed_frames,
        scene_cuts,
        cut_regions,
        config,
        thresholds,
    )
    phase_timings["chunk_building"] = time.perf_counter() - started

    manifest_path = os.path.join(run_output_dir, "manifest.jsonl")
    diagnostics_path = os.path.join(run_output_dir, "diagnostics.json")
    low_variation_count = 0

    with open(manifest_path, "w", encoding="utf-8") as manifest_handle:
        for chunk in chunks:
            selected_frames, low_variation = select_chunk_frames(
                chunk,
                analyzed_frames,
                scene_cuts,
                thresholds,
                config,
            )
            if low_variation:
                low_variation_count += 1

            safe_start = safe_timestamp_label(chunk.start)
            safe_end = safe_timestamp_label(chunk.end)
            grid_filename = f"scene{chunk.chunk_index}_chunk1_{safe_start}s_to_{safe_end}s.jpg"
            grid_filepath = os.path.join(grids_output_dir, grid_filename)
            temp_images: list[str] = []

            started = time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for frame_idx, selected in enumerate(selected_frames):
                    temp_path = os.path.join(run_output_dir, f"temp_chunk{chunk.chunk_index}_frame{frame_idx}.jpg")
                    temp_images.append(temp_path)
                    futures.append(
                        executor.submit(extract_frame, VIDEO_PATH, selected.timestamp, temp_path)
                    )
                concurrent.futures.wait(futures)
                for future in futures:
                    future.result()
            phase_timings["full_res_extraction"] += time.perf_counter() - started

            started = time.perf_counter()
            create_grid(temp_images, grid_filepath)
            phase_timings["grid_writing"] += time.perf_counter() - started
            print(f"Created {grid_filename}")

            for temp_image in temp_images:
                if os.path.exists(temp_image):
                    os.remove(temp_image)

            write_manifest_line(
                manifest_handle,
                {
                    "grid_filename": grid_filename,
                    "chunk_start": chunk.start,
                    "chunk_end": chunk.end,
                    "selected_timestamps": [frame.timestamp for frame in selected_frames],
                    "selected_scores": [frame.score for frame in selected_frames],
                    "preset": config["PRESET"],
                    "activity_class": chunk.activity_class,
                    "low_variation": low_variation,
                    "source_scene_cut_times": chunk.source_scene_cut_times,
                },
            )

    diagnostics_summary = build_diagnostics_summary(
        chunks=chunks,
        thresholds=thresholds,
        candidate_frame_count=len(analyzed_frames),
        low_variation_chunk_count=low_variation_count,
    )
    diagnostics_payload = diagnostics_summary.to_dict()
    diagnostics_payload.update(
        {
            "video_duration": total_duration,
            "analysis_fps": config["ANALYSIS_FPS"],
            "grid_count": len(chunks),
            "phase_timings_sec": phase_timings,
            "preset": config["PRESET"],
            "run_output_dir": run_output_dir,
            "grids_output_dir": grids_output_dir,
            "subtitles_output_dir": subtitles_output_dir,
            "exported_subtitle_count": len(exported_subtitles),
            "exported_subtitles": [subtitle.to_dict() for subtitle in exported_subtitles],
            "merged_cut_region_count": len(cut_regions),
        }
    )

    if config["ENABLE_DIAGNOSTICS"]:
        with open(diagnostics_path, "w", encoding="utf-8") as diagnostics_handle:
            json.dump(diagnostics_payload, diagnostics_handle, indent=2)


if __name__ == "__main__":
    process_video()
