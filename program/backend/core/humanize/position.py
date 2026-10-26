"""点击位置：别每次都点同一个像素。"""

from __future__ import annotations

import random

DEFAULT_SIGMA = 1 / 6
"""标准差相对边长的比例。

取 1/6 是因为 ±3σ 正好覆盖整个边长，99.7% 的采样自然落在框内，
剩下 0.3% 夹到边界上——既保留「中心密、边缘疏」的形状，又不会点到框外。
"""


def point_in_box(
    box: tuple[int, int, int, int], sigma: float = DEFAULT_SIGMA
) -> tuple[int, int]:
    """在矩形 (x1, y1, x2, y2) 内按正态分布取一个点。

    为什么不是均匀分布：
        人点按钮是「瞄准中心、手抖」，所以中心密集、边缘稀疏。
        均匀分布每个像素等概率，反而不像人。

    sigma=0 时返回精确中心点（调试或需要确定性时用）。
    """
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"矩形不合法：{box}")

    width = x2 - x1
    height = y2 - y1
    center_x = x1 + width / 2
    center_y = y1 + height / 2

    if sigma <= 0:
        return int(round(center_x)), int(round(center_y))

    spread_x = max(1.0, width * sigma)
    spread_y = max(1.0, height * sigma)

    px = min(max(random.gauss(center_x, spread_x), x1), x2 - 1)
    py = min(max(random.gauss(center_y, spread_y), y1), y2 - 1)
    return int(round(px)), int(round(py))
