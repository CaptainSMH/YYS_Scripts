"""模板质量检查。

为什么需要：
    OpenCV 的 TM_CCOEFF_NORMED 对「常数模板」的分母为 0，会恒定返回 1.0。
    也就是说，一块纯色区域被存成模板后，它会在任何画面上都「完美匹配」，
    而且位置固定在 roi 的左上角——静默点到完全错误的地方，还不报错。

    实测：30x30 纯色块在任何画面上的得分都是 1.000。
    现有正常模板的灰度标准差都在 55 以上，所以用 5.0 作为分界线很安全。
"""

from __future__ import annotations

import cv2
import numpy as np

MIN_CONTRAST = 5.0
"""灰度标准差低于这个值就认为「没有纹理」，不适合做模板。"""


def contrast(image: np.ndarray) -> float:
    """灰度标准差，粗略衡量这块区域有没有纹理。"""
    if image.size == 0:
        return 0.0
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return float(gray.std())


def is_textureless(image: np.ndarray, threshold: float = MIN_CONTRAST) -> bool:
    """这块区域是否几乎没有纹理（纯色或接近纯色）。"""
    return contrast(image) < threshold
