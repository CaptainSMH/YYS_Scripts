"""截取当前实例的画面并存盘。

用法（在 program/backend 下）：
    python -m tools.capture                     # 用唯一的实例配置
    python -m tools.capture --instance 名字      # 指定实例
    python -m tools.capture --out 相对路径.png    # 指定输出文件
    python -m tools.capture --dir 目录            # 指定输出目录

默认输出：`artifacts/captures/<实例名>/<时间戳>.png`
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path


from core.config import instances, paths
from core.device.base import DeviceError
from core.device.desktop import DesktopDevice
from core.vision.io import save_image


def save_png(path: Path, frame) -> None:
    """保存 PNG 截图。"""
    save_image(path, frame)


def _arg(argv: list[str], flag: str) -> str | None:
    if flag not in argv:
        return None
    index = argv.index(flag)
    if index + 1 >= len(argv):
        raise SystemExit(f"{flag} 后面要跟一个值")
    return argv[index + 1]


def main(argv: list[str]) -> int:
    name = _arg(argv, "--instance")
    out = _arg(argv, "--out")
    directory = _arg(argv, "--dir")

    try:
        item = instances.resolve(name)
    except instances.InstanceNotChosen as exc:
        print(exc)
        return 1

    try:
        device = DesktopDevice(item.title_match, item.match_index)
    except DeviceError as exc:
        print(f"绑定失败：{exc}")
        return 1

    started = time.perf_counter()
    try:
        frame = device.screenshot()
    except DeviceError as exc:
        print(f"截图失败：{exc}")
        return 1
    cost_ms = (time.perf_counter() - started) * 1000

    client = device.client_size()
    if frame.shape[1] != client[0] or frame.shape[0] != client[1]:
        print(f"注意：画面 {frame.shape[1]}x{frame.shape[0]} 与客户区 {client[0]}x{client[1]} 不一致")

    if item.client and tuple(client) != tuple(item.client):
        print(f"注意：客户区 {client[0]}x{client[1]} 与绑定时的 {item.client[0]}x{item.client[1]} 不同")

    if out:
        target = Path(out)
        if not target.is_absolute():
            target = paths.PROJECT_ROOT / target
    else:
        base = Path(directory) if directory else paths.ARTIFACTS_DIR / "captures" / item.name
        if not base.is_absolute():
            base = paths.PROJECT_ROOT / base
        target = base / f"{datetime.now():%Y%m%d-%H%M%S}.png"

    save_png(target, frame)

    print(f"实例    {item.name}")
    print(f"窗口    {device.name}")
    print(f"客户区  {client[0]}x{client[1]}")
    print(f"画面    {frame.shape[1]}x{frame.shape[0]}x{frame.shape[2]}  {frame.dtype}")
    print(f"亮度    均值 {frame.mean():.1f}  标准差 {frame.std():.1f}")
    print(f"耗时    {cost_ms:.1f} ms")
    print(f"已保存  {paths.rel(target)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
