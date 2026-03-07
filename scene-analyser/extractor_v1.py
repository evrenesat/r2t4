from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
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
from pipeline_config import PipelineConfig
from subtitle_ingestion import SUBTITLES_DIRNAME, export_available_subtitles

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

GRID_COLS = 2
GRID_ROWS = 2
MAX_EDGE = 512
MAX_WORKERS = 4
GRIDS_DIRNAME = "grids"


@dataclass(frozen=True)
class ExtractorRunConfig:
    config_path: Path
    profile: str
    video_path: Path | None


def parse_args() -> ExtractorRunConfig:
    parser = argparse.ArgumentParser(description="Extract scene grids from a title.")
    parser.add_argument("--config", default="config/pipeline.toml")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--video-path")
    args = parser.parse_args()
    return ExtractorRunConfig(
        config_path=Path(args.config),
        profile=args.profile,
        video_path=Path(args.video_path) if args.video_path else None,
    )


def runtime_config(
    pipeline_config: PipelineConfig,
    video_path_override: Path | None,
) -> dict[str, Any]:
    preset_name = pipeline_config.extractor_config.preset
    try:
        preset = PRESETS[preset_name]
    except KeyError as error:
        raise ValueError(f"Unknown preset '{preset_name}'.") from error
    return {
        "VIDEO_PATH": str(pipeline_config.resolve_video_path(video_path_override)),
        "OUTPUT_DIR": pipeline_config.extractor_config.output_dir,
        "PRESET": preset_name,
        "SCENE_THRESHOLD": preset["SCENE_THRESHOLD"],
        "ANALYSIS_FPS": preset["ANALYSIS_FPS"],
        "ANALYSIS_WIDTH": preset["ANALYSIS_WIDTH"],
        "MIN_CHUNK_SEC": preset["MIN_CHUNK_SEC"],
        "MAX_CHUNK_SEC": preset["MAX_CHUNK_SEC"],
        "CUT_MERGE_SEC": preset["CUT_MERGE_SEC"],
        "MIN_FRAME_DISTANCE": preset["MIN_FRAME_DISTANCE"],
        "BLACK_FRAME_LUMA_THRESHOLD": preset["BLACK_FRAME_LUMA_THRESHOLD"],
        "ENABLE_DIAGNOSTICS": pipeline_config.extractor_config.enable_diagnostics,
        "ALLOW_SUBLIMINAL_DOWNLOAD": pipeline_config.subtitle_ingestion_config.allow_subliminal_download,
        "SUBTITLE_LANGUAGE": pipeline_config.subtitle_ingestion_config.subtitle_language,
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


def process_video(run_config: ExtractorRunConfig) -> None:
    pipeline_config = PipelineConfig(run_config.config_path, run_config.profile)
    config = runtime_config(pipeline_config, run_config.video_path)
    ensure_output_dir(str(config["OUTPUT_DIR"]))
    run_output_dir = make_run_output_dir(str(config["OUTPUT_DIR"]), str(config["PRESET"]))
    grids_output_dir = os.path.join(run_output_dir, GRIDS_DIRNAME)
    subtitles_output_dir = os.path.join(run_output_dir, SUBTITLES_DIRNAME)
    ensure_output_dir(grids_output_dir)
    ensure_output_dir(subtitles_output_dir)
    print(f"Writing run outputs to {run_output_dir}")

    phase_timings: dict[str, float] = {
        "duration_lookup": 0.0,
        "parallel_analysis": 0.0,
        "chunk_building": 0.0,
        "full_res_extraction": 0.0,
        "grid_writing": 0.0,
        "summary_precompute": 0.0,
    }

    started = time.perf_counter()
    total_duration = get_video_duration(str(config["VIDEO_PATH"]))
    phase_timings["duration_lookup"] = time.perf_counter() - started

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_scenes = executor.submit(
            get_scene_changes,
            str(config["VIDEO_PATH"]),
            str(config["OUTPUT_DIR"]),
            float(config["SCENE_THRESHOLD"]),
        )
        future_subs = executor.submit(
            export_available_subtitles,
            Path(str(config["VIDEO_PATH"])),
            Path(subtitles_output_dir),
            subtitle_language=str(config["SUBTITLE_LANGUAGE"]),
            allow_subliminal_download=bool(config["ALLOW_SUBLIMINAL_DOWNLOAD"]),
        )
        future_frames = executor.submit(
            analyze_video_lowres,
            str(config["VIDEO_PATH"]),
            float(config["ANALYSIS_FPS"]),
            int(config["ANALYSIS_WIDTH"]),
            float(config["BLACK_FRAME_LUMA_THRESHOLD"]),
        )

        scene_cuts = future_scenes.result()
        exported_subtitles = future_subs.result()
        analyzed_frames = future_frames.result()

    cut_regions = merge_scene_cuts(scene_cuts, config["CUT_MERGE_SEC"])
    thresholds = derive_thresholds(analyzed_frames, config)
    phase_timings["parallel_analysis"] = time.perf_counter() - started

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

    from subtitle_ingestion import load_subtitles
    try:
        _, subtitle_events = load_subtitles(
            video_path=Path(str(config["VIDEO_PATH"])),
            grid_run_dir=Path(run_output_dir),
            subtitle_language=str(config["SUBTITLE_LANGUAGE"]),
            subtitle_stream_index=pipeline_config.subtitle_ingestion_config.subtitle_stream_index,
            allow_subliminal_download=bool(config["ALLOW_SUBLIMINAL_DOWNLOAD"]),
        )
    except ValueError as error:
        print(f"Warning: {error}")
        subtitle_events = []

    from subtitle_summary_precompute import ChunkWindow, precompute_summaries

    summary_chunks = [
        ChunkWindow(chunk_index=chunk.chunk_index, start=chunk.start, end=chunk.end)
        for chunk in chunks
    ]
    
    summary_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    summary_started = time.perf_counter()
    summary_future = summary_executor.submit(
        precompute_summaries,
        subtitle_events,
        summary_chunks,
        pipeline_config,
        Path(run_output_dir),
    )

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
                        executor.submit(
                            extract_frame,
                            str(config["VIDEO_PATH"]),
                            selected.timestamp,
                            temp_path,
                        )
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

    print("Grid writing completed.")

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
            "video_path": str(config["VIDEO_PATH"]),
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
            "config_profile": pipeline_config.profile_name,
            "summary_gate": pipeline_config.execution_config.summary_gate,
        }
    )

    if config["ENABLE_DIAGNOSTICS"]:
        with open(diagnostics_path, "w", encoding="utf-8") as diagnostics_handle:
            json.dump(diagnostics_payload, diagnostics_handle, indent=2)

    summary_future.result()
    phase_timings["summary_precompute"] = time.perf_counter() - summary_started
    print("Summary precomputation finished.")
    summary_executor.shutdown(wait=True)


def main() -> None:
    process_video(parse_args())


if __name__ == "__main__":
    main()
