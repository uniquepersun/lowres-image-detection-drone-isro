"""
object_matcher.py

Lightweight, CPU-only image matching: given up to 3 reference ("target")
images, search each incoming camera frame for them using ORB feature
matching + homography (RANSAC). This is the same family of technique as
classic AR marker tracking - it works well for distinct, textured/planar
targets (printed markers, logos, distinctive objects/signage) but is not
a general object detector and won't reliably find things like faces or
generic scenes.

Two pieces:
  - ReferenceStore   - holds ORB keypoints/descriptors for each uploaded
                        target image (slots 1, 2, 3)
  - MatchStore        - holds the latest match result per slot, read by
                        the /matches WebSocket

start_matching_thread() runs the search loop on a background thread so it
never blocks the camera stream or telemetry WebSocket. It's throttled to
MATCH_LOOP_HZ to keep CPU usage predictable alongside RTAB-Map/MAVROS.
"""

import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

MIN_MATCH_COUNT = 12       # good matches required before we trust a detection
RATIO_TEST = 0.75          # Lowe's ratio test threshold
ORB_FEATURES = 800
MATCH_LOOP_HZ = 4          # how often we run matching against the latest frame
SLOTS = (1, 2, 3)

_orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
_bf = cv2.BFMatcher(cv2.NORM_HAMMING)


@dataclass
class ReferenceImage:
    slot: int
    keypoints: list
    descriptors: np.ndarray
    width: int
    height: int


@dataclass
class MatchResult:
    slot: int
    loaded: bool = False
    found: bool = False
    confidence: float = 0.0
    # 4 normalized (0-1) [x, y] points, TL/TR/BR/BL, in the *frame's*
    # coordinate space - or None if not currently found
    quad: Optional[list] = None


class ReferenceStore:
    """Thread-safe holder for uploaded target images' ORB features."""

    def __init__(self):
        self._lock = threading.Lock()
        self._refs: dict[int, ReferenceImage] = {}

    def set(self, slot: int, image_bytes: bytes) -> bool:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return False
        kp, des = _orb.detectAndCompute(img, None)
        if des is None or len(kp) < MIN_MATCH_COUNT:
            return False
        with self._lock:
            self._refs[slot] = ReferenceImage(
                slot=slot, keypoints=kp, descriptors=des,
                width=img.shape[1], height=img.shape[0],
            )
        return True

    def clear(self, slot: int):
        with self._lock:
            self._refs.pop(slot, None)

    def get(self, slot: int) -> Optional[ReferenceImage]:
        with self._lock:
            return self._refs.get(slot)


class MatchStore:
    """Thread-safe holder for the latest match result per slot."""

    def __init__(self):
        self._lock = threading.Lock()
        self._results: dict[int, MatchResult] = {s: MatchResult(slot=s) for s in SLOTS}

    def update(self, slot: int, **kwargs):
        with self._lock:
            r = self._results.setdefault(slot, MatchResult(slot=slot))
            for k, v in kwargs.items():
                setattr(r, k, v)

    def snapshot(self) -> list[dict]:
        with self._lock:
            out = []
            for s in SLOTS:
                r = self._results.get(s, MatchResult(slot=s))
                out.append({
                    "slot": r.slot,
                    "loaded": r.loaded,
                    "found": r.found,
                    "confidence": round(r.confidence, 2),
                    "quad": r.quad,
                })
            return out


reference_store = ReferenceStore()
match_store = MatchStore()


def _match_against(kp2, des2, frame_w: int, frame_h: int, ref: ReferenceImage):
    if des2 is None or len(kp2) < 2:
        return False, 0.0, None

    matches = _bf.knnMatch(ref.descriptors, des2, k=2)
    good = []
    for pair in matches:
        if len(pair) != 2:
            continue
        m, n = pair
        if m.distance < RATIO_TEST * n.distance:
            good.append(m)

    if len(good) < MIN_MATCH_COUNT:
        return False, 0.0, None

    src_pts = np.float32([ref.keypoints[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if H is None or mask is None:
        return False, 0.0, None

    inliers = int(mask.sum())
    if inliers < MIN_MATCH_COUNT:
        return False, 0.0, None

    w, h = ref.width, ref.height
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(corners, H).reshape(-1, 2)

    quad = [[float(x / frame_w), float(y / frame_h)] for x, y in projected]
    confidence = min(1.0, inliers / max(len(good), 1))
    return True, confidence, quad


def matching_loop(frame_getter):
    """
    frame_getter: callable returning the latest JPEG bytes (or None).
    Runs forever, throttled to MATCH_LOOP_HZ. Computes the current frame's
    ORB features once per iteration, then checks all 3 reference slots
    against them.
    """
    period = 1.0 / MATCH_LOOP_HZ
    while True:
        start = time.time()
        jpeg = frame_getter()
        if jpeg is not None:
            arr = np.frombuffer(jpeg, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            if frame is not None:
                fh, fw = frame.shape[:2]
                kp2, des2 = _orb.detectAndCompute(frame, None)
                for slot in SLOTS:
                    ref = reference_store.get(slot)
                    if ref is None:
                        match_store.update(slot, loaded=False, found=False, confidence=0.0, quad=None)
                        continue
                    found, conf, quad = _match_against(kp2, des2, fw, fh, ref)
                    match_store.update(slot, loaded=True, found=found, confidence=conf, quad=quad)
        elapsed = time.time() - start
        time.sleep(max(0.0, period - elapsed))


def start_matching_thread(frame_getter) -> threading.Thread:
    t = threading.Thread(target=matching_loop, args=(frame_getter,), daemon=True)
    t.start()
    return t
