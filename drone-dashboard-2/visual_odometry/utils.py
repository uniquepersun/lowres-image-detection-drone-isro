"""Utility helpers for the visual odometry pipeline."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Deque, Iterable, Sequence

import cv2
import numpy as np


def to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def as_points_array(points: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
    arr = np.asarray(points, dtype=np.float32)
    if arr.size == 0:
        return arr.reshape(0, 2)
    return arr.reshape(-1, 2)


def to_cv_points(points: np.ndarray) -> np.ndarray:
    pts = as_points_array(points)
    return pts.reshape(-1, 1, 2).astype(np.float32)


def clip_points(points: np.ndarray, width: int, height: int) -> np.ndarray:
    pts = as_points_array(points)
    if pts.size == 0:
        return pts
    keep = (
        (pts[:, 0] >= 0)
        & (pts[:, 0] < width)
        & (pts[:, 1] >= 0)
        & (pts[:, 1] < height)
    )
    return pts[keep]


def point_mask(shape: tuple[int, int], points: np.ndarray, radius: int) -> np.ndarray:
    mask = np.full(shape, 255, dtype=np.uint8)
    pts = as_points_array(points)
    if pts.size == 0:
        return mask
    for x, y in pts.astype(int):
        cv2.circle(mask, (int(x), int(y)), int(radius), 0, -1)
    return mask


def angle_wrap_deg(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def angle_wrap_vector_deg(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    return (arr + 180.0) % 360.0 - 180.0


def smooth_angle_series(previous: np.ndarray | None, current: np.ndarray, alpha: float) -> np.ndarray:
    current = np.asarray(current, dtype=np.float64)
    if previous is None:
        return current.copy()
    previous = np.asarray(previous, dtype=np.float64)
    delta = current - previous
    delta = np.vectorize(angle_wrap_deg)(delta)
    return previous + alpha * delta


def rotation_matrix_to_euler_zyx(rotation: np.ndarray) -> np.ndarray:
    """Return yaw, pitch, roll in degrees for an OpenCV-compatible rotation matrix."""

    r = np.asarray(rotation, dtype=np.float64)
    sy = math.sqrt(r[0, 0] * r[0, 0] + r[1, 0] * r[1, 0])
    singular = sy < 1e-8

    if not singular:
        roll = math.atan2(r[2, 1], r[2, 2])
        pitch = math.atan2(-r[2, 0], sy)
        yaw = math.atan2(r[1, 0], r[0, 0])
    else:
        roll = math.atan2(-r[1, 2], r[1, 1])
        pitch = math.atan2(-r[2, 0], sy)
        yaw = 0.0

    return np.degrees(np.array([yaw, pitch, roll], dtype=np.float64))


def sampson_error(pts1: np.ndarray, pts2: np.ndarray, essential: np.ndarray, k_inv: np.ndarray) -> float:
    if pts1.size == 0 or pts2.size == 0:
        return 0.0

    p1 = np.hstack([as_points_array(pts1), np.ones((len(pts1), 1), dtype=np.float64)])
    p2 = np.hstack([as_points_array(pts2), np.ones((len(pts2), 1), dtype=np.float64)])
    x1 = (k_inv @ p1.T).T
    x2 = (k_inv @ p2.T).T

    ex1 = essential @ x1.T
    eTx2 = essential.T @ x2.T
    numer = np.sum(x2 * (essential @ x1.T).T, axis=1) ** 2
    denom = ex1[0] ** 2 + ex1[1] ** 2 + eTx2[0] ** 2 + eTx2[1] ** 2 + 1e-12
    error = np.sqrt(np.maximum(numer / denom, 0.0))
    return float(np.mean(error))


def compute_median_displacement(pts1: np.ndarray, pts2: np.ndarray) -> float:
    if len(pts1) == 0 or len(pts2) == 0:
        return 0.0
    diff = as_points_array(pts2) - as_points_array(pts1)
    distances = np.linalg.norm(diff, axis=1)
    return float(np.median(distances))


def draw_text(
    image: np.ndarray,
    lines: Sequence[str],
    origin: tuple[int, int] = (10, 24),
    line_spacing: int = 22,
    color: tuple[int, int, int] = (240, 240, 240),
    font_scale: float = 0.55,
    thickness: int = 1,
) -> None:
    x, y = origin
    for index, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (x, y + index * line_spacing),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA,
        )


@dataclass(slots=True)
class RunningAverage:
    window: int
    values: Deque[np.ndarray]

    def __init__(self, window: int):
        self.window = max(1, int(window))
        self.values = deque(maxlen=self.window)

    def append(self, value: Iterable[float] | np.ndarray) -> np.ndarray:
        arr = np.asarray(value, dtype=np.float64)
        self.values.append(arr)
        return self.mean()

    def mean(self) -> np.ndarray:
        if not self.values:
            return np.zeros(0, dtype=np.float64)
        stack = np.stack(self.values, axis=0)
        return np.mean(stack, axis=0)

    def median(self) -> np.ndarray:
        if not self.values:
            return np.zeros(0, dtype=np.float64)
        stack = np.stack(self.values, axis=0)
        return np.median(stack, axis=0)

    def clear(self) -> None:
        self.values.clear()


class AngleWindow:
    """Rolling window that averages angles in a local unwrapped frame."""

    def __init__(self, window: int):
        self.window = max(1, int(window))
        self.values: Deque[np.ndarray] = deque(maxlen=self.window)

    def append(self, value: Iterable[float] | np.ndarray) -> np.ndarray:
        arr = np.asarray(value, dtype=np.float64)
        self.values.append(arr)
        return self.mean()

    def _aligned_stack(self) -> np.ndarray:
        if not self.values:
            return np.zeros((0, 0), dtype=np.float64)
        ref = self.values[-1]
        aligned = [ref + angle_wrap_vector_deg(sample - ref) for sample in self.values]
        return np.stack(aligned, axis=0)

    def mean(self) -> np.ndarray:
        if not self.values:
            return np.zeros(0, dtype=np.float64)
        return np.mean(self._aligned_stack(), axis=0)

    def median(self) -> np.ndarray:
        if not self.values:
            return np.zeros(0, dtype=np.float64)
        return np.median(self._aligned_stack(), axis=0)

    def clear(self) -> None:
        self.values.clear()


class ExponentialMovingAverage:
    def __init__(self, alpha: float):
        self.alpha = float(alpha)
        self.value: np.ndarray | None = None

    def reset(self) -> None:
        self.value = None

    def update(self, sample: Iterable[float] | np.ndarray) -> np.ndarray:
        sample_arr = np.asarray(sample, dtype=np.float64)
        if self.value is None:
            self.value = sample_arr.copy()
        else:
            self.value = (1.0 - self.alpha) * self.value + self.alpha * sample_arr
        return self.value.copy()


class ConstantVelocityKalman:
    """Simple 6-state Kalman filter for 3D position and velocity."""

    def __init__(self, process_noise: float, measurement_noise: float):
        self.q = float(process_noise)
        self.r = float(measurement_noise)
        self.x = np.zeros((6, 1), dtype=np.float64)
        self.P = np.eye(6, dtype=np.float64) * 10.0
        self.H = np.zeros((3, 6), dtype=np.float64)
        self.H[0, 0] = 1.0
        self.H[1, 1] = 1.0
        self.H[2, 2] = 1.0
        self.R = np.eye(3, dtype=np.float64) * self.r

    def reset(self) -> None:
        self.x.fill(0.0)
        self.P = np.eye(6, dtype=np.float64) * 10.0

    def predict(self, dt: float) -> np.ndarray:
        dt = max(float(dt), 1e-3)
        F = np.eye(6, dtype=np.float64)
        F[0, 3] = dt
        F[1, 4] = dt
        F[2, 5] = dt

        q = self.q
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt2 * dt2
        Q = np.array(
            [
                [dt4 / 4, 0, 0, dt3 / 2, 0, 0],
                [0, dt4 / 4, 0, 0, dt3 / 2, 0],
                [0, 0, dt4 / 4, 0, 0, dt3 / 2],
                [dt3 / 2, 0, 0, dt2, 0, 0],
                [0, dt3 / 2, 0, 0, dt2, 0],
                [0, 0, dt3 / 2, 0, 0, dt2],
            ],
            dtype=np.float64,
        ) * q

        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q
        return self.x[:3, 0].copy()

    def update(self, measurement: Iterable[float] | np.ndarray) -> np.ndarray:
        z = np.asarray(measurement, dtype=np.float64).reshape(3, 1)
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        I = np.eye(6, dtype=np.float64)
        self.P = (I - K @ self.H) @ self.P
        return self.x[:3, 0].copy()

    @property
    def position(self) -> np.ndarray:
        return self.x[:3, 0].copy()


def create_trajectory_canvas(
    size: int,
    history: Sequence[np.ndarray],
    pixels_per_unit: float,
    grid_spacing: int,
) -> np.ndarray:
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    canvas[:] = (10, 10, 12)
    center = size // 2

    for offset in range(0, size // 2 + 1, max(1, grid_spacing)):
        color = (30, 30, 36) if offset % (grid_spacing * 5) else (45, 45, 54)
        cv2.line(canvas, (center - offset, 0), (center - offset, size), color, 1, cv2.LINE_AA)
        cv2.line(canvas, (center + offset, 0), (center + offset, size), color, 1, cv2.LINE_AA)
        cv2.line(canvas, (0, center - offset), (size, center - offset), color, 1, cv2.LINE_AA)
        cv2.line(canvas, (0, center + offset), (size, center + offset), color, 1, cv2.LINE_AA)

    cv2.line(canvas, (center, 0), (center, size), (120, 120, 120), 2, cv2.LINE_AA)
    cv2.line(canvas, (0, center), (size, center), (120, 120, 120), 2, cv2.LINE_AA)
    cv2.putText(
        canvas,
        "X",
        (size - 35, center - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (180, 180, 180),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "Z",
        (center + 8, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (180, 180, 180),
        2,
        cv2.LINE_AA,
    )

    if len(history) >= 2:
        pts = []
        for position in history:
            pos = np.asarray(position, dtype=np.float64).reshape(3)
            x = int(center + pos[0] * pixels_per_unit)
            z = int(center - pos[2] * pixels_per_unit)
            pts.append((x, z))

        for i in range(1, len(pts)):
            cv2.line(canvas, pts[i - 1], pts[i], (0, 200, 255), 2, cv2.LINE_AA)

        for pt in pts[-20:]:
            cv2.circle(canvas, pt, 3, (80, 255, 120), -1, cv2.LINE_AA)

        cv2.circle(canvas, pts[0], 5, (255, 120, 0), -1, cv2.LINE_AA)
        cv2.circle(canvas, pts[-1], 7, (0, 255, 255), -1, cv2.LINE_AA)

    draw_text(
        canvas,
        [
            "Trajectory",
            f"History: {len(history)}",
            "Origin marked in orange",
        ],
        origin=(18, 28),
        line_spacing=22,
        color=(235, 235, 235),
        font_scale=0.6,
        thickness=1,
    )
    return canvas
