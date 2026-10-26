"""列出所有阴阳师窗口。

用法（在 program/backend 下）：
    python -m tools.list_windows
"""

from __future__ import annotations

import sys

from core.device.desktop import WindowInfo, list_game_windows
from tools._console import pad


def render_table(windows: list[WindowInfo]) -> list[str]:
    """把窗口列表渲染成对齐的文本行。"""
    lines = [
        pad("序号", 6)
        + pad("角色", 18)
        + pad("服务器", 16)
        + pad("客户区", 12)
        + pad("屏幕位置", 16)
        + "状态"
    ]
    lines.append("-" * 84)
    for index, info in enumerate(windows):
        state = "已最小化" if info.minimized else "正常"
        x, y = info.position
        lines.append(
            pad(str(index), 6)
            + pad(info.role, 18)
            + pad(info.server, 16)
            + pad(f"{info.client[0]}x{info.client[1]}", 12)
            + pad(f"({x}, {y})", 16)
            + state
        )
    return lines


def main() -> int:
    windows = list_game_windows()
    if not windows:
        print("没有找到阴阳师窗口（按进程名 onmyoji.exe 判定）")
        return 1

    print(f"共 {len(windows)} 个窗口\n")
    for line in render_table(windows):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
