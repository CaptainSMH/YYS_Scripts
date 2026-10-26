"""页面与元素的基类。

一个界面（Page）要回答两个问题：
    1. 怎么认出「现在是这个界面」？   → anchors（锚点，全部命中才算）
    2. 这个界面上有哪些东西可以点？   → 元素（El），供流程层引用

元素引用的名字是「本页面文件夹里的模板名」：
    HomePage.SHOP = El("shop_entry")  →  assets/pages/home/shop_entry.png
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class El:
    """页面上的一个元素：对应 assets/pages/<page>/<name>.png。"""

    name: str
    """模板名，不含页面前缀。"""

    note: str = ""
    """给人看的说明。"""

    def key(self, page: str) -> str:
        """完整模板 key，如 home/shop_entry。"""
        return f"{page}/{self.name}"


class Page:
    """一个界面。

    子类只写类属性，不需要实例化——页面定义是「数据」，不是对象。
    """

    key: str = ""
    """页面标识，用于日志和查找，如 home。"""

    page: str = ""
    """模板所在文件夹名（assets/pages/<page>/），通常与 key 相同。"""

    anchors: tuple[str, ...] = ()
    """判定锚点：这些模板全部命中，才算在这个界面。"""

    priority: int = 0
    """多个页面同时命中时，优先级高的胜出（弹窗应高于主界面）。"""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.key:
            raise TypeError(f"{cls.__name__} 必须定义 key")
        if not cls.page:
            cls.page = cls.key
        if not cls.anchors:
            raise TypeError(f"{cls.__name__} 至少要有一个 anchors")

    @classmethod
    def elements(cls) -> dict[str, El]:
        """本页面所有的元素（类属性里 El 的实例）。"""
        found: dict[str, El] = {}
        for name, value in vars(cls).items():
            if isinstance(value, El):
                found[name] = value
        return found

    @classmethod
    def anchor_keys(cls) -> list[str]:
        """锚点对应的完整模板 key。"""
        return [f"{cls.page}/{anchor}" for anchor in cls.anchors]

    def __repr__(self) -> str:  # pragma: no cover - 只为调试输出
        return f"<Page {self.key}>"
