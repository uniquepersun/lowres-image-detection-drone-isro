"""Configuration for the monocular visual odometry demo.

The values below are intentionally exposed as module-level constants so they are
easy to tweak without touching the implementation. The ``Config`` dataclass is
used by the runtime to keep the settings organized and to provide a single
object that can be passed around cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

import cv2
import numpy as np


# Camera intrinsics. Adjust these for your webcam if you know the calibration.
FX = 920.0
FY = 920.0
CX = 640.0
CY = 360.0


@dataclass(slots=True)
class Config:
    # Camera
    frame_width: int = 1280
    frame_height: int = 720
    target_fps: int = 30

    # Intrinsics
    fx: float = FX
    fy: float = FY
    cx: float = CX
    cy: float = CY

    # ORB feature detection
    orb_nfeatures: int = 5000
    orb_scale_factor: float = 1.2
    orb_nlevels: int = 8
    orb_fast_threshold: int = 12
    feature_redetect_threshold: int = 2400
    feature_redetect_batch: int = 1800
    min_feature_spacing_px: int = 12

    # Lucas-Kanade tracking
    lk_win_size: Tuple[int, int] = (21, 21)
    lk_max_level: int = 3
    lk_criteria_eps: float = 0.01
    lk_criteria_count: int = 30
    lk_forward_backward_threshold: float = 1.25
    lk_max_error: float = 14.0

    # Essential matrix / pose recovery
    essential_ransac_threshold: float = 1.0
    essential_ransac_prob: float = 0.999
    essential_ransac_max_iters: int = 2000
    min_tracked_for_pose: int = 30
    min_inlier_ratio: float = 0.22

    # Motion gating and scale
    min_motion_displacement_px: float = 1.5
    max_rotation_deg_per_frame: float = 10.0
    min_scale: float = 0.002
    max_scale: float = 0.30
    scale_gain: float = 0.018
    scale_smoothing_alpha: float = 0.18
    max_translation_step: float = 0.35

    # Filtering
    enable_ema: bool = True
    ema_alpha: float = 0.20
    enable_median_filter: bool = True
    median_window: int = 5
    enable_moving_average: bool = True
    moving_average_window: int = 5
    enable_kalman_filter: bool = True
    kalman_process_noise: float = 0.025
    kalman_measurement_noise: float = 0.20

    # Confidence and display
    confidence_alpha: float = 0.12
    overlay_font_scale: float = 0.55
    overlay_font_thickness: int = 1
    overlay_line_type: int = cv2.LINE_AA
    point_radius: int = 2
    tracked_point_color: Tuple[int, int, int] = (0, 255, 0)
    rejected_point_color: Tuple[int, int, int] = (0, 0, 255)
    motion_vector_color: Tuple[int, int, int] = (255, 180, 0)
    text_color: Tuple[int, int, int] = (240, 240, 240)
    panel_color: Tuple[int, int, int] = (20, 20, 20)

    # Trajectory canvas
    trajectory_canvas_size: int = 1000
    trajectory_pixels_per_unit: float = 80.0
    trajectory_history_size: int = 5000
    trajectory_grid_spacing: int = 100

    # Runtime behavior
    reset_key: str = "r"
    quit_key: str = "q"

    @property
    def camera_matrix(self) -> np.ndarray:
        return np.array(
            [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )

    @property
    def lk_criteria(self) -> tuple[int, int, float]:
        return (
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            self.lk_criteria_count,
            self.lk_criteria_eps,
        )


def build_default_config() -> Config:
    return Config()


__all__ = [
    "FX",
    "FY",
    "CX",
    "CY",
    "Config",
    "build_default_config",
]
