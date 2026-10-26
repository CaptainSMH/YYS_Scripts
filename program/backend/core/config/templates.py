"""模板清单：一个页面一个文件夹，文件夹里放模板图 + templates.yaml。

目录结构：

    assets/pages/
    └─ home/
       ├─ templates.yaml     本页所有模板的 roi / 阈值
       ├─ explore.png        模板图
       └─ soul_entry.png

模板的完整 key 是「页面/元素」，例如 `home/explore`。

为什么不放一个大清单：
    一个页面的元素放在一起，改版时整个文件夹重做，不牵扯别的页面；
    也不用在一个几百行的文件里翻条目。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.config import paths

MANIFEST_NAME = "templates.yaml"


@dataclass(frozen=True)
class Template:
    """一张模板图及其匹配参数。"""

    page: str
    """所属页面，也是文件夹名。"""

    name: str
    """页面内的元素名。"""

    file: str
    """相对页面文件夹的图片文件名，如 explore.png。"""

    roi: list[float]
    """归一化搜索区域 [x1, y1, x2, y2]。"""

    threshold: float = 0.85
    """模板匹配的得分下限。"""

    since: str = ""
    """最后验证通过的日期。"""

    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.page}/{self.name}"

    @property
    def image_path(self) -> Path:
        return paths.page_dir(self.page) / self.file

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "note": self.note,
            "roi": list(self.roi),
            "since": self.since,
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, page: str, name: str, data: dict) -> Template:
        return cls(
            page=page,
            name=name,
            file=str(data["file"]),
            roi=[float(v) for v in data["roi"]],
            threshold=float(data.get("threshold", 0.85)),
            since=str(data.get("since", "")),
            note=str(data.get("note", "")),
        )


# ---------------------------------------------------------------- 校验

def validate(item: Template) -> None:
    """写入前检查，问题越早暴露越好。"""
    if not item.page or not item.name:
        raise ValueError(f"页面名和元素名都不能为空：{item.key!r}")
    if len(item.roi) != 4:
        raise ValueError(f"{item.key}: roi 必须是 4 个数，实际 {item.roi}")
    if not all(0.0 <= v <= 1.0 for v in item.roi):
        raise ValueError(f"{item.key}: roi 每个值都必须在 0~1，实际 {item.roi}")
    if not 0.0 < item.threshold <= 1.0:
        raise ValueError(f"{item.key}: 阈值必须在 (0, 1]，实际 {item.threshold}")


# ---------------------------------------------------------------- 读写

def manifest_path(page: str) -> Path:
    return paths.page_dir(page) / MANIFEST_NAME


def load_page(page: str) -> list[Template]:
    """读一个页面的全部模板；文件不存在返回空列表。"""
    path = manifest_path(page)
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{paths.rel(path)}: 顶层必须是「元素名 -> 配置」的映射")
    result = []
    for name, data in raw.items():
        item = Template.from_dict(page, str(name), data)
        validate(item)
        result.append(item)
    return sorted(result, key=lambda t: t.name)


def save_image(page: str, name: str, image) -> Path:
    """把模板图写进该页面文件夹，返回文件路径。

    用 cv2.imencode + tofile 而不是 imwrite——后者在 Windows 上不支持中文路径。
    """
    import cv2
    import numpy as np

    target = paths.page_dir(page) / f"{name}.png"
    paths.ensure_dir(target.parent)
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("PNG 编码失败")
    buffer.tofile(str(target))
    return target


def save_page(page: str, items: list[Template]) -> Path:
    """覆盖写一个页面的清单（按元素名排序）。"""
    for item in items:
        validate(item)
    paths.ensure_dir(paths.page_dir(page))
    payload = {item.name: item.to_dict() for item in sorted(items, key=lambda t: t.name)}
    body = yaml.safe_dump(
        payload, allow_unicode=True, sort_keys=True, default_flow_style=None, width=200
    )
    header = f"# 页面 {page} 的模板清单，由 python -m tools.workbench 生成\n"
    path = manifest_path(page)
    path.write_text(header + body, encoding="utf-8")
    return path


def save(item: Template) -> Path:
    """写入单个模板（同页同名会覆盖），返回清单文件路径。"""
    validate(item)
    items = [t for t in load_page(item.page) if t.name != item.name]
    items.append(item)
    return save_page(item.page, items)


def remove(page: str, name: str) -> bool:
    """删除一个模板条目（不删图片）；不存在返回 False。"""
    items = load_page(page)
    kept = [t for t in items if t.name != name]
    if len(kept) == len(items):
        return False
    save_page(page, kept)
    return True


# ---------------------------------------------------------------- 查询

def list_pages() -> list[str]:
    """所有已有清单的页面名。"""
    if not paths.PAGES_DIR.exists():
        return []
    return sorted(
        child.name for child in paths.PAGES_DIR.iterdir() if (child / MANIFEST_NAME).exists()
    )


def list_all() -> list[Template]:
    """跨页面读取全部模板。"""
    result: list[Template] = []
    for page in list_pages():
        result.extend(load_page(page))
    return result


def find(key: str) -> Template | None:
    """按「页面/元素」查找；找不到返回 None。"""
    page, _, name = key.partition("/")
    if not page or not name:
        raise ValueError(f"模板 key 必须是「页面/元素」格式，实际 {key!r}")
    for item in load_page(page):
        if item.name == name:
            return item
    return None
