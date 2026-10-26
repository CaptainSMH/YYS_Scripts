"""主界面（庭院）。

锚点选择：底部导航栏的「式神录」和「好友」。
    · 两个都在底部栏，画面里非常稳定（实测得分恒为 1.000）
    · 底部栏只在庭院出现，进了任何子界面都会消失，正好用来判断「在不在家」

为什么不用「探索」灯笼做锚点：
    它有呼吸光效、还会被飘过的花瓣遮挡，得分在 0.90~0.99 之间波动。
    锚点应该选最稳的东西，而不是最显眼的。
"""

from __future__ import annotations

from core.page.base import El, Page
from core.page.registry import register


@register
class HomePage(Page):
    """庭院主界面。"""

    key = "home"
    page = "home"
    anchors = ("shikigami_entry", "friends_entry")
    priority = 10

    # 底部导航栏
    SHIKIGAMI = El("shikigami_entry", "式神录")
    FRIENDS = El("friends_entry", "好友")
    SHOP = El("shop_entry", "商店")

    # 画面上方
    EXPLORE = El("explore", "探索灯笼")
