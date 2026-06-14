from pathlib import Path
import numpy as np
import cv2
import requests


class Image:
    def __init__(self, data: np.ndarray):
        self.data = data

    @classmethod
    def from_file(cls, path) -> "Image":
        """
        Load image from file.
        Supports str, Path, or any path-like object.
        """

        path = Path(path) # supports path or str

        data = cv2.imread(str(path), cv2.IMREAD_COLOR)

        if data is None:
            raise ValueError(f"Failed to load image: {path}")

        return cls(data)
    
    @classmethod
    def from_url(cls, url: str, timeout: int = 10) -> "Image":
        """
        Load image from a URL (http/https).
        """
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            raise ValueError(f"Failed to download image from URL: {url}") from e

        img_array = np.frombuffer(response.content, np.uint8)
        data = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if data is None:
            raise ValueError(f"Failed to decode image from URL: {url}")

        return cls(data)

    @classmethod
    def from_array(cls, array: np.ndarray) -> "Image":
        """
        Wrap existing numpy image.
        """
        return cls(array)

    def copy(self):
        return Image(self.data.copy())

    def gray(self):
        """Return grayscale numpy array."""
        return cv2.cvtColor(self.data, cv2.COLOR_BGR2GRAY)

    def crop(self, top_ratio=0, bottom_ratio=1, left_ratio=0, right_ratio=1):
        h, w = self.data.shape[:2]

        y1 = int(h * top_ratio)
        y2 = int(h * bottom_ratio)
        x1 = int(w * left_ratio)
        x2 = int(w * right_ratio)

        return Image(self.data[y1:y2, x1:x2])

    def compare(self, template: "Image") -> float:
        """
        Returns similarity score (0-1) using OpenCV matchTemplate.
        """

        img_gray = self.gray()
        tpl_gray = template.gray()

        res = cv2.matchTemplate(
            img_gray,
            tpl_gray,
            cv2.TM_CCOEFF_NORMED
        )

        return float(np.max(res))

    def matches(self, other: "Image", threshold=0.8) -> bool:
        return self.compare(other) >= threshold