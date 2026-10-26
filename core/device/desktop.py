"""Windows 桌面窗口的设备实现。

截图：GetDC + BitBlt + GetDIBits。
      不用 PrintWindow——该游戏的窗口对 PrintWindow 一律返回 0（实测三种参数均失败），
      而 GetDC 读的是窗口自己的表面，被其他窗口遮挡也能截到完整画面。

点击：PostMessage 投递鼠标消息到窗口，不移动真实光标、不抢焦点。
      该操作受 UIPI 限制，必须以管理员身份运行，否则消息会被拒绝（错误码 5）。
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass

import numpy as np

from core.device.base import Device, DeviceError, NotElevatedError, WindowNotFound

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# 游戏进程名（不含扩展名）
GAME_PROCESS = "onmyoji"

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

ERROR_ACCESS_DENIED = 5


# ---------------------------------------------------------------- 结构体

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


# ---------------------------------------------------------------- 类型声明

user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int


# ---------------------------------------------------------------- 基础查询

def enable_dpi_awareness() -> None:
    """让程序按物理像素工作；否则在 125%/150% 缩放下量到的尺寸会偏小。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 每显示器感知
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def is_elevated() -> bool:
    """当前进程是否以管理员身份运行。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _process_name(pid: int) -> str:
    """返回进程可执行文件名（不含路径），失败时返回空串。"""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _client_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise DeviceError(f"取客户区尺寸失败，窗口句柄 {hwnd}")
    return rect.right - rect.left, rect.bottom - rect.top


def _is_minimized(hwnd: int) -> bool:
    return bool(user32.IsIconic(hwnd))


# ---------------------------------------------------------------- 窗口枚举

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
        """从标题「角色名 · 服务器名」里取出角色名，取不到就返回标题。"""
        return self.title.split(" · ", 1)[0].strip() or self.title

    @property
    def server(self) -> str:
        """从标题里取出服务器名，取不到返回空串。"""
        parts = self.title.split(" · ", 1)
        return parts[1].strip() if len(parts) == 2 else ""


_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def list_game_windows() -> list[WindowInfo]:
    """枚举所有可见的阴阳师窗口，按屏幕位置（先上后下、先左后右）排序。"""
    found: list[WindowInfo] = []

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd)
        if not title.strip():
            return True
        pid = _window_pid(hwnd)
        exe = _process_name(pid)
        if exe.rsplit(".", 1)[0].lower() != GAME_PROCESS:
            return True
        found.append(
            WindowInfo(
                hwnd=hwnd,
                title=title,
                pid=pid,
                exe=exe,
                client=_client_size(hwnd),
                minimized=_is_minimized(hwnd),
            )
        )
        return True

    user32.EnumWindows(_ENUM_PROC(callback), 0)

    # 按位置排序：多开时编号才稳定
    def position(hwnd: int) -> tuple[int, int]:
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect.top, rect.left

    found.sort(key=lambda info: position(info.hwnd))
    return found


def find_window(title_match: str, match_index: int = 0) -> WindowInfo:
    """按标题包含匹配找到第 match_index 个窗口。

    match_index 从 0 开始；多开时标题可能完全相同，用它区分。
    """
    matched = [info for info in list_game_windows() if title_match in info.title]
    if not matched:
        titles = [info.title for info in list_game_windows()]
        raise WindowNotFound(
            f"没有找到标题含「{title_match}」的阴阳师窗口。当前可见窗口：{titles}"
        )
    if match_index >= len(matched):
        raise WindowNotFound(
            f"标题含「{title_match}」的窗口只有 {len(matched)} 个，"
            f"但要求第 {match_index + 1} 个"
        )
    return matched[match_index]


# ---------------------------------------------------------------- 设备实现

class DesktopDevice(Device):
    """通过 Win32 消息操作一个阴阳师窗口。"""

    def __init__(self, title_match: str, match_index: int = 0) -> None:
        enable_dpi_awareness()
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
        return _client_size(self._info.hwnd)

    # ---- 内部辅助 ----

    def _require_window(self) -> int:
        """确认窗口还在；不在了就尝试重新绑定一次。"""
        if user32.IsWindow(self._info.hwnd):
            return self._info.hwnd
        try:
            self._info = find_window(self._title_match, self._match_index)
        except WindowNotFound as exc:
            raise WindowNotFound(f"窗口已失效且无法重新绑定：{exc}") from exc
        return self._info.hwnd

    # ---- 截图 ----

    def _grab(self) -> np.ndarray:
        hwnd = self._require_window()
        if _is_minimized(hwnd):
            raise DeviceError(f"窗口处于最小化状态，无法截图：{self._info.title}")

        width, height = _client_size(hwnd)
        if width <= 0 or height <= 0:
            raise DeviceError(f"客户区尺寸异常：{width}x{height}")

        src_dc = user32.GetDC(hwnd)
        if not src_dc:
            raise DeviceError(f"GetDC 失败，窗口句柄 {hwnd}")

        mem_dc = gdi32.CreateCompatibleDC(src_dc)
        bitmap = gdi32.CreateCompatibleBitmap(src_dc, width, height)
        old_obj = gdi32.SelectObject(mem_dc, bitmap)
        try:
            ok = gdi32.BitBlt(
                mem_dc, 0, 0, width, height, src_dc, 0, 0, SRCCOPY | CAPTUREBLT
            )
            if not ok:
                raise DeviceError(f"BitBlt 失败，错误码 {ctypes.get_last_error()}")

            buffer = np.empty((height, width, 4), dtype=np.uint8)

            info_header = BITMAPINFO()
            info_header.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            info_header.bmiHeader.biWidth = width
            info_header.bmiHeader.biHeight = -height  # 负数 = 自上而下
            info_header.bmiHeader.biPlanes = 1
            info_header.bmiHeader.biBitCount = 32
            info_header.bmiHeader.biCompression = 0  # BI_RGB

            lines = gdi32.GetDIBits(
                mem_dc,
                bitmap,
                0,
                height,
                buffer.ctypes.data_as(ctypes.c_void_p),
                ctypes.byref(info_header),
                DIB_RGB_COLORS,
            )
            if lines == 0:
                raise DeviceError(f"GetDIBits 失败，错误码 {ctypes.get_last_error()}")
        finally:
            gdi32.SelectObject(mem_dc, old_obj)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(hwnd, src_dc)

        # 缓冲区是 BGRA，丢掉 alpha 通道；ascontiguousarray 保证内存连续，cv2 才好用
        return np.ascontiguousarray(buffer[:, :, :3])

    # ---- 输入 ----

    def _post(self, message: int, wparam: int, lparam: int) -> None:
        if not user32.PostMessageW(self._info.hwnd, message, wparam, lparam):
            error = ctypes.get_last_error()
            if error == ERROR_ACCESS_DENIED:
                raise NotElevatedError(
                    "消息被拒绝（错误码 5）：游戏以管理员身份运行，"
                    "脚本也必须以管理员身份运行"
                )
            raise DeviceError(f"PostMessage 失败，消息 0x{message:04X}，错误码 {error}")

    def tap(self, x: int, y: int) -> None:
        if not is_elevated():
            raise NotElevatedError(
                "后台点击需要管理员权限（UIPI 限制），请以管理员身份运行"
            )
        hwnd = self._require_window()
        w, h = _client_size(hwnd)
        if not (0 <= x < w and 0 <= y < h):
            raise DeviceError(f"点击坐标 ({x}, {y}) 超出客户区范围 {w}x{h}")

        lparam = (y << 16) | (x & 0xFFFF)
        self._post(WM_MOUSEMOVE, 0, lparam)
        self._post(WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        self._post(WM_LBUTTONUP, 0, lparam)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        if not is_elevated():
            raise NotElevatedError(
                "滑动需要管理员权限（UIPI 限制），请以管理员身份运行"
            )
        hwnd = self._require_window()
        w, h = _client_size(hwnd)
        for x, y in ((x1, y1), (x2, y2)):
            if not (0 <= x < w and 0 <= y < h):
                raise DeviceError(f"滑动坐标 ({x}, {y}) 超出客户区范围 {w}x{h}")

        steps = max(2, duration_ms // 20)
        delay = duration_ms / 1000 / steps

        self._post(WM_MOUSEMOVE, 0, (y1 << 16) | (x1 & 0xFFFF))
        self._post(WM_LBUTTONDOWN, MK_LBUTTON, (y1 << 16) | (x1 & 0xFFFF))
        for step in range(1, steps + 1):
            x = round(x1 + (x2 - x1) * step / steps)
            y = round(y1 + (y2 - y1) * step / steps)
            self._post(WM_MOUSEMOVE, MK_LBUTTON, (y << 16) | (x & 0xFFFF))
            time.sleep(delay)
        self._post(WM_LBUTTONUP, 0, (y2 << 16) | (x2 & 0xFFFF))
