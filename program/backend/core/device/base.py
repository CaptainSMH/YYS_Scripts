"""设备层的抽象接口。

所有具体后端（Windows 窗口、MuMu 模拟器……）都实现 Device；
上层代码只依赖这份契约，不依赖具体实现。

坐标约定：所有坐标都是「客户区坐标」——去掉标题栏和边框后的画面内坐标，
左上角为 (0, 0)，单位像素。不是屏幕坐标，也不是窗口坐标。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


# ---------------------------------------------------------------- 异常

class DeviceError(RuntimeError):
    """设备层所有异常的基类，上层可以只捕获这一个。"""

    hint = "设备层操作失败：窗口、截图或点击出了问题"


class WindowNotFound(DeviceError):
    """找不到目标窗口：游戏没开、标题变了、或窗口被关闭。"""

    hint = "游戏没开，或者窗口标题变了——先看看游戏窗口还在不在"


class BlackFrameError(DeviceError):
    """截到的画面无效（全黑或近乎纯色），不能交给识别层。"""

    hint = "窗口可能最小化了，或者被完全遮住——把它还原到屏幕上再试"


class NotElevatedError(DeviceError):
    """该操作需要管理员权限，但当前进程没有。"""

    hint = "后台点击需要管理员权限——用 tools/runner 启动（它会自己提权）"


# ---------------------------------------------------------------- 接口

class Device(ABC):
    """一个可以截图和点击的游戏窗口。"""

    # ---- 子类必须实现 ----

    @abstractmethod
    def client_size(self) -> tuple[int, int]:
        """返回客户区尺寸 (宽, 高)，单位像素。"""

    @abstractmethod
    def _grab(self) -> np.ndarray:
        """真正抓一帧画面，返回 BGR 三通道的 uint8 数组。

        不要直接调用——请用 screenshot()，那里有统一的校验。
        """

    @abstractmethod
    def tap(self, x: int, y: int, hold_ms: int = 0) -> None:
        """在客户区坐标 (x, y) 处点击一次。

        hold_ms 是按下到抬起之间停留的毫秒数。
        真实鼠标点击大约 50~150 毫秒；传 0 表示按下立刻抬起（脚本特征明显）。
        """

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        """从 (x1, y1) 滑到 (x2, y2)，耗时 duration_ms 毫秒。用于滚动列表。"""

    # ---- 基类提供 ----

    @property
    def name(self) -> str:
        """给日志用的设备名称，子类可以覆盖成窗口标题之类。"""
        return type(self).__name__

    def screenshot(self) -> np.ndarray:
        """抓一帧画面并校验有效性；无效时抛 BlackFrameError。"""
        frame = self._grab()
        self._validate(frame)
        return frame

    @staticmethod
    def _validate(
        frame: np.ndarray | None,
        min_std: float = 3.0,
        max_black_ratio: float = 0.98,
    ) -> None:
        """检查画面是否可用。

        min_std          亮度标准差下限。整张图几乎一个颜色时标准差接近 0，
                         全黑、全白、纯灰都会被这里拦住。3.0 是经验值：
                         正常游戏画面通常在 30 以上，纯色背景也不低于 5。
        max_black_ratio  近黑像素占比上限。有些画面标准差不算低，
                         但大部分是黑的（比如只渲染了一小块），也会被拦。
        """
        if frame is None or frame.size == 0:
            raise BlackFrameError("抓到的画面是空的")

        if frame.ndim != 3 or frame.shape[2] != 3:
            raise BlackFrameError(f"画面格式不对，期望 BGR 三通道，实际 shape={frame.shape}")

        std = float(frame.std())
        # 每个像素取三个通道里最大的那个，小于 8 就算「近黑」
        black_ratio = float((frame.max(axis=2) < 8).mean())

        if std < min_std or black_ratio > max_black_ratio:
            raise BlackFrameError(
                f"画面无效：亮度标准差 {std:.1f}（下限 {min_std}），"
                f"近黑像素占比 {black_ratio:.1%}（上限 {max_black_ratio:.0%}）"
            )
