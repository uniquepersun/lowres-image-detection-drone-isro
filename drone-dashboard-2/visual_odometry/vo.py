"""Monocular visual odometry pipeline built on OpenCV.

The implementation is intentionally explicit: feature detection, tracking,
outlier rejection, pose recovery, scale estimation, filtering, and rendering are
kept in separate methods so the pipeline is easy to audit and extend.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Deque, Sequence

import cv2
import numpy as np

try:  # Support both ``python main.py`` and ``import visual_odometry.vo``.
    from .config import Config, build_default_config
    from .utils import (
        AngleWindow,
        ConstantVelocityKalman,
        ExponentialMovingAverage,
        RunningAverage,
        clip_points,
        compute_median_displacement,
        create_trajectory_canvas,
        draw_text,
        point_mask,
        rotation_matrix_to_euler_zyx,
        to_cv_points,
        to_gray,
    )
except ImportError:  # pragma: no cover - fallback for script execution
    from config import Config, build_default_config
    from utils import (
        AngleWindow,
        ConstantVelocityKalman,
        ExponentialMovingAverage,
        RunningAverage,
        clip_points,
        compute_median_displacement,
        create_trajectory_canvas,
        draw_text,
        point_mask,
        rotation_matrix_to_euler_zyx,
        to_cv_points,
        to_gray,
    )


@dataclass(slots=True)
class FrameResult:
    overlay: np.ndarray
    trajectory: np.ndarray
    frame_index: int
    fps: float
    tracked_features: int
    inliers: int
    tracking_percentage: float
    tracking_error: float
    reprojection_error: float
    scale: float
    position: np.ndarray
    orientation_deg: np.ndarray
    confidence: float
    status: str


class VisualOdometry:
    """Stateful monocular VO estimator."""

    def __init__(self, config: Config | None = None):
        self.cfg = config or build_default_config()
        self.K = self.cfg.camera_matrix
        self.K_inv = np.linalg.inv(self.K)

        self.orb = cv2.ORB_create(
            nfeatures=self.cfg.orb_nfeatures,
            scaleFactor=self.cfg.orb_scale_factor,
            nlevels=self.cfg.orb_nlevels,
            fastThreshold=self.cfg.orb_fast_threshold,
        )

        self.prev_gray: np.ndarray | None = None
        self.points: np.ndarray = np.zeros((0, 2), dtype=np.float32)

        self.R_global_raw = np.eye(3, dtype=np.float64)
        self.T_global_raw = np.zeros(3, dtype=np.float64)

        self.display_position = np.zeros(3, dtype=np.float64)
        self.display_orientation = np.zeros(3, dtype=np.float64)

        self.position_ema = ExponentialMovingAverage(self.cfg.ema_alpha)
        self.position_window = RunningAverage(self.cfg.moving_average_window)
        self.position_median_window = RunningAverage(self.cfg.median_window)

        self.orientation_ema = ExponentialMovingAverage(self.cfg.ema_alpha)
        self.orientation_window = AngleWindow(self.cfg.moving_average_window)
        self.orientation_median_window = AngleWindow(self.cfg.median_window)

        self.scale_ema = ExponentialMovingAverage(self.cfg.scale_smoothing_alpha)
        self.confidence_ema = ExponentialMovingAverage(self.cfg.confidence_alpha)
        self.kalman = (
            ConstantVelocityKalman(
                process_noise=self.cfg.kalman_process_noise,
                measurement_noise=self.cfg.kalman_measurement_noise,
            )
            if self.cfg.enable_kalman_filter
            else None
        )

        self.frame_index = 0
        self.last_scale = 0.0
        self.last_tracking_error = 0.0
        self.last_reprojection_error = 0.0
        self.last_tracking_percentage = 0.0
        self.last_confidence = 0.0
        self.last_status = "INITIALIZING"
        self.last_inlier_count = 0
        self.last_tracked_count = 0
        self.last_motion_disp = 0.0
        self.last_motion_step = np.zeros(3, dtype=np.float64)
        self.last_valid_update = False
        self.last_rotation_deg = 0.0
        self.last_good_prev = np.zeros((0, 2), dtype=np.float32)
        self.last_good_curr = np.zeros((0, 2), dtype=np.float32)
        self.last_inlier_prev = np.zeros((0, 2), dtype=np.float32)
        self.last_inlier_curr = np.zeros((0, 2), dtype=np.float32)
        self.last_inlier_mask: np.ndarray | None = None

        self.trajectory_history: Deque[np.ndarray] = deque(maxlen=self.cfg.trajectory_history_size)
        self.last_frame_size: tuple[int, int] = (self.cfg.frame_width, self.cfg.frame_height)

    def reset(self) -> None:
        self.prev_gray = None
        self.points = np.zeros((0, 2), dtype=np.float32)
        self.R_global_raw = np.eye(3, dtype=np.float64)
        self.T_global_raw = np.zeros(3, dtype=np.float64)
        self.display_position = np.zeros(3, dtype=np.float64)
        self.display_orientation = np.zeros(3, dtype=np.float64)
        self.position_ema.reset()
        self.position_window.clear()
        self.position_median_window.clear()
        self.orientation_ema.reset()
        self.orientation_window.clear()
        self.orientation_median_window.clear()
        self.scale_ema.reset()
        self.confidence_ema.reset()
        if self.kalman is not None:
            self.kalman.reset()
        self.frame_index = 0
        self.last_scale = 0.0
        self.last_tracking_error = 0.0
        self.last_reprojection_error = 0.0
        self.last_tracking_percentage = 0.0
        self.last_confidence = 0.0
        self.last_status = "RESET"
        self.last_inlier_count = 0
        self.last_tracked_count = 0
        self.last_motion_disp = 0.0
        self.last_motion_step = np.zeros(3, dtype=np.float64)
        self.last_valid_update = False
        self.last_rotation_deg = 0.0
        self.last_good_prev = np.zeros((0, 2), dtype=np.float32)
        self.last_good_curr = np.zeros((0, 2), dtype=np.float32)
        self.last_inlier_prev = np.zeros((0, 2), dtype=np.float32)
        self.last_inlier_curr = np.zeros((0, 2), dtype=np.float32)
        self.last_inlier_mask = None
        self.trajectory_history.clear()

    def _detect_features(self, gray: np.ndarray, existing_points: np.ndarray, limit: int | None = None) -> np.ndarray:
        max_new = self.cfg.feature_redetect_batch if limit is None else int(limit)
        if max_new <= 0:
            return np.zeros((0, 2), dtype=np.float32)
        mask = point_mask(gray.shape, existing_points, self.cfg.min_feature_spacing_px)
        keypoints = self.orb.detect(gray, mask)
        if not keypoints:
            return np.zeros((0, 2), dtype=np.float32)
        keypoints = sorted(keypoints, key=lambda kp: kp.response, reverse=True)
        points = np.array([kp.pt for kp in keypoints[:max_new]], dtype=np.float32)
        points = clip_points(points, gray.shape[1], gray.shape[0])
        return points.astype(np.float32, copy=False)

    def _track_points(self, prev_gray: np.ndarray, gray: np.ndarray, points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if len(points) == 0:
            empty = np.zeros((0, 2), dtype=np.float32)
            return empty, empty, np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)

        p0 = to_cv_points(points)
        p1, st1, err1 = cv2.calcOpticalFlowPyrLK(
            prev_gray,
            gray,
            p0,
            None,
            winSize=self.cfg.lk_win_size,
            maxLevel=self.cfg.lk_max_level,
            criteria=self.cfg.lk_criteria,
        )
        if p1 is None or st1 is None or err1 is None:
            empty = np.zeros((0, 2), dtype=np.float32)
            return empty, empty, np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)

        p0_back, st2, err2 = cv2.calcOpticalFlowPyrLK(
            gray,
            prev_gray,
            p1,
            None,
            winSize=self.cfg.lk_win_size,
            maxLevel=self.cfg.lk_max_level,
            criteria=self.cfg.lk_criteria,
        )
        if p0_back is None or st2 is None or err2 is None:
            empty = np.zeros((0, 2), dtype=np.float32)
            return empty, empty, np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)

        prev_pts = points.reshape(-1, 2)
        curr_pts = p1.reshape(-1, 2)
        back_pts = p0_back.reshape(-1, 2)
        lk_err = err1.reshape(-1).astype(np.float64)
        fb_err = np.linalg.norm(prev_pts - back_pts, axis=1)
        valid = (
            (st1.reshape(-1) > 0)
            & (st2.reshape(-1) > 0)
            & np.isfinite(fb_err)
            & np.isfinite(lk_err)
            & (fb_err <= self.cfg.lk_forward_backward_threshold)
            & (lk_err <= self.cfg.lk_max_error)
        )

        return (
            prev_pts[valid].astype(np.float32, copy=False),
            curr_pts[valid].astype(np.float32, copy=False),
            fb_err[valid],
            lk_err[valid],
        )

    def _estimate_pose(
        self,
        prev_pts: np.ndarray,
        curr_pts: np.ndarray,
    ) -> tuple[bool, np.ndarray | None, np.ndarray | None, np.ndarray | None, np.ndarray | None, float, float, int]:
        if len(prev_pts) < self.cfg.min_tracked_for_pose or len(curr_pts) < self.cfg.min_tracked_for_pose:
            return False, None, None, None, None, 0.0, 0.0, 0

        essential, mask = cv2.findEssentialMat(
            prev_pts,
            curr_pts,
            cameraMatrix=self.K,
            method=cv2.RANSAC,
            prob=self.cfg.essential_ransac_prob,
            threshold=self.cfg.essential_ransac_threshold,
            maxIters=self.cfg.essential_ransac_max_iters,
        )
        if essential is None or mask is None:
            return False, None, None, None, None, 0.0, 0.0, 0

        if essential.ndim == 3:
            essential = essential[0]

        inlier_mask = mask.reshape(-1) > 0
        inlier_prev = prev_pts[inlier_mask]
        inlier_curr = curr_pts[inlier_mask]
        if len(inlier_prev) < self.cfg.min_tracked_for_pose:
            return False, None, None, None, None, 0.0, 0.0, 0

        _, R_rel, t_rel, pose_mask = cv2.recoverPose(
            essential,
            inlier_prev,
            inlier_curr,
            cameraMatrix=self.K,
        )
        if pose_mask is None:
            return False, None, None, None, None, 0.0, 0.0, 0

        pose_inliers = pose_mask.reshape(-1) > 0
        final_prev = inlier_prev[pose_inliers]
        final_curr = inlier_curr[pose_inliers]
        if len(final_prev) < self.cfg.min_tracked_for_pose:
            return False, None, None, None, None, 0.0, 0.0, 0

        reprojection_error = self._reprojection_error(R_rel, t_rel, final_prev, final_curr)
        tracking_error = float(np.mean(np.linalg.norm(final_curr - final_prev, axis=1)))
        inlier_count = int(len(final_prev))

        return True, R_rel, t_rel.reshape(3), final_prev, final_curr, reprojection_error, tracking_error, inlier_count

    def _reprojection_error(
        self,
        R_rel: np.ndarray,
        t_rel: np.ndarray,
        pts1: np.ndarray,
        pts2: np.ndarray,
    ) -> float:
        if len(pts1) == 0 or len(pts2) == 0:
            return 0.0
        P1 = self.K @ np.hstack((np.eye(3, dtype=np.float64), np.zeros((3, 1), dtype=np.float64)))
        P2 = self.K @ np.hstack((R_rel.astype(np.float64), t_rel.reshape(3, 1).astype(np.float64)))
        pts4d = cv2.triangulatePoints(P1, P2, pts1.T.astype(np.float64), pts2.T.astype(np.float64))
        pts4d /= np.maximum(pts4d[3:4], 1e-12)
        proj1 = P1 @ pts4d
        proj2 = P2 @ pts4d
        proj1 = proj1[:2] / np.maximum(proj1[2:3], 1e-12)
        proj2 = proj2[:2] / np.maximum(proj2[2:3], 1e-12)
        err1 = np.linalg.norm(proj1.T - pts1, axis=1)
        err2 = np.linalg.norm(proj2.T - pts2, axis=1)
        return float(np.mean(0.5 * (err1 + err2)))

    def _apply_scale_and_motion_gates(
        self,
        R_rel: np.ndarray,
        t_rel: np.ndarray,
        prev_pts: np.ndarray,
        curr_pts: np.ndarray,
    ) -> tuple[bool, np.ndarray, float, float, float]:
        motion_disp = compute_median_displacement(prev_pts, curr_pts)
        rot_vec, _ = cv2.Rodrigues(R_rel)
        rotation_deg = float(np.linalg.norm(rot_vec) * 180.0 / math.pi)

        if rotation_deg > self.cfg.max_rotation_deg_per_frame:
            return False, np.zeros(3, dtype=np.float64), 0.0, motion_disp, rotation_deg

        if motion_disp < self.cfg.min_motion_displacement_px and rotation_deg < 0.25 * self.cfg.max_rotation_deg_per_frame:
            return False, np.zeros(3, dtype=np.float64), 0.0, motion_disp, rotation_deg

        raw_scale = self.cfg.scale_gain * motion_disp
        raw_scale = float(np.clip(raw_scale, self.cfg.min_scale, self.cfg.max_scale))
        if self.scale_ema.value is None:
            scale = raw_scale
        else:
            scale = float(self.scale_ema.update(np.array([raw_scale], dtype=np.float64))[0])
        if self.scale_ema.value is None:
            self.scale_ema.update(np.array([raw_scale], dtype=np.float64))

        t_vec = t_rel.astype(np.float64).reshape(3)
        if motion_disp < self.cfg.min_motion_displacement_px:
            t_vec = np.zeros(3, dtype=np.float64)
        else:
            t_vec = t_vec * scale

        norm = float(np.linalg.norm(t_vec))
        if norm > self.cfg.max_translation_step:
            t_vec = t_vec / norm * self.cfg.max_translation_step

        if not np.all(np.isfinite(t_vec)):
            return False, np.zeros(3, dtype=np.float64), 0.0, motion_disp, rotation_deg

        if np.linalg.norm(t_vec) == 0.0 and rotation_deg < 0.25 * self.cfg.max_rotation_deg_per_frame:
            return False, np.zeros(3, dtype=np.float64), scale, motion_disp, rotation_deg

        return True, t_vec, scale, motion_disp, rotation_deg

    def _smooth_position(self, measurement: np.ndarray, dt: float, accepted: bool) -> np.ndarray:
        if not accepted:
            if self.kalman is not None:
                return self.kalman.predict(dt)
            return self.display_position.copy()

        value = np.asarray(measurement, dtype=np.float64)
        if self.cfg.enable_median_filter:
            self.position_median_window.append(value)
            value = self.position_median_window.median()
        if self.cfg.enable_moving_average:
            self.position_window.append(value)
            value = self.position_window.mean()
        if self.cfg.enable_ema:
            value = self.position_ema.update(value)
        if self.kalman is not None:
            self.kalman.predict(dt)
            value = self.kalman.update(value)
        return value

    def _smooth_orientation(self, measurement: np.ndarray, accepted: bool) -> np.ndarray:
        if not accepted:
            return self.display_orientation.copy()

        value = np.asarray(measurement, dtype=np.float64)
        if self.cfg.enable_median_filter:
            self.orientation_median_window.append(value)
            value = self.orientation_median_window.median()
        if self.cfg.enable_moving_average:
            self.orientation_window.append(value)
            value = self.orientation_window.mean()
        if self.cfg.enable_ema:
            value = self.orientation_ema.update(value)
        return value

    def _compute_confidence(
        self,
        tracked_count: int,
        inlier_count: int,
        tracking_error: float,
        reprojection_error: float,
        scale: float,
        motion_disp: float,
        rotation_deg: float,
        accepted: bool,
    ) -> float:
        tracked_ratio = min(1.0, tracked_count / max(self.cfg.orb_nfeatures * 0.35, 1.0))
        inlier_ratio = inlier_count / max(tracked_count, 1)
        tracking_quality = 1.0 - min(tracking_error / max(self.cfg.lk_forward_backward_threshold * 3.0, 1.0), 1.0)
        reprojection_quality = 1.0 - min(reprojection_error / 6.0, 1.0)
        motion_quality = 1.0 if accepted else 0.35
        expected_motion = self.cfg.min_motion_displacement_px
        motion_consistency = 1.0 - min(abs(motion_disp - expected_motion) / max(expected_motion * 6.0, 1e-6), 1.0)
        rotation_consistency = 1.0 - min(rotation_deg / max(self.cfg.max_rotation_deg_per_frame, 1e-6), 1.0)
        scale_consistency = 1.0 - min(abs(scale - self.last_scale) / max(self.last_scale + 1e-6, 0.15), 1.0)
        consistency_quality = max(0.0, min(1.0, 0.4 * motion_consistency + 0.35 * rotation_consistency + 0.25 * scale_consistency))

        raw = 100.0 * (
            0.28 * tracked_ratio
            + 0.24 * inlier_ratio
            + 0.16 * tracking_quality
            + 0.16 * reprojection_quality
            + 0.16 * motion_quality
        )
        raw = max(0.0, min(100.0, raw * consistency_quality))
        if self.confidence_ema.value is None:
            return raw
        return float(self.confidence_ema.update(np.array([raw], dtype=np.float64))[0])

    def _draw_tracks(
        self,
        frame: np.ndarray,
        prev_pts: np.ndarray,
        curr_pts: np.ndarray,
        inlier_mask: np.ndarray | None,
    ) -> None:
        if len(prev_pts) == 0 or len(curr_pts) == 0:
            return

        total = len(prev_pts)
        stride = max(1, total // 1200)
        for idx in range(0, total, stride):
            p0 = tuple(np.round(prev_pts[idx]).astype(int))
            p1 = tuple(np.round(curr_pts[idx]).astype(int))
            if inlier_mask is None:
                color = self.cfg.motion_vector_color
            else:
                color = self.cfg.tracked_point_color if inlier_mask[idx] else self.cfg.rejected_point_color
            cv2.line(frame, p0, p1, color, 1, cv2.LINE_AA)
            cv2.circle(frame, p1, self.cfg.point_radius, color, -1, cv2.LINE_AA)

    def _build_overlay(
        self,
        frame: np.ndarray,
        position: np.ndarray,
        orientation_deg: np.ndarray,
        confidence: float,
        fps: float,
        scale: float,
        status: str,
    ) -> np.ndarray:
        overlay = frame.copy()
        inlier_mask = self.last_inlier_mask
        if inlier_mask is not None and len(inlier_mask) != len(self.last_good_prev):
            inlier_mask = None
        self._draw_tracks(
            overlay,
            self.last_good_prev,
            self.last_good_curr,
            inlier_mask,
        )

        panel = overlay.copy()
        cv2.rectangle(panel, (8, 8), (560, 330), self.cfg.panel_color, -1)
        cv2.addWeighted(panel, 0.55, overlay, 0.45, 0.0, overlay)

        yaw, pitch, roll = orientation_deg
        lines = [
            f"Status: {status}",
            f"Frame: {self.frame_index}",
            f"FPS: {fps:.2f}",
            f"Tracked: {self.last_tracked_count}",
            f"Inliers: {self.last_inlier_count}",
            f"Tracking %: {self.last_tracking_percentage:.1f}",
            f"Tracking err: {self.last_tracking_error:.3f}",
            f"Reproj err: {self.last_reprojection_error:.3f}",
            f"Scale: {scale:.4f}",
            f"Confidence: {confidence:5.1f}",
            f"X: {position[0]:.4f}",
            f"Y: {position[1]:.4f}",
            f"Z: {position[2]:.4f}",
            f"Yaw: {yaw:.2f} deg",
            f"Pitch: {pitch:.2f} deg",
            f"Roll: {roll:.2f} deg",
        ]
        draw_text(
            overlay,
            lines,
            origin=(18, 36),
            line_spacing=18,
            color=self.cfg.text_color,
            font_scale=self.cfg.overlay_font_scale,
            thickness=self.cfg.overlay_font_thickness,
        )
        return overlay

    def _replenish_features(self, gray: np.ndarray) -> None:
        if len(self.points) >= self.cfg.feature_redetect_threshold:
            return
        missing = self.cfg.orb_nfeatures - len(self.points)
        if missing <= 0:
            return
        fresh = self._detect_features(gray, self.points, min(self.cfg.feature_redetect_batch, missing))
        if len(fresh) == 0:
            return
        if len(self.points) == 0:
            self.points = fresh
        else:
            self.points = np.vstack([self.points, fresh]).astype(np.float32, copy=False)

    def _initialize_if_needed(self, gray: np.ndarray) -> None:
        if self.prev_gray is not None:
            return
        self.prev_gray = gray
        self.points = self._detect_features(gray, np.zeros((0, 2), dtype=np.float32), self.cfg.orb_nfeatures)

    def process_frame(self, frame: np.ndarray, dt: float) -> FrameResult:
        self.frame_index += 1
        self.last_frame_size = (frame.shape[1], frame.shape[0])
        gray = to_gray(frame)
        self._initialize_if_needed(gray)

        if self.prev_gray is None:
            self.prev_gray = gray

        status = "INITIALIZING"
        accepted_update = False
        scale = self.last_scale
        reprojection_error = 0.0
        tracking_error = 0.0
        inlier_count = 0
        tracking_percentage = 0.0
        position_for_display = self.display_position.copy()
        orientation_for_display = self.display_orientation.copy()

        if len(self.points) == 0:
            self.points = self._detect_features(gray, np.zeros((0, 2), dtype=np.float32), self.cfg.orb_nfeatures)
            self.prev_gray = gray
            self.last_good_prev = np.zeros((0, 2), dtype=np.float32)
            self.last_good_curr = np.zeros((0, 2), dtype=np.float32)
            self.last_inlier_mask = None
            self.last_tracked_count = 0
            self.last_inlier_count = 0
            self.last_tracking_percentage = 0.0
            self.last_reprojection_error = 0.0
            self.last_tracking_error = 0.0
            self.last_motion_disp = 0.0
            self.last_rotation_deg = 0.0
            status = "REINITIALIZING"
        else:
            prev_pts, curr_pts, fb_err, lk_err = self._track_points(self.prev_gray, gray, self.points)
            self.last_good_prev = prev_pts
            self.last_good_curr = curr_pts
            self.last_tracked_count = len(curr_pts)
            tracking_percentage = 100.0 * len(curr_pts) / max(len(self.points), 1)
            self.last_tracking_percentage = tracking_percentage
            tracking_error = float(np.mean(fb_err)) if len(fb_err) else 0.0
            self.last_tracking_error = tracking_error

            if len(curr_pts) < self.cfg.min_tracked_for_pose:
                status = "INSUFFICIENT TRACKS"
                self.points = curr_pts
                self.prev_gray = gray
                self.last_inlier_count = 0
                self.last_reprojection_error = 0.0
                self.last_motion_disp = 0.0
                self.last_rotation_deg = 0.0
            else:
                ok, R_rel, t_rel, pose_prev, pose_curr, reproj_err, track_err_pose, inlier_count = self._estimate_pose(prev_pts, curr_pts)
                if not ok or R_rel is None or t_rel is None or pose_prev is None:
                    status = "POSE FAILED"
                    self.points = curr_pts
                    self.prev_gray = gray
                    self.last_inlier_count = 0
                    self.last_reprojection_error = 0.0
                    self.last_motion_disp = 0.0
                    self.last_rotation_deg = 0.0
                else:
                    pose_prev = pose_prev.astype(np.float32, copy=False)
                    pose_curr = pose_curr.astype(np.float32, copy=False)
                    motion_ok, t_step, scale, motion_disp, rotation_deg = self._apply_scale_and_motion_gates(
                        R_rel,
                        t_rel,
                        pose_prev,
                        pose_curr,
                    )
                    self.last_motion_disp = motion_disp
                    self.last_rotation_deg = rotation_deg
                    reprojection_error = reproj_err
                    tracking_error = track_err_pose
                    self.last_reprojection_error = reprojection_error
                    self.last_tracking_error = tracking_error
                    self.last_inlier_count = inlier_count
                    inlier_ratio = inlier_count / max(len(curr_pts), 1)
                    if not motion_ok:
                        status = "MOTION REJECTED"
                        self.points = curr_pts
                        self.prev_gray = gray
                        self.last_inlier_count = 0
                        self.last_reprojection_error = 0.0
                    else:
                        accepted_update = True
                        self.last_scale = scale
                        if not np.allclose(t_step, 0.0):
                            self.T_global_raw = self.T_global_raw + self.R_global_raw @ t_step
                            self.last_motion_step = t_step.copy()
                        else:
                            self.last_motion_step = np.zeros(3, dtype=np.float64)
                        self.R_global_raw = R_rel @ self.R_global_raw
                        euler_raw = rotation_matrix_to_euler_zyx(self.R_global_raw)
                        position_for_display = self._smooth_position(self.T_global_raw, dt, True)
                        orientation_for_display = self._smooth_orientation(euler_raw, True)
                        self.display_position = position_for_display.copy()
                        self.display_orientation = orientation_for_display.copy()
                        status = "OK" if inlier_ratio >= self.cfg.min_inlier_ratio else "LOW INLIER RATIO"
                        self.points = pose_curr.astype(np.float32, copy=False)
                        self.prev_gray = gray
                        self.last_valid_update = True
                        self.last_good_prev = pose_prev.astype(np.float32, copy=False)
                        self.last_good_curr = pose_curr.astype(np.float32, copy=False)
                        self.last_inlier_prev = pose_prev.astype(np.float32, copy=False)
                        self.last_inlier_curr = pose_curr.astype(np.float32, copy=False)
                        self.last_inlier_mask = np.ones(len(pose_curr), dtype=bool)

        if not accepted_update:
            position_for_display = self._smooth_position(self.T_global_raw, dt, False)
            orientation_for_display = self._smooth_orientation(rotation_matrix_to_euler_zyx(self.R_global_raw), False)
            self.display_position = position_for_display.copy()
            self.display_orientation = orientation_for_display.copy()
            self.last_valid_update = False
            self.last_motion_step = np.zeros(3, dtype=np.float64)
            self.last_inlier_mask = None

        if accepted_update and self.kalman is not None:
            position_for_display = self.display_position.copy()
        elif accepted_update:
            position_for_display = self.display_position.copy()

        if self.cfg.enable_kalman_filter and self.kalman is not None and accepted_update:
            position_for_display = self.kalman.position.copy()

        if accepted_update:
            self.trajectory_history.append(position_for_display.copy())
        else:
            self.trajectory_history.append(self.display_position.copy())

        if len(self.points) < self.cfg.feature_redetect_threshold:
            self._replenish_features(gray)

        confidence = self._compute_confidence(
            tracked_count=self.last_tracked_count,
            inlier_count=self.last_inlier_count,
            tracking_error=self.last_tracking_error,
            reprojection_error=self.last_reprojection_error,
            scale=self.last_scale,
            motion_disp=self.last_motion_disp,
            rotation_deg=self.last_rotation_deg,
            accepted=accepted_update,
        )
        if self.confidence_ema.value is None:
            self.confidence_ema.update(np.array([confidence], dtype=np.float64))
            self.last_confidence = confidence
        else:
            self.last_confidence = float(self.confidence_ema.update(np.array([confidence], dtype=np.float64))[0])

        overlay = self._build_overlay(
            frame,
            self.display_position,
            self.display_orientation,
            self.last_confidence,
            fps=1.0 / max(dt, 1e-6),
            scale=self.last_scale,
            status=status,
        )
        trajectory = create_trajectory_canvas(
            self.cfg.trajectory_canvas_size,
            list(self.trajectory_history),
            self.cfg.trajectory_pixels_per_unit,
            self.cfg.trajectory_grid_spacing,
        )

        if len(self.points) < self.cfg.feature_redetect_threshold:
            self.last_status = f"{status} | REPLENISHING"
        else:
            self.last_status = status

        return FrameResult(
            overlay=overlay,
            trajectory=trajectory,
            frame_index=self.frame_index,
            fps=1.0 / max(dt, 1e-6),
            tracked_features=self.last_tracked_count,
            inliers=self.last_inlier_count,
            tracking_percentage=self.last_tracking_percentage,
            tracking_error=self.last_tracking_error,
            reprojection_error=self.last_reprojection_error,
            scale=self.last_scale,
            position=self.display_position.copy(),
            orientation_deg=self.display_orientation.copy(),
            confidence=self.last_confidence,
            status=self.last_status,
        )
