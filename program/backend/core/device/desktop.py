"""Windows 桌面窗口的设备实现（pywin32 + psutil）。

为什么用 pywin32 而不是裸 ctypes
--------------------------------
裸 ctypes 调 Win32 要为每个函数手写 `argtypes` / `restype`。64 位下句柄（HWND/HDC/HBITMAP）
是 8 字节指针，漏声明就会被当成 32 位整数截断，抛 `OverflowError`；更糟的是崩的位置
往往不在真正出错的函数里（本项目踩过：`DeleteDC` 漏声明，崩在截图收尾的清理阶段，
现象和原因隔了十几行）。

pywin32 的签名写在 C 扩展里，不存在「忘记声明」这个环节。

进程名为什么用 psutil
--------------------
pywin32 没有封装 `QueryFullProcessImageName`，而 `GetModuleFileNameEx` 需要
`PROCESS_VM_READ` 权限——非管理员读不了管理员进程，而这个游戏正是以管理员运行的。
psutil 走 LIMITED 信息权限，跨权限可读。

截图与点击
----------
截图：`GetDC + BitBlt`。不用 `PrintWindow`——该游戏窗口对 `PrintWindow` 一律返回 0
      （实测三种参数均失败），而 `GetDC` 读的是窗口自己的表面，被遮挡也能截全。
点击：`PostMessage` 投递鼠标消息，不移动光标、不抢焦点；受 UIPI 限制，需管理员权限。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np
import psutil
import pywintypes
import win32api
import win32con
import win32gui
import win32process
import win32security
import win32ui

from core.device.base import Device, DeviceError, NotElevatedError, WindowNotFound

# 游戏进程名（不含扩展名）
GAME_PROCESS = "onmyoji"

# 窗口标题的分隔符：「角色名 · 服务器名」
TITLE_SEPARATOR = " · "

ERROR_ACCESS_DENIED = 5

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

# 客户区应有的宽高比，以及允许的偏差
TARGET_ASPECT = 16 / 9
ASPECT_TOLERANCE = 0.0  # 0 = 只要不是精确 16:9 就调整
# 浮点保护：800/450 与 16/9 可能差最后一个二进制位，不能因此误判并反复调整
_ASPECT_EPSILON = 1e-6

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- 环境

def is_elevated() -> bool:
    """当前进程是否以管理员身份运行。"""
    try:
        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
        )
        try:
            return bool(win32security.GetTokenInformation(token, win32security.TokenElevation))
        finally:
            win32api.CloseHandle(token)
    except Exception:
        return False


def process_name(pid: int) -> str:
    """进程可执行文件名（含扩展名）；取不到返回空串。"""
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""


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
    position: tuple[int, int] = (0, 0)
    """窗口左上角在屏幕上的坐标，用于把序号和屏幕上的位置对上。"""

    @property
    def role(self) -> str:
        """从标题里取出角色名，取不到就返回整条标题。"""
        return self.title.split(TITLE_SEPARATOR, 1)[0].strip() or self.title

    @property
    def server(self) -> str:
        """从标题里取出服务器名，取不到返回空串。"""
        parts = self.title.split(TITLE_SEPARATOR, 1)
        return parts[1].strip() if len(parts) == 2 else ""


def _client_size(hwnd: int) -> tuple[int, int]:
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    return right - left, bottom - top


def _frame_overhead(hwnd: int) -> tuple[int, int]:
    """窗口框比客户区多出来的宽和高（边框 + 标题栏）。"""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    client_width, client_height = _client_size(hwnd)
    return (right - left) - client_width, (bottom - top) - client_height


def resize_client(hwnd: int, width: int, height: int) -> None:
    """把客户区调整到指定尺寸；窗口位置不动。

    注意：目标窗口若以管理员身份运行，本进程也必须提权，否则 SetWindowPos
    会被 UIPI 拒绝（错误码 5）——和后台点击是同一类限制。
    """
    overhead_width, overhead_height = _frame_overhead(hwnd)
    try:
        win32gui.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            width + overhead_width,
            height + overhead_height,
            win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )
    except pywintypes.error as exc:
        if getattr(exc, "winerror", None) == ERROR_ACCESS_DENIED:
            raise DeviceError(
                "调整窗口尺寸被拒绝（错误码 5）：游戏以管理员身份运行，"
                "调整窗口也必须以管理员身份运行"
            ) from exc
        raise DeviceError(f"调整窗口尺寸失败：{exc}") from exc


def _all_visible_windows() -> list[tuple[int, str]]:
    """所有可见、带标题的顶层窗口。"""
    rows: list[tuple[int, str]] = []

    def callback(hwnd, _extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip():
                rows.append((hwnd, title))
        return True

    win32gui.EnumWindows(callback, None)
    return rows


def list_game_windows() -> list[WindowInfo]:
    """枚举所有阴阳师窗口，按屏幕位置（先上后下、先左后右）排序。"""
    found: list[WindowInfo] = []
    for hwnd, title in _all_visible_windows():
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = process_name(pid)
        if exe.rsplit(".", 1)[0].lower() != GAME_PROCESS:
            continue
        left, top, _right, _bottom = win32gui.GetWindowRect(hwnd)
        found.append(
            WindowInfo(
                hwnd=hwnd,
                title=title,
                pid=pid,
                exe=exe,
                client=_client_size(hwnd),
                minimized=bool(win32gui.IsIconic(hwnd)),
                position=(left, top),
            )
        )

    # 多开时标题可能完全相同，按屏幕位置排序让编号稳定（先上后下、先左后右）
    found.sort(key=lambda info: (info.position[1], info.position[0]))
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


# ---------------------------------------------------------------- 截图

def grab_frame(hwnd: int, width: int, height: int) -> np.ndarray:
    """把窗口客户区截成 BGR 数组。"""
    hdc = win32gui.GetDC(hwnd)
    if not hdc:
        raise DeviceError(f"GetDC 失败，窗口句柄 {hwnd}")
    source = win32ui.CreateDCFromHandle(hdc)
    try:
        memory = source.CreateCompatibleDC()
        try:
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(source, width, height)
            try:
                memory.SelectObject(bitmap)
                memory.BitBlt((0, 0), (width, height), source, (0, 0), win32con.SRCCOPY)
                bits = bitmap.GetBitmapBits(True)
            finally:
                win32gui.DeleteObject(bitmap.GetHandle())
        finally:
            memory.DeleteDC()
    finally:
        win32gui.ReleaseDC(hwnd, hdc)

    # bits 是 BGRA；丢掉 alpha，并拷贝成可写、内存连续的数组供 cv2 使用
    buffer = np.frombuffer(bits, dtype=np.uint8).reshape(height, width, 4)
    return np.ascontiguousarray(buffer[:, :, :3])


# ---------------------------------------------------------------- 设备实现

class DesktopDevice(Device):
    """通过 Win32 消息操作一个阴阳师窗口。"""

    def __init__(
        self,
        title_match: str,
        match_index: int = 0,
        *,
        fix_aspect: bool = True,
    ) -> None:
        self._title_match = title_match
        self._match_index = match_index
        self._fix_aspect = fix_aspect
        self._info = find_window(title_match, match_index)
        self._ensure_aspect()

    # ---- 比例校正 ----

    def _ensure_aspect(self) -> None:
        """客户区不是 16:9 时按需调整窗口。

        容差由 ASPECT_TOLERANCE 控制；设为 0 时，只要比例不是精确 16:9 就会调整。
        浮点比较留了 1e-6 的保护，避免 800x450 这种"本该相等"的尺寸被反复调整。
        """
        tolerance = max(ASPECT_TOLERANCE, _ASPECT_EPSILON)

        width, height = _client_size(self._info.hwnd)
        if height <= 0:
            raise DeviceError(f"客户区尺寸异常：{width}x{height}")

        ratio = width / height
        deviation = abs(ratio - TARGET_ASPECT) / TARGET_ASPECT
        if deviation <= tolerance:
            return

        message = (
            f"客户区 {width}x{height} 的宽高比 {ratio:.4f} 偏离 16:9 {deviation:.2%}"
        )
        if not self._fix_aspect:
            raise DeviceError(message)

        target_width = round(height * TARGET_ASPECT)
        logger.warning("%s，正在调整为 %dx%d", message, target_width, height)
        resize_client(self._info.hwnd, target_width, height)

        new_width, new_height = _client_size(self._info.hwnd)
        new_ratio = new_width / new_height if new_height else 0
        if abs(new_ratio - TARGET_ASPECT) / TARGET_ASPECT > tolerance:
            raise DeviceError(
                f"调整窗口比例失败：目标 {target_width}x{height}，"
                f"实际 {new_width}x{new_height}"
            )
        logger.warning("窗口已调整为 %dx%d", new_width, new_height)

    # ---- 基本信息 ----

    @property
    def name(self) -> str:
        return self._info.title

    @property
    def info(self) -> WindowInfo:
        return self._info

    def client_size(self) -> tuple[int, int]:
        self._require_window()
        return _client_size(self._info.hwnd)

    # ---- 内部 ----

    def _require_window(self) -> int:
        """确认窗口还在；不在了就尝试重新绑定一次。"""
        if win32gui.IsWindow(self._info.hwnd):
            return self._info.hwnd
        try:
            self._info = find_window(self._title_match, self._match_index)
        except WindowNotFound as exc:
            raise WindowNotFound(f"窗口已失效且无法重新绑定：{exc}") from exc
        return self._info.hwnd

    def _require_elevated(self, action: str) -> None:
        if not is_elevated():
            raise NotElevatedError(
                f"{action}需要管理员权限（UIPI 限制），请以管理员身份运行"
            )

    def _post(self, message: int, wparam: int, x: int, y: int) -> None:
        lparam = (y << 16) | (x & 0xFFFF)
        try:
            win32gui.PostMessage(self._info.hwnd, message, wparam, lparam)
        except pywintypes.error as exc:
            if getattr(exc, "winerror", None) == ERROR_ACCESS_DENIED:
                raise NotElevatedError(
                    "消息被拒绝（错误码 5）：游戏以管理员身份运行，"
                    "脚本也必须以管理员身份运行"
                ) from exc
            raise DeviceError(f"PostMessage 失败：{exc}") from exc

    # ---- 截图 ----

    def _grab(self) -> np.ndarray:
        hwnd = self._require_window()
        if win32gui.IsIconic(hwnd):
            raise DeviceError(f"窗口处于最小化状态，无法截图：{self._info.title}")

        width, height = _client_size(hwnd)
        if width <= 0 or height <= 0:
            raise DeviceError(f"客户区尺寸异常：{width}x{height}")

        try:
            return grab_frame(hwnd, width, height)
        except pywintypes.error as exc:
            raise DeviceError(f"截图失败：{exc}") from exc

    # ---- 输入 ----

    def tap(self, x: int, y: int) -> None:
        self._require_elevated("后台点击")
        hwnd = self._require_window()
        width, height = _client_size(hwnd)
        if not (0 <= x < width and 0 <= y < height):
            raise DeviceError(f"点击坐标 ({x}, {y}) 超出客户区范围 {width}x{height}")

        self._post(WM_MOUSEMOVE, 0, x, y)
        self._post(WM_LBUTTONDOWN, MK_LBUTTON, x, y)
        self._post(WM_LBUTTONUP, 0, x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._require_elevated("滑动")
        hwnd = self._require_window()
        width, height = _client_size(hwnd)
        for x, y in ((x1, y1), (x2, y2)):
            if not (0 <= x < width and 0 <= y < height):
                raise DeviceError(f"滑动坐标 ({x}, {y}) 超出客户区范围 {width}x{height}")

        steps = max(2, duration_ms // 20)
        delay = duration_ms / 1000 / steps

        self._post(WM_MOUSEMOVE, 0, x1, y1)
        self._post(WM_LBUTTONDOWN, MK_LBUTTON, x1, y1)
        for step in range(1, steps + 1):
            x = round(x1 + (x2 - x1) * step / steps)
            y = round(y1 + (y2 - y1) * step / steps)
            self._post(WM_MOUSEMOVE, MK_LBUTTON, x, y)
            time.sleep(delay)
        self._post(WM_LBUTTONUP, 0, x2, y2)
