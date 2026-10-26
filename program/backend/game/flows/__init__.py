"""流程：用会话层的原子动作拼出一个个具体任务。

每个流程就是一个函数：

    def run(ctx: Session) -> None:
        ctx.tap(SomePage.SOMETHING)
        ctx.expect(SomePage, timeout=3)

不返回值，失败就抛异常。异常信息里带得分和当前页面，方便定位是
「按钮没认出来」还是「界面没切过去」。
"""

from __future__ import annotations

from typing import Callable

from core.session.session import Session
from game.flows.enter_guild import run as enter_guild

Flow = Callable[[Session], None]

FLOWS: dict[str, Flow] = {
    "enter_guild": enter_guild,
}

__all__ = ["FLOWS", "Flow", "enter_guild"]
