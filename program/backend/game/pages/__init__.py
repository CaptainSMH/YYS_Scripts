"""页面定义集合。

这里 import 各个页面模块，注册就自动完成（每个页面用 @register 装饰）。
新增页面时在下面加一行 import 即可。
"""

from __future__ import annotations

from game.pages.home import HomePage  # noqa: F401  注册用

__all__ = ["HomePage"]
