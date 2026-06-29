"""
Centroid tracker and gate-crossing detector.

For single-athlete timing we track the largest moving contour.
Gates are user-defined lines in pixel space (normalised to frame dims
when sent over the wire, converted to pixels here).

Crossing detection uses subframe interpolation for timing precision.
"""

from dataclasses import dataclass, field
from typing import Optional
from interpolator import interpolate_crossing_time


@dataclass
class Gate:
    id: str
    label: str          # e.g. "Start", "10m", "Finish"
    x1: float           # pixel coords (absolute)
    y1: float
    x2: float
    y2: float
    crossed: bool = False
    crossed_at: Optional[float] = None  # seconds from video start


@dataclass
class TrackState:
    gates: list[Gate] = field(default_factory=list)
    prev_centroid: Optional[tuple] = None
    prev_timestamp: Optional[float] = None
    crossings: list[dict] = field(default_factory=list)
    start_time: Optional[float] = None  # timestamp of first gate crossing

    def reset(self):
        for g in self.gates:
            g.crossed = False
            g.crossed_at = None
        self.prev_centroid = None
        self.prev_timestamp = None
        self.crossings = []
        self.start_time = None


def gates_from_payload(payload: list, frame_w: int, frame_h: int) -> list[Gate]:
    """
    Convert normalised gate definitions (0–1 coords) from the frontend
    into pixel-space Gate objects.
    """
    gates = []
    for g in payload:
        gates.append(Gate(
            id=g["id"],
            label=g["label"],
            x1=g["x1_norm"] * frame_w,
            y1=g["y1_norm"] * frame_h,
            x2=g["x2_norm"] * frame_w,
            y2=g["y2_norm"] * frame_h,
        ))
    return gates


def update_tracker(
    state: TrackState,
    centroid: Optional[tuple],
    timestamp: float,
) -> list[dict]:
    """
    Called once per frame with the current centroid (or None if no athlete visible).
    Returns a list of new crossing events that occurred this frame.
    """
    new_events = []

    if centroid is not None and state.prev_centroid is not None:
        for gate in state.gates:
            if gate.crossed:
                continue

            crossed_at = interpolate_crossing_time(
                pos_before=state.prev_centroid,
                pos_after=centroid,
                gate={"x1": gate.x1, "y1": gate.y1, "x2": gate.x2, "y2": gate.y2},
                t_before=state.prev_timestamp,
                t_after=timestamp,
            )

            if crossed_at is not None:
                gate.crossed = True
                gate.crossed_at = crossed_at

                # First gate crossed becomes T0
                if state.start_time is None:
                    state.start_time = crossed_at

                split = crossed_at - state.start_time

                event = {
                    "gate_id": gate.id,
                    "gate_label": gate.label,
                    "video_time": round(crossed_at, 4),
                    "split_time": round(split, 4),
                }
                state.crossings.append(event)
                new_events.append(event)

    state.prev_centroid = centroid
    state.prev_timestamp = timestamp

    return new_events
