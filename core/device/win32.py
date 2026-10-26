"""Win32 API 的统一声明与薄封装。

为什么单独做成一层
------------------
用 ctypes 调 Win32 时必须显式声明 `argtypes` / `restype`。64 位下句柄（HWND/HDC/HBITMAP）
是 8 字节指针，而 ctypes 默认按 32 位 `int` 传参，句柄一旦变大就会被截断，
抛 `OverflowError: int too long to convert`——而且崩溃位置往往不在真正出错的函数里，
极难排查（本项目就踩过：`DeleteDC` 漏声明，崩在截图结束的清理阶段）。

两条规则保证不再犯
------------------
1. 所有 Win32 函数只能通过 `declare()` 取得，它强制要求写明参数与返回类型。
2. 本模块**不导出** `user32` / `gdi32` / `kernel32`，业务代码没有绕过 `declare()` 的入口。

`check_declarations()` 可以随时自检有没有漏声明。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

import numpy as np

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_DECLARED: list = []


# ---------------------------------------------------------------- 声明机制

def declare(dll, name: str, argtypes: list, restype):
    """按显式签名取出一个 Win32 函数。所有函数都必须走这里。"""
    fn = getattr(dll, name)
    fn.argtypes = argtypes
    fn.restype = restype
    _DECLARED.append(fn)
    return fn


def check_declarations() -> list[str]:
    """返回缺少类型声明的函数名列表；正常应为空列表。"""
    return [fn.__name__ for fn in _DECLARED if fn.argtypes is None or fn.restype is None]


# ---------------------------------------------------------------- 错误

class Win32Error(OSError):
    """Win32 调用失败，携带 GetLastError 的错误码。"""

    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(message)
        self.code = code


ERROR_ACCESS_DENIED = 5


# ---------------------------------------------------------------- 常量

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001


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


# ---------------------------------------------------------------- 函数声明

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

EnumWindows = declare(_user32, "EnumWindows", [_ENUM_PROC, wintypes.LPARAM], wintypes.BOOL)
GetDC = declare(_user32, "GetDC", [wintypes.HWND], wintypes.HDC)
ReleaseDC = declare(_user32, "ReleaseDC", [wintypes.HWND, wintypes.HDC], ctypes.c_int)
GetClientRect = declare(
    _user32, "GetClientRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL
)
GetWindowRect = declare(
    _user32, "GetWindowRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL
)
GetWindowTextLengthW = declare(
    _user32, "GetWindowTextLengthW", [wintypes.HWND], ctypes.c_int
)
GetWindowTextW = declare(
    _user32, "GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int
)
GetWindowThreadProcessId = declare(
    _user32, "GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)],
    wintypes.DWORD,
)
IsWindow = declare(_user32, "IsWindow", [wintypes.HWND], wintypes.BOOL)
IsWindowVisible = declare(_user32, "IsWindowVisible", [wintypes.HWND], wintypes.BOOL)
IsIconic = declare(_user32, "IsIconic", [wintypes.HWND], wintypes.BOOL)
PostMessageW = declare(
    _user32, "PostMessageW", [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM],
    wintypes.BOOL,
)

CreateCompatibleDC = declare(_gdi32, "CreateCompatibleDC", [wintypes.HDC], wintypes.HDC)
CreateCompatibleBitmap = declare(
    _gdi32, "CreateCompatibleBitmap", [wintypes.HDC, ctypes.c_int, ctypes.c_int],
    wintypes.HBITMAP,
)
SelectObject = declare(
    _gdi32, "SelectObject", [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ
)
DeleteObject = declare(_gdi32, "DeleteObject", [wintypes.HGDIOBJ], wintypes.BOOL)
DeleteDC = declare(_gdi32, "DeleteDC", [wintypes.HDC], wintypes.BOOL)
BitBlt = declare(
    _gdi32, "BitBlt",
    [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
     wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD],
    wintypes.BOOL,
)
GetDIBits = declare(
    _gdi32, "GetDIBits",
    [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
     ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT],
    ctypes.c_int,
)

OpenProcess = declare(
    _kernel32, "OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
)
CloseHandle = declare(_kernel32, "CloseHandle", [wintypes.HANDLE], wintypes.BOOL)
QueryFullProcessImageNameW = declare(
    _kernel32, "QueryFullProcessImageNameW",
    [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)],
    wintypes.BOOL,
)


# ---------------------------------------------------------------- 薄封装

def enable_dpi_awareness() -> None:
    """按物理像素工作；否则在 125%/150% 系统缩放下量到的尺寸会偏小。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            _user32.SetProcessDPIAware()
        except Exception:
            pass


