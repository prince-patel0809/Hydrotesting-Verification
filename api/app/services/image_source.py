from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray


class SampleImageSource:
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path

    @property
    def filename(self) -> str:
        return self.image_path.name

    def read(self) -> NDArray[np.uint8]:
        image = cv2.imread(str(self.image_path))
        if image is None:
            raise FileNotFoundError(f"Could not read sample image: {self.image_path}")
        return image
