"""模板匹配。

只做「给一张画面 + 一张模板 + 一个 roi，返回得分和位置」这一件事。
上层（workbench、whereami、以后的页面路由）都从这里取结果，
不要在别处直接调 cv2.matchTemplate——否则阈值口径会各不相同。
"""

from __future__ import annotations

import cv2
import numpy as np

from core.vision.roi import roi_to_pixels

METHOD = cv2.TM_CCOEFF_NORMED


def best_match(
    frame: np.ndarray,
    template: np.ndarray,
    roi: list[float],
) -> tuple[float, tuple[int, int] | None]:
    """在 roi 区域内找模板，返回 (最高得分, 左上角像素坐标)。

    roi 区域比模板还小时返回 (0.0, None)——调用方据此判定「框太小」。
    """
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = roi_to_pixels(roi, width, height)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    region = frame[y1:y2, x1:x2]

    template_height, template_width = template.shape[:2]
    if region.shape[0] < template_height or region.shape[1] < template_width:
        return 0.0, None

    result = cv2.matchTemplate(region, template, METHOD)
    _min_value, max_value, _min_loc, max_loc = cv2.minMaxLoc(result)
    return float(max_value), (x1 + max_loc[0], y1 + max_loc[1])


def score(frame: np.ndarray, template: np.ndarray, roi: list[float]) -> float:
    """只关心得分时用这个。"""
    return best_match(frame, template, roi)[0]
