"""页面注册表与路由。

判定算法：
    对每个已注册页面，逐个检查它的锚点：
        锚点模板得分 ≥ 阈值 → 这个锚点通过
    全部锚点通过 → 这个页面成立
    在成立的页面里取 priority 最高的一个
    一个都不成立 → 未知页面（返回 None）

为什么用 priority：
    弹窗盖在主界面上时，两边的锚点可能同时命中。
    弹窗优先级高，就会被判定为弹窗，而不是主界面。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.config import templates
from core.page.base import Page
from core.vision import match
from core.vision.io import load_image

_REGISTRY: dict[str, type[Page]] = {}


# ---------------------------------------------------------------- 注册

def register(page_cls: type[Page]) -> type[Page]:
    """注册一个页面。重复注册同一个 key 会报错（避免两个定义悄悄覆盖）。"""
    if page_cls.key in _REGISTRY and _REGISTRY[page_cls.key] is not page_cls:
        raise ValueError(f"页面 key 重复：{page_cls.key}")
    _REGISTRY[page_cls.key] = page_cls
    return page_cls


def pages() -> list[type[Page]]:
    """所有已注册页面，按 priority 从高到低。"""
    return sorted(_REGISTRY.values(), key=lambda p: p.priority, reverse=True)


def get(key: str) -> type[Page] | None:
    return _REGISTRY.get(key)


def clear() -> None:
    """清空注册表（测试用）。"""
    _REGISTRY.clear()


# ---------------------------------------------------------------- 结果

@dataclass
class AnchorResult:
    anchor: str
    score: float
    threshold: float
    location: tuple[int, int] | None
    ok: bool


@dataclass
class PageResult:
    page: type[Page]
    anchors: list[AnchorResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.anchors) and all(a.ok for a in self.anchors)

    @property
    def min_score(self) -> float:
        return min((a.score for a in self.anchors), default=0.0)


@dataclass
class PageMatch:
    page: type[Page]
    result: PageResult

    @property
    def key(self) -> str:
        return self.page.key

    @property
    def priority(self) -> int:
        return self.page.priority


# ---------------------------------------------------------------- 判定

def evaluate(frame: np.ndarray) -> list[PageResult]:
    """逐页检查锚点，返回每个页面的判定细节（不管成不成立）。"""
    results: list[PageResult] = []
    for page_cls in pages():
        result = PageResult(page=page_cls)
        for anchor, key in zip(page_cls.anchors, page_cls.anchor_keys()):
            item = templates.find(key)
            if item is None:
                # 模板缺失：记 0 分、位置 None，锚点判为不通过
                result.anchors.append(
                    AnchorResult(anchor=anchor, score=0.0, threshold=1.0, location=None, ok=False)
                )
                continue

            image = load_image(item.image_path)
            if image is None:
                result.anchors.append(
                    AnchorResult(
                        anchor=anchor, score=0.0, threshold=item.threshold, location=None, ok=False
                    )
                )
                continue

            score, location = match.best_match(frame, image, item.roi)
            result.anchors.append(
                AnchorResult(
                    anchor=anchor,
                    score=score,
                    threshold=item.threshold,
                    location=location,
                    ok=score >= item.threshold,
                )
            )
        results.append(result)
    return results


def detect(frame: np.ndarray, results: list[PageResult] | None = None) -> PageMatch | None:
    """返回当前页面；认不出来时返回 None。

    已经调用过 evaluate() 的话把结果传进来，避免重复做一遍匹配。
    """
    results = results if results is not None else evaluate(frame)
    candidates = [r for r in results if r.ok]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: (r.page.priority, r.min_score))
    return PageMatch(page=best.page, result=best)
