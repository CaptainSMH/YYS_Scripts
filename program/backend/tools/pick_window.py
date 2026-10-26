"""交互式绑定窗口：把选中的窗口写进 configs/instances.yaml。

用法（在 program/backend 下）：
    python -m tools.pick_window
    python -m tools.pick_window all      # 直接绑定全部窗口，不进入交互
    python -m tools.pick_window --list   # 只看当前配置
"""

from __future__ import annotations

import sys

from core.config import instances, paths
from core.device.desktop import WindowInfo, list_game_windows
from tools.list_windows import pad, render_table


def _unique_name(base: str, taken: set[str]) -> str:
    """角色名可能重复；重名时追加序号。"""
    if base not in taken:
        return base
    index = 2
    while f"{base}_{index}" in taken:
        index += 1
    return f"{base}_{index}"


def _match_index_of(windows: list[WindowInfo], target: WindowInfo) -> int:
    """同一个 title_match 命中多个窗口时，算出当前窗口排第几。"""
    same = [info for info in windows if target.role in info.title]
    for index, info in enumerate(same):
        if info.hwnd == target.hwnd:
            return index
    return 0


def build_instances(windows: list[WindowInfo], chosen: list[WindowInfo]) -> list[instances.Instance]:
    taken: set[str] = set()
    result = []
    for info in chosen:
        name = _unique_name(info.role, taken)
        taken.add(name)
        result.append(
            instances.Instance(
                name=name,
                title_match=info.role,
                match_index=_match_index_of(windows, info),
                client=info.client,
            )
        )
    return result


def show_current() -> None:
    items = instances.load()
    if not items:
        print(f"当前没有绑定的实例（配置文件：{paths.rel(paths.INSTANCES_YAML)}）")
        return
    print(f"当前已绑定 {len(items)} 个实例（{paths.rel(paths.INSTANCES_YAML)}）：")
    for item in items:
        size = f"{item.client[0]}x{item.client[1]}" if item.client else "未记录"
        print(
            f"  {pad(item.name, 16)}第 {item.match_index + 1} 个  {size:<10}  "
            f"title_match={item.title_match!r}"
        )


def main(argv: list[str]) -> int:
    if "--list" in argv:
        show_current()
        return 0

    windows = list_game_windows()
    if not windows:
        print("没有找到阴阳师窗口（按进程名 onmyoji.exe 判定）")
        return 1

    print(f"共 {len(windows)} 个窗口\n")
    for line in render_table(windows):
        print(line)
    print()

    if "all" in argv:
        chosen = windows
    else:
        answer = input("请输入要绑定的序号（all = 全部，q = 取消）：").strip().lower()
        if answer in ("q", ""):
            print("已取消")
            return 0
        if answer == "all":
            chosen = windows
        else:
            try:
                chosen = [windows[int(answer)]]
            except (ValueError, IndexError):
                print(f"无效的序号：{answer!r}")
                return 1

    new_items = build_instances(windows, chosen)
    merged = instances.upsert(new_items)
    path = instances.save(merged)

    print(f"已写入 {paths.rel(path)}（共 {len(merged)} 个实例）")
    for item in new_items:
        print(f"  + {item.name}  <- {item.title_match!r} 第 {item.match_index + 1} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
