"""命令行输出的排版工具。

为什么需要它：
    中文在等宽字体里占 2 格，英文占 1 格。直接用 f"{s:<20}" 补空格会错位——
    它补的是字符数，不是显示宽度。

    pad("黑崎一护", 14)   → 补 6 个空格（占 8 格）
    f"{'黑崎一护':<14}"   → 补 10 个空格（占 18 格）

以前这段逻辑在三个地方各抄了一份（list_windows / doctor / 各工具内联），
现在集中在这里。只给 tools 用，不算引擎能力，所以不放 core。
"""

from __future__ import annotations

import unicodedata


def display_width(text: str) -> int:
    """按显示宽度算字符串长度（中文/全角符号占 2 格）。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad(text: str, width: int) -> str:
    """左对齐补空格到指定显示宽度。"""
    return text + " " * max(0, width - display_width(text))
