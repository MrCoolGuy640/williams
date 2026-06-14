from pathlib import Path
import numpy as np
import cv2
import requests
import imageio.v2 as imageio2
import imageio.v3 as imageio3
from io import BytesIO



class Gif:
    def __init__(self, frames: list[np.ndarray], durations: list[float]):
        """
        frames: BGR numpy arrays (OpenCV-ready)
        durations: milliseconds per frame
        """
        self.frames = frames
        self.durations = durations


    @classmethod
    def from_file(cls, path) -> "Gif":
        path = str(Path(path))

        raw_frames = imageio3.imread(path, index=None)  # (T, H, W, C) RGBA/RGB

        frames = []
        durations = []

        meta = imageio3.immeta(path, index=None)

        # imageio gives per-frame duration in ms (usually)
        frame_durations = meta.get("duration", None)

        for i, frame in enumerate(raw_frames):
            frame = cls._to_bgr(frame)
            frames.append(frame)

            if isinstance(frame_durations, (list, tuple)):
                durations.append(frame_durations[i])
            else:
                durations.append(frame_durations or 100)

        return cls(frames, durations)

    # @classmethod
    # def from_url(cls, url: str) -> "Gif":
    #     r = requests.get(url, timeout=10)
    #     r.raise_for_status()

    #     data = iio.imread(r.content, index=None, extension=".gif")

    #     frames = [cls._to_bgr(f) for f in data]
    #     durations = [100] * len(frames)  # fallback (URLs often lose metadata)

    #     return cls(frames, durations)
    @classmethod
    def from_url(cls, url: str) -> "Gif":
        r = requests.get(url, timeout=10)
        r.raise_for_status()

        buffer = BytesIO(r.content)

        reader = imageio2.get_reader(buffer, format="GIF")

        frames = []
        durations = []

        for frame in reader:
            meta = reader.get_meta_data()

            frames.append(cls._to_bgr(frame))

            duration = meta.get("duration", 0.1)
            durations.append(int(duration * 1000))

        reader.close()

        return cls(frames, durations)


    @staticmethod
    def _to_bgr(frame: np.ndarray) -> np.ndarray:
        """
        Convert imageio frame (RGB/RGBA) → OpenCV BGR
        """
        if frame.shape[-1] == 4:
            frame = frame[:, :, :3]

        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def __len__(self):
        return len(self.frames)

    def __getitem__(self, idx):
        return self.frames[idx]

    def to_numpy(self) -> np.ndarray:
        return np.stack(self.frames, axis=0)


    def iter_frames(self, loop: bool = True):
        """
        Yields frames with correct timing info (for rendering systems).
        """
        while True:
            for frame, dt in zip(self.frames, self.durations):
                yield frame, dt / 1000.0
            if not loop:
                break


    def compare_frame(self, frame_index: int, template: np.ndarray) -> float:
        """
        Match template against a GIF frame using OpenCV.
        """
        frame = self.frames[frame_index]

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        res = cv2.matchTemplate(gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        return float(np.max(res))

    def best_match(self, template: np.ndarray) -> tuple[int, float]:
        """
        Returns (best_frame_index, score)
        """
        best_i = -1
        best_score = -1.0

        for i, frame in enumerate(self.frames):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

            res = cv2.matchTemplate(gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
            score = float(np.max(res))

            if score > best_score:
                best_score = score
                best_i = i

        return best_i, best_score


    def resize(self, width: int, height: int):
        self.frames = [
            cv2.resize(f, (width, height), interpolation=cv2.INTER_AREA)
            for f in self.frames
        ]
        return self

    def grayscale(self):
        self.frames = [
            cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in self.frames
        ]
        return self



    def save(self, path: str):
        """
        Proper GIF save (keeps animation + timing).
        """
        rgb_frames = [
            cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
            for f in self.frames
        ]

        imageio3.imwrite(
            path,
            rgb_frames,
            duration=[d / 1000 for d in self.durations],
            loop=0
        )