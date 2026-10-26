"""从主界面进入阴阳寮。

这是最小的一条完整链路：找到按钮 → 点击 → 等界面出现。
用来验证设备、识别、页面、会话四层能不能串起来。

前置条件：必须停在主界面。流程开头用 ctx.require(HomePage) 声明这一点——
不在主界面就直接失败，并说明当前在哪个界面，而不是去点主界面的按钮。
"""

from __future__ import annotations

from core.session.session import Session
from game.pages.guild import GuildPage
from game.pages.home import HomePage


def run(ctx: Session) -> None:
    """点主界面的「阴阳寮」，然后等阴阳寮界面出现。"""
    ctx.require(HomePage)

    print("  点「阴阳寮」…")
    x, y = ctx.tap(HomePage.GUILD)
    print(f"  点击坐标 ({x}, {y})")

    matched = ctx.expect(GuildPage, timeout=3)
    anchors = ", ".join(f"{a.anchor}={a.score:.3f}" for a in matched.result.anchors)
    print(f"  已进入 {matched.key}，锚点 {anchors}")
