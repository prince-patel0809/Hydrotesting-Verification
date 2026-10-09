"""Image / video frame sources for the detection pipeline.

Two concrete sources are provided:

* ``VideoSource`` – reads frames from an MP4 / video file in a loop.
  It opens the file once and cycles continuously so the pipeline always
  has a frame to process.  When the last frame is reached it loops back
  to the start, simulating a continuous camera feed from the video.

* ``SampleImageSource`` – legacy single-image source; kept for tests and
  as a fallback when no video is available.

Each source exposes ``.filename``, ``.mode``, and ``.read() -> NDArray``.
``VideoSource`` additionally exposes ``.frame_index`` and ``.total_frames``.
"""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray


class VideoSource:
    """Loops through an MP4 video file, returning one frame per ``read()`` call.

    Thread-safe: ``read()`` may be called from multiple threads (the pipeline
    runs OCR with a ThreadPoolExecutor), but a single internal ``threading.Lock``
    keeps the ``VideoCapture`` state consistent.
    """

    mode = "video-loop"

    def __init__(
        self,
        video_path: Path,
        *,
        sample_every_n_frames: int = 1,
    ) -> None:
        self.video_path = video_path
        self.sample_every_n_frames = max(1, sample_every_n_frames)
        self._lock = threading.Lock()
        self._cap: cv2.VideoCapture | None = None
        self._frame_index = 0
        self._total_frames = 0
        self._open()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def filename(self) -> str:
        return self.video_path.name

    @property
    def frame_index(self) -> int:
        return self._frame_index

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def fps(self) -> float:
        with self._lock:
            if self._cap is None:
                return 0.0
            return float(self._cap.get(cv2.CAP_PROP_FPS))

    def read(self) -> NDArray[np.uint8]:
        """Return the next sampled frame.  Loops when the video ends."""
        with self._lock:
            if self._cap is None or not self._cap.isOpened():
                self._open()

            # Skip frames to hit the desired sample rate
            for _ in range(self.sample_every_n_frames - 1):
                self._cap.grab()
                self._frame_index = (self._frame_index + 1) % max(1, self._total_frames)

            ok, frame = self._cap.read()
            if not ok or frame is None:
                # Loop back to the beginning
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._frame_index = 0
                ok, frame = self._cap.read()

            if not ok or frame is None:
                raise RuntimeError(
                    f"Could not read any frame from video: {self.video_path}"
                )

            self._frame_index = (self._frame_index + 1) % max(1, self._total_frames)
            return frame  # type: ignore[return-value]

    def release(self) -> None:
        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open(self) -> None:
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise FileNotFoundError(
                f"Could not open video source: {self.video_path}"
            )
        self._cap = cap
        self._total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._frame_index = 0


class SampleImageSource:
    """Reads a single static image on every ``read()`` call (legacy / test use)."""

    mode = "sample-image"

    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path

    @property
    def filename(self) -> str:
        return self.image_path.name

    def read(self) -> NDArray[np.uint8]:
        image = cv2.imread(str(self.image_path))
        if image is None:
            raise FileNotFoundError(
                f"Could not read sample image: {self.image_path}"
            )
        return image  # type: ignore[return-value]