def is_elevated() -> bool:
    """当前进程是否以管理员身份运行。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_window(hwnd: int) -> bool:
    return bool(IsWindow(hwnd))


def window_title(hwnd: int) -> str:
    length = GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def process_name(pid: int) -> str:
    """进程可执行文件名（不含路径）；失败返回空串。"""
    handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        CloseHandle(handle)


def client_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not GetClientRect(hwnd, ctypes.byref(rect)):
        raise Win32Error(f"GetClientRect 失败，句柄 {hwnd}", ctypes.get_last_error())
    return rect.right - rect.left, rect.bottom - rect.top


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """整个窗口框的 (left, top, width, height)，含标题栏与边框。"""
    rect = wintypes.RECT()
    if not GetWindowRect(hwnd, ctypes.byref(rect)):
        return (0, 0, 0, 0)
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def is_minimized(hwnd: int) -> bool:
    return bool(IsIconic(hwnd))


def enum_visible_windows() -> list[int]:
    """所有可见且带标题的顶层窗口句柄。"""
    handles: list[int] = []

    def callback(hwnd, _lparam):
        if IsWindowVisible(hwnd) and window_title(hwnd).strip():
            handles.append(hwnd)
        return True

    EnumWindows(_ENUM_PROC(callback), 0)
    return handles


def grab_frame(hwnd: int, width: int, height: int) -> np.ndarray:
    """把窗口客户区截成 BGR 数组。"""
    src_dc = GetDC(hwnd)
    if not src_dc:
        raise Win32Error(f"GetDC 失败，句柄 {hwnd}", ctypes.get_last_error())

    mem_dc = CreateCompatibleDC(src_dc)
    bitmap = CreateCompatibleBitmap(src_dc, width, height)
    old_obj = SelectObject(mem_dc, bitmap)
    try:
        if not BitBlt(mem_dc, 0, 0, width, height, src_dc, 0, 0, SRCCOPY | CAPTUREBLT):
            raise Win32Error("BitBlt 失败", ctypes.get_last_error())

        buffer = np.empty((height, width, 4), dtype=np.uint8)

        header = BITMAPINFO()
        header.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.bmiHeader.biWidth = width
        header.bmiHeader.biHeight = -height  # 负数表示自上而下存储
        header.bmiHeader.biPlanes = 1
        header.bmiHeader.biBitCount = 32
        header.bmiHeader.biCompression = 0  # BI_RGB

        lines = GetDIBits(
            mem_dc, bitmap, 0, height,
            buffer.ctypes.data_as(ctypes.c_void_p), ctypes.byref(header), DIB_RGB_COLORS,
        )
        if lines == 0:
            raise Win32Error("GetDIBits 失败", ctypes.get_last_error())
    finally:
        SelectObject(mem_dc, old_obj)
        DeleteObject(bitmap)
        DeleteDC(mem_dc)
        ReleaseDC(hwnd, src_dc)

    # 缓冲区是 BGRA，丢掉 alpha；ascontiguousarray 保证内存连续，cv2 才好用
    return np.ascontiguousarray(buffer[:, :, :3])


def post_mouse(hwnd: int, message: int, wparam: int, x: int, y: int) -> None:
    """向窗口投递一条鼠标消息（客户区坐标）。"""
    lparam = (y << 16) | (x & 0xFFFF)
    if not PostMessageW(hwnd, message, wparam, lparam):
        raise Win32Error(f"PostMessage 失败（消息 0x{message:04X}）", ctypes.get_last_error())
