"""
Subframe interpolation for precise gate-crossing timestamps.

When a centroid crosses a gate line between two frames, we don't round
to the nearest frame — we interpolate the exact fractional position.

Given:
  - pos_before: centroid position at frame N (before crossing)
  - pos_after:  centroid position at frame N+1 (after crossing)
  - gate:       the line definition (x1,y1,x2,y2)
  - t_before:   timestamp of frame N (seconds)
  - t_after:    timestamp of frame N+1 (seconds)

We find the parameter t where the centroid's path intersects the gate line,
then interpolate the timestamp.
"""


def _cross_product_2d(ax, ay, bx, by) -> float:
    return ax * by - ay * bx


def line_intersection_param(px, py, dx, dy, ax, ay, bx, by):
    """
    Find parameter t such that (px + t*dx, py + t*dy) lies on segment AB.
    Returns t in [0, 1] if intersection exists, else None.

    Segment AB is the gate line. Ray is centroid motion from before to after.
    """
    # Direction of gate segment
    sx = bx - ax
    sy = by - ay

    denom = _cross_product_2d(dx, dy, sx, sy)
    if abs(denom) < 1e-10:
        # Parallel — no single crossing point
        return None

    # Vector from ray origin to segment start
    wx = ax - px
    wy = ay - py

    t = _cross_product_2d(wx, wy, sx, sy) / denom
    u = _cross_product_2d(wx, wy, dx, dy) / denom

    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t  # fraction of the inter-frame interval

    return None


def interpolate_crossing_time(
    pos_before: tuple,
    pos_after: tuple,
    gate: dict,
    t_before: float,
    t_after: float,
) -> float | None:
    """
    Returns the interpolated timestamp (in seconds) when the centroid
    crossed the gate line, or None if no crossing detected.

    pos_before / pos_after: (cx, cy) centroid pixel coords
    gate: {"x1": ..., "y1": ..., "x2": ..., "y2": ...}
    t_before / t_after: timestamps in seconds
    """
    px, py = pos_before
    dx = pos_after[0] - px
    dy = pos_after[1] - py

    ax, ay = gate["x1"], gate["y1"]
    bx, by = gate["x2"], gate["y2"]

    t_param = line_intersection_param(px, py, dx, dy, ax, ay, bx, by)

    if t_param is None:
        return None

    # Interpolate the actual timestamp
    return t_before + t_param * (t_after - t_before)
