"""Windows 桌面窗口的设备实现。

平台 API 全部经由 core.device.win32 调用（那里统一声明了参数类型）；
本文件只负责「设备语义」：找窗口、绑定、把 Win32 错误翻译成设备层异常。

截图：GetDC + BitBlt + GetDIBits。
      不用 PrintWindow——该游戏的窗口对 PrintWindow 一律返回 0（实测三种参数均失败），
      而 GetDC 读的是窗口自己的表面，被其他窗口遮挡也能截到完整画面。

点击：PostMessage 投递鼠标消息到窗口，不移动真实光标、不抢焦点。
      该操作受 UIPI 限制，必须以管理员身份运行，否则消息会被拒绝（错误码 5）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from core.device import win32
from core.device.base import Device, DeviceError, NotElevatedError, WindowNotFound

# 游戏进程名（不含扩展名）
GAME_PROCESS = "onmyoji"

# 窗口标题的分隔符：「角色名 · 服务器名」
TITLE_SEPARATOR = " · "


# ---------------------------------------------------------------- 窗口信息

@dataclass(frozen=True)
class WindowInfo:
    """一个阴阳师窗口。"""

    hwnd: int
    title: str
    pid: int
    exe: str
    client: tuple[int, int]
    minimized: bool

    @property
    def role(self) -> str:
        """从标题里取出角色名，取不到就返回整条标题。"""
        return self.title.split(TITLE_SEPARATOR, 1)[0].strip() or self.title

    @property
    def server(self) -> str:
        """从标题里取出服务器名，取不到返回空串。"""
        parts = self.title.split(TITLE_SEPARATOR, 1)
        return parts[1].strip() if len(parts) == 2 else ""


def list_game_windows() -> list[WindowInfo]:
    """枚举所有阴阳师窗口，按屏幕位置（先上后下、先左后右）排序。"""
    found: list[WindowInfo] = []
    for hwnd in win32.enum_visible_windows():
        pid = win32.window_pid(hwnd)
        exe = win32.process_name(pid)
        if exe.rsplit(".", 1)[0].lower() != GAME_PROCESS:
            continue
        found.append(
            WindowInfo(
                hwnd=hwnd,
                title=win32.window_title(hwnd),
                pid=pid,
                exe=exe,
                client=win32.client_size(hwnd),
                minimized=win32.is_minimized(hwnd),
            )
        )

    # 多开时标题可能完全相同，按屏幕位置排序让编号稳定
    found.sort(key=lambda info: (win32.window_rect(info.hwnd)[1], win32.window_rect(info.hwnd)[0]))
    return found


def find_window(title_match: str, match_index: int = 0) -> WindowInfo:
    """按标题包含匹配找第 match_index 个窗口（从 0 开始）。"""
    windows = list_game_windows()
    matched = [info for info in windows if title_match in info.title]
    if not matched:
        titles = [info.title for info in windows]
        raise WindowNotFound(
            f"没有找到标题含「{title_match}」的阴阳师窗口。当前可见的窗口：{titles}"
        )
    if match_index >= len(matched):
        raise WindowNotFound(
            f"标题含「{title_match}」的窗口只有 {len(matched)} 个，"
            f"但要第 {match_index + 1} 个"
        )
    return matched[match_index]


# ---------------------------------------------------------------- 设备实现

class DesktopDevice(Device):
    """通过 Win32 消息操作一个阴阳师窗口。"""

    def __init__(self, title_match: str, match_index: int = 0) -> None:
        win32.enable_dpi_awareness()
        self._title_match = title_match
        self._match_index = match_index
        self._info = find_window(title_match, match_index)

    # ---- 基本信息 ----

    @property
    def name(self) -> str:
        return self._info.title

    @property
    def info(self) -> WindowInfo:
        return self._info

    def client_size(self) -> tuple[int, int]:
        self._require_window()
        return win32.client_size(self._info.hwnd)

    # ---- 内部 ----

    def _require_window(self) -> int:
        """确认窗口还在；不在了就尝试重新绑定一次。"""
        if win32.is_window(self._info.hwnd):
            return self._info.hwnd
        try:
            self._info = find_window(self._title_match, self._match_index)
        except WindowNotFound as exc:
            raise WindowNotFound(f"窗口已失效且无法重新绑定：{exc}") from exc
        return self._info.hwnd

    def _require_elevated(self, action: str) -> None:
        if not win32.is_elevated():
            raise NotElevatedError(
                f"{action}需要管理员权限（UIPI 限制），请以管理员身份运行"
            )

    def _post(self, message: int, wparam: int, x: int, y: int) -> None:
        try:
            win32.post_mouse(self._info.hwnd, message, wparam, x, y)
        except win32.Win32Error as exc:
            if exc.code == win32.ERROR_ACCESS_DENIED:
                raise NotElevatedError(
                    "消息被拒绝（错误码 5）：游戏以管理员身份运行，"
                    "脚本也必须以管理员身份运行"
                ) from exc
            raise DeviceError(str(exc)) from exc

    # ---- 截图 ----

    def _grab(self) -> np.ndarray:
        hwnd = self._require_window()
        if win32.is_minimized(hwnd):
            raise DeviceError(f"窗口处于最小化状态，无法截图：{self._info.title}")

        width, height = win32.client_size(hwnd)
        if width <= 0 or height <= 0:
            raise DeviceError(f"客户区尺寸异常：{width}x{height}")

        try:
            return win32.grab_frame(hwnd, width, height)
        except win32.Win32Error as exc:
            raise DeviceError(f"截图失败：{exc}") from exc

    # ---- 输入 ----

    def tap(self, x: int, y: int) -> None:
        self._require_elevated("后台点击")
        hwnd = self._require_window()
        width, height = win32.client_size(hwnd)
        if not (0 <= x < width and 0 <= y < height):
            raise DeviceError(f"点击坐标 ({x}, {y}) 超出客户区范围 {width}x{height}")

        self._post(win32.WM_MOUSEMOVE, 0, x, y)
        self._post(win32.WM_LBUTTONDOWN, win32.MK_LBUTTON, x, y)
        self._post(win32.WM_LBUTTONUP, 0, x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._require_elevated("滑动")
        hwnd = self._require_window()
        width, height = win32.client_size(hwnd)
        for x, y in ((x1, y1), (x2, y2)):
            if not (0 <= x < width and 0 <= y < height):
                raise DeviceError(f"滑动坐标 ({x}, {y}) 超出客户区范围 {width}x{height}")

        steps = max(2, duration_ms // 20)
        delay = duration_ms / 1000 / steps

        self._post(win32.WM_MOUSEMOVE, 0, x1, y1)
        self._post(win32.WM_LBUTTONDOWN, win32.MK_LBUTTON, x1, y1)
        for step in range(1, steps + 1):
            x = round(x1 + (x2 - x1) * step / steps)
            y = round(y1 + (y2 - y1) * step / steps)
            self._post(win32.WM_MOUSEMOVE, win32.MK_LBUTTON, x, y)
            time.sleep(delay)
        self._post(win32.WM_LBUTTONUP, 0, x2, y2)
