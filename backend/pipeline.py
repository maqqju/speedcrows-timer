"""
OpenCV processing pipeline.

Reads frames from a video file (or webcam index), applies MOG2 background
subtraction, finds the largest moving contour (the athlete), and returns
the centroid + a debug-annotated JPEG thumbnail for the frontend preview.
"""

import cv2
import numpy as np
from typing import Optional, Generator


class VideoPipeline:
    def __init__(self, source, learning_rate: float = 0.005):
        """
        source: path to video file, or integer webcam index
        learning_rate: MOG2 background model update rate.
          Lower = slower adaptation (better for fixed camera, short clips).
          0 = completely static background model (use after warmup).
        """
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open video source: {source}")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # MOG2: good for outdoor lighting variation
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=200,
            varThreshold=40,
            detectShadows=False,       # shadows waste CPU and confuse contours
        )
        self.learning_rate = learning_rate

        # Morphology kernel to clean up foreground mask
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

    @property
    def info(self) -> dict:
        return {
            "fps": self.fps,
            "width": self.frame_w,
            "height": self.frame_h,
            "total_frames": self.total_frames,
            "duration": self.total_frames / self.fps if self.fps else 0,
        }

    def warmup(self, n_frames: int = 60):
        """
        Prime the background model with the first N frames before tracking.
        Call this before iterating frames for timing.
        """
        saved_pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        for _ in range(n_frames):
            ret, frame = self.cap.read()
            if not ret:
                break
            self.bg_subtractor.apply(frame, learningRate=0.05)

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, saved_pos)

    def process_frames(
        self,
        gates: list = None,
        thumb_width: int = 640,
        min_contour_area: int = 800,
    ) -> Generator[dict, None, None]:
        """
        Generator that yields one dict per frame:
        {
            "frame_index": int,
            "timestamp": float,          # seconds
            "centroid": (cx, cy) | None,
            "thumb_jpeg": bytes,         # annotated preview
            "progress": float,           # 0–1
        }
        """
        gates = gates or []

        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            frame_idx = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            timestamp = frame_idx / self.fps

            # --- Background subtraction ---
            fg_mask = self.bg_subtractor.apply(frame, learningRate=self.learning_rate)

            # Clean: remove noise, fill gaps
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self.kernel)
            fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self.kernel)

            # --- Find largest contour ---
            contours, _ = cv2.findContours(
                fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            centroid = None
            best_area = min_contour_area

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > best_area:
                    best_area = area
                    M = cv2.moments(cnt)
                    if M["m00"] > 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        centroid = (cx, cy)

            # --- Build annotated thumbnail ---
            thumb = self._draw_debug(frame, fg_mask, centroid, gates, timestamp)
            scale = thumb_width / self.frame_w
            thumb_small = cv2.resize(
                thumb, (thumb_width, int(self.frame_h * scale))
            )
            _, jpeg = cv2.imencode(".jpg", thumb_small, [cv2.IMWRITE_JPEG_QUALITY, 75])

            progress = frame_idx / self.total_frames if self.total_frames > 0 else 0

            yield {
                "frame_index": frame_idx,
                "timestamp": timestamp,
                "centroid": centroid,
                "thumb_jpeg": jpeg.tobytes(),
                "progress": min(progress, 1.0),
            }

    def _draw_debug(self, frame, fg_mask, centroid, gates, timestamp):
        out = frame.copy()

        # Draw gates
        for gate in gates:
            color = (0, 255, 100) if not gate.crossed else (0, 100, 255)
            cv2.line(
                out,
                (int(gate.x1), int(gate.y1)),
                (int(gate.x2), int(gate.y2)),
                color, 2,
            )
            cv2.putText(
                out, gate.label,
                (int(gate.x1), int(gate.y1) - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
            )

        # Draw centroid
        if centroid:
            cv2.circle(out, centroid, 10, (0, 220, 255), -1)
            cv2.circle(out, centroid, 12, (0, 0, 0), 2)

        # Timestamp overlay
        cv2.putText(
            out, f"{timestamp:.3f}s",
            (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2,
        )

        return out

    def release(self):
        self.cap.release()
