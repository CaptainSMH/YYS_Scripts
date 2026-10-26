"""检查页面定义与模板清单是否对得上。

用法（在 program/backend 下）：
    python -m tools.check_pages

查四件事：
    1. 页面锚点写的模板，清单里有没有
    2. 页面元素（El）写的模板，清单里有没有
    3. 清单里登记了，但图片文件不见了
    4. 清单里有、但没有任何页面引用的模板（提示，不算错误）

为什么要它：
    改模板名、删模板、复制页面忘改名字，都会留下「代码里引用了不存在的模板」。
    这种断链运行到那一步才会炸，而且报错往往离真正的原因很远。
"""

from __future__ import annotations

import sys

import game.pages  # noqa: F401  触发页面注册
from core.config import templates
from core.page.registry import pages
from tools._console import pad


def _check_template(key: str, referenced: set[str], problems: list[str]) -> str:
    """检查一个模板 key，返回给终端看的结论；有问题就记进 problems。"""
    referenced.add(key)
    item = templates.find(key)
    if item is None:
        problems.append(f"{key}: 清单里没有这个模板")
        return "清单缺失"
    if not item.image_path.exists():
        problems.append(f"{key}: 图片文件不存在 {item.file}")
        return "图片缺失"
    return "OK"


def main() -> int:
    page_list = pages()
    if not page_list:
        print("没有注册任何页面")
        return 1

    problems: list[str] = []
    referenced: set[str] = set()

    print(f"页面 {len(page_list)} 个，模板 {len(templates.list_all())} 个")
    print()

    for page_cls in page_list:
        print(f"[{page_cls.key}]   锚点 {len(page_cls.anchors)} 个，元素 {len(page_cls.elements())} 个")

        for anchor in page_cls.anchors:
            key = f"{page_cls.page}/{anchor}"
            status = _check_template(key, referenced, problems)
            print(f"  锚点  {pad(key, 34)}{status}")

        for attr, element in page_cls.elements().items():
            key = element.key(page_cls.page)
            status = _check_template(key, referenced, problems)
            note = f"  {element.note}" if element.note else ""
            print(f"  元素  {pad(key, 34)}{status}{note}")
        print()

    # 清单里有、但没人引用的模板
    orphans = [item.key for item in templates.list_all() if item.key not in referenced]
    if orphans:
        print("未被任何页面引用的模板（不算错误，可能是流程里直接用）：")
        for key in orphans:
            print(f"  {key}")
        print()

    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for line in problems:
            print(f"  - {line}")
        return 1

    print("没有发现问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
