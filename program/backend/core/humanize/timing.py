"""时间：别每次都一样快。

人在游戏里点按钮，两次操作之间不会精确停 0.5 秒；
按下和抬起之间也不会是 0 毫秒。这两件事都是可被识别的特征。

注意：这里只返回「应该等多久」，不负责真的去 sleep。
      真的等由调用方决定——这样这些函数依然是纯函数，可以直接测。
"""

from __future__ import annotations

import random

# 两次操作之间的正常间隔（秒）
DEFAULT_DELAY = (0.3, 1.2)

# 按下到抬起的时长（秒）。真实点击大约 50~150 毫秒
DEFAULT_HOLD = (0.05, 0.12)


def _uniform(bounds: tuple[float, float], name: str) -> float:
    low, high = bounds
    if low < 0 or high < low:
        raise ValueError(f"{name} 区间不合法：{bounds}")
    return random.uniform(low, high)


def delay(bounds: tuple[float, float] = DEFAULT_DELAY) -> float:
    """两次操作之间该停多久（秒）。

    均匀分布而不是正态：人的停顿其实长尾很重（偶尔发呆几秒），
    均匀分布至少保证了「不会每次都一样」这个最低要求。
    真要模拟长尾，以后可以换成对数正态。
    """
    return _uniform(bounds, "delay")


def hold(bounds: tuple[float, float] = DEFAULT_HOLD) -> float:
    """按下到抬起之间该停多久（秒）。

    现在 device.tap 是「按下立刻抬起」，等于 0 毫秒——这是明显的脚本特征。
    等 device 层支持按住时长后，用这个值填进去。
    """
    return _uniform(bounds, "hold")
