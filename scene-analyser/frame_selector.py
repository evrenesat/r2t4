from __future__ import annotations

import math
import subprocess
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional acceleration
    np = None

from PIL import Image, ImageChops, ImageFilter, ImageStat


@dataclass(frozen=True)
class AnalyzedFrame:
    index: int
    timestamp: float
    mean_luma: float
    black_frame: bool
    sharpness: float
    motion: float
    novelty: float
    dhash: int


@dataclass(frozen=True)
class ChunkWindow:
    chunk_index: int
    start: float
    end: float
    activity_class: str
    source_scene_cut_times: list[float]


@dataclass(frozen=True)
class SelectedFrame:
    timestamp: float
    score: float
    bin_index: int
    frame_index: int
    dhash: int


@dataclass(frozen=True)
class DiagnosticsSummary:
    candidate_frame_count: int
    thresholds_used: dict[str, float]
    low_variation_chunk_count: int
    chunk_duration_stats: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def percentile(values: list[float], q: float, fallback: float = 0.0) -> float:
    if not values:
        return float(fallback)
    if np is not None:
        return float(np.percentile(np.asarray(values, dtype=np.float32), q))

    sorted_values = sorted(float(value) for value in values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (q / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return sorted_values[lower]
    fraction = rank - lower
    return (sorted_values[lower] * (1.0 - fraction)) + (sorted_values[upper] * fraction)


def normalize_band(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return float(max(0.0, min(1.0, (value - low) / (high - low))))


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def estimate_sharpness(frame: Any) -> float:
    if np is not None and not isinstance(frame, Image.Image):
        frame_f = frame.astype(np.float32)
        horizontal = np.abs(np.diff(frame_f, axis=1)).mean() if frame.shape[1] > 1 else 0.0
        vertical = np.abs(np.diff(frame_f, axis=0)).mean() if frame.shape[0] > 1 else 0.0
        return float(horizontal + vertical)

    edges = frame.filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(edges).mean[0])


def compute_dhash(frame: Any) -> int:
    resized = (
        frame if isinstance(frame, Image.Image) else Image.fromarray(frame)
    ).resize((9, 8), Image.Resampling.BILINEAR)
    pixels = list(resized.getdata())
    value = 0
    for row in range(8):
        offset = row * 9
        for col in range(8):
            left = pixels[offset + col]
            right = pixels[offset + col + 1]
            value = (value << 1) | int(right > left)
    return value


def _probe_dimensions(video_path: str) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        video_path,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    width_text, height_text = result.stdout.strip().split("x", 1)
    return int(width_text), int(height_text)


def _scaled_dimensions(video_path: str, target_width: int) -> tuple[int, int]:
    source_width, source_height = _probe_dimensions(video_path)
    if source_width <= 0 or source_height <= 0:
        raise RuntimeError(f"Invalid video dimensions for {video_path}.")

    width = min(target_width, source_width)
    scaled_height = int(round(source_height * (width / source_width)))
    if scaled_height % 2 == 1:
        scaled_height += 1
    return width, max(2, scaled_height)


def analyze_video_lowres(
    video_path: str,
    analysis_fps: float,
    analysis_width: int,
    black_frame_luma_threshold: float,
) -> list[AnalyzedFrame]:
    width, height = _scaled_dimensions(video_path, analysis_width)
    frame_size = width * height
    vf = f"fps={analysis_fps},scale={width}:{height}:flags=lanczos,format=gray"
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        video_path,
        "-vf",
        vf,
        "-pix_fmt",
        "gray",
        "-f",
        "rawvideo",
        "-",
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Could not start ffmpeg analysis process.")

    frames: list[AnalyzedFrame] = []
    previous_pixels: Any | None = None
    previous_hash: int | None = None
    index = 0

    try:
        while True:
            raw = process.stdout.read(frame_size)
            if not raw:
                break
            if len(raw) != frame_size:
                raise RuntimeError("Incomplete low-resolution frame read from ffmpeg.")

            if np is not None:
                pixels = np.frombuffer(raw, dtype=np.uint8).reshape((height, width))
                frame_hash = compute_dhash(pixels)
                mean_luma = float(pixels.mean())
                sharpness = estimate_sharpness(pixels)
            else:
                pixels = Image.frombytes("L", (width, height), raw)
                frame_hash = compute_dhash(pixels)
                mean_luma = float(ImageStat.Stat(pixels).mean[0])
                sharpness = estimate_sharpness(pixels)
            if previous_pixels is None:
                motion = 0.0
                novelty = 0.0
            else:
                if np is not None:
                    diff = np.abs(pixels.astype(np.int16) - previous_pixels.astype(np.int16))
                    motion = float(diff.mean())
                else:
                    diff_image = ImageChops.difference(pixels, previous_pixels)
                    motion = float(ImageStat.Stat(diff_image).mean[0])
                novelty = float(hamming_distance(previous_hash or 0, frame_hash))

            frames.append(
                AnalyzedFrame(
                    index=index,
                    timestamp=index / analysis_fps,
                    mean_luma=mean_luma,
                    black_frame=mean_luma <= black_frame_luma_threshold,
                    sharpness=sharpness,
                    motion=motion,
                    novelty=novelty,
                    dhash=frame_hash,
                )
            )
            previous_pixels = pixels
            previous_hash = frame_hash
            index += 1
    finally:
        process.stdout.close()

    stderr = process.stderr.read().decode("utf-8", errors="replace")
    process.stderr.close()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"ffmpeg low-resolution analysis failed: {stderr.strip()}")

    return frames


def derive_thresholds(
    frames: list[AnalyzedFrame],
    config: dict[str, Any],
) -> dict[str, float]:
    motions = [frame.motion for frame in frames]
    novelties = [frame.novelty for frame in frames]
    sharpness = [frame.sharpness for frame in frames]

    motion_medium = percentile(motions, 55, 0.0)
    motion_high = percentile(motions, 85, motion_medium)
    novelty_medium = percentile(novelties, 55, 0.0)
    novelty_high = max(
        float(config["MIN_FRAME_DISTANCE"]),
        percentile(novelties, 85, float(config["MIN_FRAME_DISTANCE"])),
    )
    quality_floor = percentile(sharpness, 20, 0.0)
    sharpness_high = percentile(sharpness, 80, quality_floor)

    high_motion_fraction = (
        float(sum(value >= motion_high for value in motions) / len(motions)) if motions else 0.0
    )

    return {
        "motion_medium": motion_medium,
        "motion_high": max(motion_high, motion_medium + 1e-6),
        "novelty_medium": novelty_medium,
        "novelty_high": max(novelty_high, novelty_medium + 1e-6),
        "quality_floor": quality_floor,
        "sharpness_high": max(sharpness_high, quality_floor + 1e-6),
        "busy_motion_fraction": max(0.15, min(0.5, high_motion_fraction + 0.05)),
        "busy_activity_score": 0.52,
        "low_variation_motion": percentile(motions, 30, 0.0),
        "low_variation_novelty": max(
            float(config["MIN_FRAME_DISTANCE"]) * 0.75,
            percentile(novelties, 35, float(config["MIN_FRAME_DISTANCE"]) * 0.5),
        ),
    }


def _timestamps(frames: list[AnalyzedFrame]) -> list[float]:
    return [frame.timestamp for frame in frames]


def _slice_frames(
    frames: list[AnalyzedFrame],
    timestamps: list[float],
    start: float,
    end: float,
) -> list[AnalyzedFrame]:
    left = bisect_left(timestamps, start)
    right = bisect_right(timestamps, end)
    return frames[left:right]


def _count_intersecting_regions(
    cut_regions: list[dict[str, Any]],
    start: float,
    end: float,
) -> int:
    return sum(1 for region in cut_regions if region["end"] > start and region["start"] < end)


def _window_activity(
    frames: list[AnalyzedFrame],
    scene_cuts: list[float],
    cut_regions: list[dict[str, Any]],
    thresholds: dict[str, float],
    start: float,
    end: float,
) -> dict[str, float | str]:
    duration = max(end - start, 1e-6)
    window_frames = [frame for frame in frames if start <= frame.timestamp <= end]
    window_cuts = [cut for cut in scene_cuts if start < cut < end]

    if not window_frames:
        return {
            "activity_score": 0.0,
            "mean_motion_norm": 0.0,
            "high_motion_fraction": 0.0,
            "activity_class": "calm",
            "cut_count": float(len(window_cuts)),
        }

    motion_norms = [
        normalize_band(frame.motion, thresholds["motion_medium"], thresholds["motion_high"])
        for frame in window_frames
    ]
    mean_motion_norm = sum(motion_norms) / len(motion_norms)
    high_motion_fraction = (
        sum(frame.motion >= thresholds["motion_high"] for frame in window_frames) / len(window_frames)
    )
    region_count = _count_intersecting_regions(cut_regions, start, end)
    cut_density = min(1.0, len(window_cuts) / max(1.0, duration / 2.5))
    region_density = min(1.0, region_count / max(1.0, duration / 4.0))

    activity_score = (
        0.45 * high_motion_fraction
        + 0.25 * mean_motion_norm
        + 0.20 * cut_density
        + 0.10 * region_density
    )
    if activity_score >= thresholds["busy_activity_score"] or (
        high_motion_fraction >= thresholds["busy_motion_fraction"] and len(window_cuts) >= 1
    ):
        activity_class = "busy"
    elif activity_score >= thresholds["busy_activity_score"] * 0.65:
        activity_class = "mixed"
    else:
        activity_class = "calm"

    return {
        "activity_score": activity_score,
        "mean_motion_norm": mean_motion_norm,
        "high_motion_fraction": high_motion_fraction,
        "activity_class": activity_class,
        "cut_count": float(len(window_cuts)),
    }


def build_adaptive_chunks(
    video_duration: float,
    frames: list[AnalyzedFrame],
    scene_cuts: list[float],
    cut_regions: list[dict[str, Any]],
    config: dict[str, Any],
    thresholds: dict[str, float],
) -> list[ChunkWindow]:
    if video_duration <= 0:
        return []

    scene_cuts = sorted(cut for cut in scene_cuts if 0.0 < cut < video_duration)
    timestamps = _timestamps(frames)
    chunks: list[ChunkWindow] = []
    chunk_index = 1
    start = 0.0

    while start < video_duration - 1e-6:
        remaining = video_duration - start
        if remaining <= config["MAX_CHUNK_SEC"]:
            end = video_duration
        else:
            min_end = start + config["MIN_CHUNK_SEC"]
            max_end = min(video_duration, start + config["MAX_CHUNK_SEC"])
            cut_candidates = [cut for cut in scene_cuts if min_end <= cut <= max_end]

            end: float | None = None
            for cut in cut_candidates:
                metrics = _window_activity(frames, scene_cuts, cut_regions, thresholds, start, cut)
                if metrics["activity_class"] == "busy":
                    end = cut
                    break

            if end is None:
                probe_frames = _slice_frames(frames, timestamps, min_end, max_end)
                for frame in probe_frames:
                    metrics = _window_activity(
                        frames,
                        scene_cuts,
                        cut_regions,
                        thresholds,
                        start,
                        frame.timestamp,
                    )
                    if metrics["activity_class"] == "busy":
                        end = frame.timestamp
                        break

            if end is None:
                calm_cuts = [
                    cut
                    for cut in cut_candidates
                    if cut >= max_end - max(1.0, config["MIN_CHUNK_SEC"] * 0.25)
                ]
                end = calm_cuts[-1] if calm_cuts else max_end

            tail = video_duration - end
            if 0.0 < tail < config["MIN_CHUNK_SEC"] * 0.5 and remaining <= (
                config["MAX_CHUNK_SEC"] + config["MIN_CHUNK_SEC"] * 0.5
            ):
                end = video_duration

        chunk_cuts = [cut for cut in scene_cuts if start < cut < end]
        metrics = _window_activity(frames, scene_cuts, cut_regions, thresholds, start, end)
        chunks.append(
            ChunkWindow(
                chunk_index=chunk_index,
                start=start,
                end=end,
                activity_class=str(metrics["activity_class"]),
                source_scene_cut_times=chunk_cuts,
            )
        )
        chunk_index += 1
        start = end

    return chunks


def _candidate_score(
    frame: AnalyzedFrame,
    scene_cuts: list[float],
    thresholds: dict[str, float],
    config: dict[str, Any],
) -> float:
    motion_score = normalize_band(
        frame.motion, thresholds["motion_medium"], thresholds["motion_high"]
    )
    novelty_score = normalize_band(
        frame.novelty, thresholds["novelty_medium"], thresholds["novelty_high"]
    )
    sharpness_score = normalize_band(
        frame.sharpness, thresholds["quality_floor"], thresholds["sharpness_high"]
    )
    cut_bonus = 1.0 if any(abs(frame.timestamp - cut) <= 0.75 for cut in scene_cuts) else 0.0
    black_penalty = 0.75 if frame.black_frame else 0.0
    quality_penalty = 0.30 if frame.sharpness < thresholds["quality_floor"] else 0.0
    return (
        0.45 * motion_score
        + 0.20 * novelty_score
        + 0.15 * sharpness_score
        + 0.20 * cut_bonus
        - black_penalty
        - quality_penalty
        - (0.05 if frame.novelty < config["MIN_FRAME_DISTANCE"] * 0.5 else 0.0)
    )


def collect_chunk_candidates(
    chunk: ChunkWindow,
    frames: list[AnalyzedFrame],
    scene_cuts: list[float],
    thresholds: dict[str, float],
    config: dict[str, Any],
) -> list[tuple[AnalyzedFrame, float]]:
    timestamps = _timestamps(frames)
    window_frames = _slice_frames(frames, timestamps, chunk.start, chunk.end)

    candidate_by_index = {frame.index: frame for frame in window_frames}
    for cut in scene_cuts:
        if not (chunk.start < cut < chunk.end):
            continue
        position = bisect_left(timestamps, cut)
        if position < len(frames):
            candidate = frames[position]
            if candidate.timestamp <= chunk.end + 1e-6:
                candidate_by_index[candidate.index] = candidate
        elif position > 0:
            candidate_by_index[frames[position - 1].index] = frames[position - 1]

    candidates = sorted(candidate_by_index.values(), key=lambda frame: frame.timestamp)
    valid_candidates = [
        frame
        for frame in candidates
        if not frame.black_frame and frame.sharpness >= thresholds["quality_floor"]
    ]
    if len(valid_candidates) >= 4:
        candidates = valid_candidates
    elif len(valid_candidates) >= max(1, len(candidates) // 2):
        kept_indexes = {frame.index for frame in valid_candidates}
        candidates = valid_candidates + [frame for frame in candidates if frame.index not in kept_indexes]

    chunk_cuts = [cut for cut in scene_cuts if chunk.start < cut < chunk.end]
    return [
        (frame, _candidate_score(frame, chunk_cuts, thresholds, config))
        for frame in candidates
    ]


def _fallback_timestamp(chunk: ChunkWindow, bin_index: int) -> float:
    duration = max(chunk.end - chunk.start, 1e-6)
    bin_width = duration / 4.0
    return chunk.start + (bin_index * bin_width) + (bin_width / 2.0)


def select_chunk_frames(
    chunk: ChunkWindow,
    frames: list[AnalyzedFrame],
    scene_cuts: list[float],
    thresholds: dict[str, float],
    config: dict[str, Any],
) -> tuple[list[SelectedFrame], bool]:
    candidates = collect_chunk_candidates(chunk, frames, scene_cuts, thresholds, config)
    duration = max(chunk.end - chunk.start, 1e-6)
    bin_width = duration / 4.0
    bins: list[list[tuple[AnalyzedFrame, float]]] = [[] for _ in range(4)]

    for frame, score in candidates:
        raw_bin = (frame.timestamp - chunk.start) / duration
        bin_index = min(3, max(0, int(raw_bin * 4)))
        bins[bin_index].append((frame, score))

    for bin_index, bucket in enumerate(bins):
        center = chunk.start + (bin_index * bin_width) + (bin_width / 2.0)
        bucket.sort(key=lambda item: (-item[1], abs(item[0].timestamp - center), item[0].timestamp))

    used_indexes: set[int] = set()
    selections: list[SelectedFrame] = []

    for bin_index, bucket in enumerate(bins):
        chosen: tuple[AnalyzedFrame, float] | None = None
        for candidate in bucket:
            if candidate[0].index not in used_indexes:
                chosen = candidate
                break

        if chosen is None:
            center = _fallback_timestamp(chunk, bin_index)
            fallback_pool = sorted(
                candidates,
                key=lambda item: (item[0].index in used_indexes, abs(item[0].timestamp - center), -item[1]),
            )
            for candidate in fallback_pool:
                if candidate[0].index not in used_indexes:
                    chosen = candidate
                    break

        if chosen is None:
            timestamp = _fallback_timestamp(chunk, bin_index)
            selections.append(
                SelectedFrame(
                    timestamp=timestamp,
                    score=-0.1,
                    bin_index=bin_index,
                    frame_index=-1,
                    dhash=0,
                )
            )
            continue

        frame, score = chosen
        used_indexes.add(frame.index)
        selections.append(
            SelectedFrame(
                timestamp=frame.timestamp,
                score=score,
                bin_index=bin_index,
                frame_index=frame.index,
                dhash=frame.dhash,
            )
        )

    def attempt_replacement(target_index: int) -> SelectedFrame | None:
        target = selections[target_index]
        alternatives = bins[target.bin_index]
        others = [
            selection
            for selection_index, selection in enumerate(selections)
            if selection_index != target_index
        ]
        for frame, score in alternatives:
            if frame.index == target.frame_index or frame.index in used_indexes:
                continue
            if all(
                selection.frame_index < 0
                or hamming_distance(frame.dhash, selection.dhash) >= config["MIN_FRAME_DISTANCE"]
                for selection in others
            ):
                return SelectedFrame(
                    timestamp=frame.timestamp,
                    score=score,
                    bin_index=target.bin_index,
                    frame_index=frame.index,
                    dhash=frame.dhash,
                )
        return None

    for left in range(len(selections)):
        for right in range(left + 1, len(selections)):
            if selections[left].frame_index < 0 or selections[right].frame_index < 0:
                continue
            if hamming_distance(selections[left].dhash, selections[right].dhash) >= config["MIN_FRAME_DISTANCE"]:
                continue

            replace_index = left if selections[left].score <= selections[right].score else right
            replacement = attempt_replacement(replace_index)
            if replacement is None:
                continue
            if selections[replace_index].frame_index >= 0:
                used_indexes.discard(selections[replace_index].frame_index)
            used_indexes.add(replacement.frame_index)
            selections[replace_index] = replacement

    low_variation = False
    for left in range(len(selections)):
        for right in range(left + 1, len(selections)):
            if selections[left].frame_index < 0 or selections[right].frame_index < 0:
                continue
            if hamming_distance(selections[left].dhash, selections[right].dhash) < config["MIN_FRAME_DISTANCE"]:
                low_variation = True
                break
        if low_variation:
            break

    selections.sort(key=lambda selection: selection.timestamp)
    return selections, low_variation


def build_diagnostics_summary(
    chunks: list[ChunkWindow],
    thresholds: dict[str, float],
    candidate_frame_count: int,
    low_variation_chunk_count: int,
) -> DiagnosticsSummary:
    durations = [chunk.end - chunk.start for chunk in chunks]
    if not durations:
        duration_stats = {"min": 0.0, "median": 0.0, "mean": 0.0, "max": 0.0}
    else:
        duration_stats = {
            "min": float(min(durations)),
            "median": percentile(durations, 50, 0.0),
            "mean": float(sum(durations) / len(durations)),
            "max": float(max(durations)),
        }

    return DiagnosticsSummary(
        candidate_frame_count=candidate_frame_count,
        thresholds_used={key: float(value) for key, value in thresholds.items()},
        low_variation_chunk_count=low_variation_chunk_count,
        chunk_duration_stats=duration_stats,
    )
