"""给一张画面，报告所有模板的命中情况。

用法（在 program/backend 下）：
    python -m tools.whereami --instance 随便玩玩002
    python -m tools.whereami --file artifacts/captures/xxx.png
    python -m tools.whereami --file a.png --page home     # 只看某个页面

和 workbench 的区别：
    workbench 是给人一张一张点着看的；
    这个是一次跑完所有模板，而且支持历史截图——不用开游戏，
    将来做回归测试（「每张历史截图应该命中哪些模板」）就靠它。
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

import game.pages  # noqa: F401  触发页面注册
from core.config import instances, paths, templates
from core.device.base import DeviceError
from core.device.desktop import DesktopDevice
from core.page import registry
from core.vision import match
from tools.list_windows import pad


def _arg(argv: list[str], flag: str) -> str | None:
    if flag not in argv:
        return None
    index = argv.index(flag)
    if index + 1 >= len(argv):
        raise SystemExit(f"{flag} 后面要跟一个值")
    return argv[index + 1]


def load_frame(argv: list[str]) -> tuple[np.ndarray, str]:
    """返回 (画面, 来源描述)。"""
    file = _arg(argv, "--file")
    if file:
        path = Path(file)
        if not path.is_absolute():
            path = paths.PROJECT_ROOT / path
        frame = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise DeviceError(f"读不了这张图：{path}")
        return frame, paths.rel(path)

    name = _arg(argv, "--instance")
    item = instances.resolve(name)
    device = DesktopDevice(item.title_match, item.match_index)
    return device.screenshot(), f"实例 {item.name}"


def main(argv: list[str]) -> int:
    page = _arg(argv, "--page")

    try:
        frame, source = load_frame(argv)
    except (DeviceError, instances.InstanceNotChosen) as exc:
        print(f"取图失败：{exc}")
        return 1

    items = templates.load_page(page) if page else templates.list_all()
    if not items:
        print("还没有任何模板，请先用 tools.workbench 标注")
        return 1

    height, width = frame.shape[:2]
    print(f"画面  {width}x{height}   来源 {source}")
    print()

    # ---- 页面判定 ----
    results = registry.evaluate(frame)
    if results:
        best = registry.detect(frame, results)
        if best is None:
            print("页面判定  未知（没有任何页面的锚点全部命中）")
            for result in results:
                failed = [a for a in result.anchors if not a.ok]
                detail = "，".join(
                    f"{a.anchor} {a.score:.3f} < {a.threshold:.2f}" for a in failed
                )
                print(f"  {result.page.key:<10} 未通过：{detail}")
        else:
            print(f"页面判定  {best.key}（优先级 {best.priority}）")
            for anchor in best.result.anchors:
                print(
                    f"  锚点 {pad(anchor.anchor, 18)}"
                    f"{anchor.score:.3f} ≥ {anchor.threshold:.2f}  OK"
                )
        print()

    hits = 0
    missing = 0
    for item in items:
        path = item.image_path
        if not path.exists():
            print(f"  {pad(item.key, 26)}模板图缺失  {paths.rel(path)}")
            missing += 1
            continue

        image = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            print(f"  {pad(item.key, 26)}模板图读不了  {paths.rel(path)}")
            missing += 1
            continue

        score, location = match.best_match(frame, image, item.roi)
        ok = score >= item.threshold
        hits += int(ok)
        mark = "OK  " if ok else "MISS"
        where = f"({location[0]}, {location[1]})" if location else "—"
        th, tw = image.shape[:2]
        print(
            f"  {mark} {pad(item.key, 24)}"
            f"得分 {score:.3f} / 阈值 {item.threshold:.2f}   "
            f"{where:<16} 模板 {tw}x{th}"
        )

    print()
    total = len(items)
    print(f"合计  {hits}/{total} 命中" + (f"   {missing} 个模板图缺失" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
