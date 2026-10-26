"""图像文件读写。

为什么单独一个模块：
    · 读图的地方太多（页面判定、元素定位、命中报告、工作台），
      以前每个地方都抄一遍 np.fromfile + cv2.imdecode
    · 不用 cv2.imread / cv2.imwrite —— 它们在 Windows 上不支持中文路径，
      而我们的实例名、页面名、产物目录都可能是中文

约定：文件不存在、是空文件、或者解码失败，读图一律返回 None，
      让调用方自己决定报什么错（配置错误？画面问题？两边含义不同）。
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def load_image(path: str | Path) -> np.ndarray | None:
    """读一张图，失败返回 None。

    文件不存在、是空文件、或者解码失败，一律返回 None——
    调用方据此决定报「配置错误」还是「画面问题」。
    """
    target = Path(path)
    if not target.exists():
        return None

    try:
        data = np.fromfile(str(target), np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def save_image(path: str | Path, image: np.ndarray) -> Path:
    """写一张 PNG（覆盖），返回路径；父目录不存在会自动建。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError(f"PNG 编码失败：{target}")
    buffer.tofile(str(target))
    return target
