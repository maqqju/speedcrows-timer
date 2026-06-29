# Sprint Timer

Multi-gate split timing from video files. Python/OpenCV backend + browser frontend.

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + Uvicorn |
| Computer Vision | OpenCV (MOG2 background subtraction) |
| Timing precision | Subframe interpolation |
| Frontend | Vanilla HTML/JS, no dependencies |
| Transport | WebSocket (frame streaming) + REST |

## Setup

```bash
# 1. Install Python deps
cd backend
pip install -r requirements.txt

# 2. Start the server
python main.py
# → http://localhost:8000
```

The frontend is served automatically from `/frontend/` by FastAPI's StaticFiles.
Open `http://localhost:8000` in a browser.

## How to use

1. **Load** — drop a video file (MP4, MOV, AVI etc.)
2. **Gates** — click and drag lines across the athlete's path on the first frame
   - Name each gate (Start, 10m, 30m, Finish…)
   - Draw as many as you need
3. **Analyse** — click ▶ Analyse; watch the preview update in real time
4. **Results** — splits appear as each gate is crossed; export to CSV when done

## Accuracy

Timing precision comes from **subframe interpolation** — when the athlete's
centroid crosses a gate line between frame N and frame N+1, we solve for the
exact fractional moment of crossing rather than rounding to the nearest frame.

Theoretical accuracy: depends on camera frame rate, but typically **±5–15ms**
vs. the ±33ms floor of frame-rounding at 30fps.

Practical limits:
- Camera shake (use a tripod or weighted bag)
- Motion blur at high speeds blurs the contour centroid
- Lighting changes (MOG2 handles slow variation; sudden shade changes can confuse it)

## Pipeline tuning

In `pipeline.py`:

| Parameter | Default | Notes |
|---|---|---|
| `learning_rate` | `0.003` | Lower = slower BG adaptation (good for fixed camera) |
| `history` (MOG2) | `200` | Frames used to build background model |
| `varThreshold` | `40` | Sensitivity — raise if getting false detections |
| `min_contour_area` | `800` | Minimum pixels² to count as athlete — raise in noisy conditions |
| `warmup` frames | `90` | Frames to train BG model before tracking starts |

## Gate coordinate system

Gates are stored as **normalised coordinates** (0–1 relative to frame dimensions).
Pixel conversion happens in `tracker.py → gates_from_payload()`.
This means gate definitions are resolution-independent — the same gate JSON
works for 720p, 1080p, 4K source footage.

## Extending

- **Multiple athletes**: assign contours by bounding-box region (e.g. lane Y-range)
- **Live camera**: change `source` in `VideoPipeline` from a file path to `0` (webcam index)
- **Speed calculation**: add a calibration distance marker, compute px/m, divide by split time
- **Reaction time**: first gate = trigger sensor or audio spike detection
