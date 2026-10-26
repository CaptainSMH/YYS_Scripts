"""阴阳寮界面。

锚点用右侧的「结界」和「寮信息」两个页签：
    · 它们只在阴阳寮界面出现，进不了别的界面
    · 位置分开，不容易被同一次遮挡同时盖住

优先级 20（高于主界面的 10）：
    如果哪天出现「弹窗盖在阴阳寮上」或者「两个界面同时像」，阴阳寮优先。
"""

from __future__ import annotations

from core.page.base import El, Page
from core.page.registry import register


@register
class GuildPage(Page):
    """阴阳寮。"""

    key = "guild"
    page = "guild"
    anchors = ("barrier", "info")
    priority = 20

    BARRIER = El("barrier", "结界")
    INFO = El("info", "寮信息")
    BACK = El("back", "返回")
