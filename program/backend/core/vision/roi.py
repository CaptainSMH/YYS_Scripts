"""roi（搜索区域）与像素坐标之间的换算。

约定：
    · roi 用归一化的 [x1, y1, x2, y2]（0~1），与分辨率无关
    · 像素坐标是画面内的绝对像素，左上角为 (0, 0)
"""

from __future__ import annotations

# 搜索区域在模板四周各外扩多少像素
# 用固定值而不是按框大小的比例：元素漂移是绝对像素，
# 按比例扩会让大元素的搜索区域膨胀到半个屏幕，既慢又容易误匹配。
ROI_MARGIN = 60


def expand_roi(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
    margin: int = ROI_MARGIN,
) -> list[float]:
    """把框选的像素矩形四周外扩 margin 像素，转成归一化 roi。"""
    x1, y1, x2, y2 = box
    return [
        round(max(0, x1 - margin) / width, 4),
        round(max(0, y1 - margin) / height, 4),
        round(min(width, x2 + margin) / width, 4),
        round(min(height, y2 + margin) / height, 4),
    ]


def roi_to_pixels(roi: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    """归一化 roi 转成像素矩形。"""
    return (
        int(round(roi[0] * width)),
        int(round(roi[1] * height)),
        int(round(roi[2] * width)),
        int(round(roi[3] * height)),
    )


def pixels_to_roi(box: tuple[int, int, int, int], width: int, height: int) -> list[float]:
    """像素矩形转成归一化 roi，并夹在画面范围内。"""
    x1, y1, x2, y2 = box
    return [
        round(max(0, x1) / width, 4),
        round(max(0, y1) / height, 4),
        round(min(width, x2) / width, 4),
        round(min(height, y2) / height, 4),
    ]


def clamp_box(
    box: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int]:
    """把像素矩形限制在画面内。"""
    x1, y1, x2, y2 = box
    return (
        max(0, min(x1, width)),
        max(0, min(y1, height)),
        max(0, min(x2, width)),
        max(0, min(y2, height)),
    )
