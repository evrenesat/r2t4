Here is the formalized project description. You can pass this directly to your coding agent to establish the full context, hardware constraints, and overarching logic of the system.

---

# Project Specification: Narrative-Aware Smart Video Player

## 1. Project Objective

The goal is to build a specialized video player designed for viewers who experience suspense fatigue, anxiety, or severe second-hand embarrassment (cringe).

Instead of simple static content warnings, the system analyzes full-length movies and TV shows to understand the narrative trajectory. It maps the escalation of tension, looming threats, and social discomfort. This data allows the player to automatically skip the build-up and climax of uncomfortable scenes, jumping the user directly to the resolution while maintaining plot continuity.

## 2. Hardware and Environment Constraints

The pipeline is built to run entirely locally. The coding agent must respect these specific hardware and framework limitations:

* **Hardware:** Apple M4 MacBook Air with 32GB of unified memory.
* **Framework:** Apple MLX (`mlx-vlm`). Standard PyTorch implementations should be avoided in favor of MLX for memory efficiency.
* **Vision Model:** Qwen 3.5 0.8B Vision model.
* **Critical Constraint:** The MLX vision architecture currently does not support KV cache quantization. This means the 16-bit KV cache will quickly exhaust the 32GB of unified memory if multiple individual image frames are passed sequentially.

## 3. Architecture Overview

To bypass the memory bottleneck while providing the vision model with the temporal context needed to judge "escalation" and "pacing," the project is divided into three distinct phases.

### Phase 1: Pre-processing (The Grid Extractor)

Instead of feeding the model sequential frames, the system converts temporal video data into a single spatial image (a grid) to minimize the prefill memory penalty.

1. **Scene Detection:** Use `ffmpeg` to detect visual scene cuts. Cache the results using an MD5 hash of the video file to skip this step on subsequent runs.
2. **Chunking:** Divide long scenes into chunks with a maximum duration of 15 seconds.
3. **Extraction and Stitching:** Extract 4 equidistant keyframes from each chunk. Proportionally scale these frames (do not stretch or letterbox) and stitch them into a single 2x2 image grid.
4. **Output:** Save grids with filenames containing the exact start and end timestamps (e.g., `scene3_chunk1_24_5s_to_39_5s.jpg`) for later synchronization.

### Phase 2: Vision Model Inference (Scene Categorization)

The 2x2 grids are passed to the Qwen 0.8B Vision model via MLX. The model is prompted to analyze the 4 frames as a single continuous chronological event.

* **Prompting Strategy:** The model must output a strict JSON object. Free-text analysis is prohibited to prevent hallucinations and parsing errors.
* **JSON Schema Requirements:**
* `summary`: 1-2 sentence objective description.
* `primary_mood`: Categorical mood (Tense, Awkward, Action, etc.).
* `tension_trend`: Ordinal scale mapping narrative pacing (Escalating, Peaking, Resolving, Flat).
* `threat_anticipation`: Ordinal scale indicating incoming negative events (None, Looming, Active).
* `social_discomfort`: Ordinal scale for cringe/embarrassment (None, Mild, Severe).
* `content_warnings`: Array of explicit triggers (Violence, Gore, Nudity, etc.).
* `setting`: General environment context.



### Phase 3: Downstream LLM & Player Integration

The accumulated JSON outputs from the vision model, combined with synchronized subtitle data, are passed to a larger LLM.

1. **Timeline Mapping:** The larger LLM uses the `tension_trend`, `threat_anticipation`, and `social_discomfort` markers to plot an emotional graph of the movie.
2. **Skip Generation:** The LLM identifies the start of an uncomfortable sequence (e.g., trend shifts to "Escalating" + threat "Looming") and scans forward to find the exact timestamp where the trend shifts to "Resolving."
3. **Playback Control:** These generated start and stop timestamps dictate the safe viewing jumps within the custom video player.

---

Would you like me to adjust any of the terminology in this document before you hand it off to the agent?
