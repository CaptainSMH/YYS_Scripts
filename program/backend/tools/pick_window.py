"""绑定一个游戏窗口到实例配置。

用法（在 program/backend 下）：
    python -m tools.pick_window                    # 没有配置就交互选择；已有就直接用
    python -m tools.pick_window --rebind           # 强制重新选择
    python -m tools.pick_window --instance 名字    # 指定实例名（多开时每个脚本各用一个）
    python -m tools.pick_window --list             # 只看已有配置
    python -m tools.pick_window --remove 名字      # 删除某个实例配置

流程：
    1. 若 --instance 指定的配置已存在且未加 --rebind → 直接使用，不打扰
    2. 否则枚举所有游戏窗口，列出（标出已被其他实例占用的）
    3. 你选一个 → 以窗口标题里的角色名作为实例名 → 写入 configs/instances/<名字>.yaml
"""

from __future__ import annotations

import sys

from core.config import instances, paths
from core.device.base import WindowNotFound
from core.device.desktop import WindowInfo, find_window, list_game_windows
from tools.list_windows import pad, render_table


def show_all() -> None:
    items = instances.list_all()
    if not items:
        print(f"还没有任何实例配置（{paths.rel(paths.INSTANCES_DIR)}）")
        return
    print(f"共 {len(items)} 个实例配置（{paths.rel(paths.INSTANCES_DIR)}）：")
    for item in items:
        size = f"{item.client[0]}x{item.client[1]}" if item.client else "未记录"
        print(
            f"  {pad(item.name, 16)}{size:<10} 第 {item.match_index + 1} 个  "
            f"title_match={item.title_match!r}"
        )


def _occupied_windows() -> dict[int, str]:
    """已被其他实例占用的窗口：hwnd -> 实例名。"""
    occupied: dict[int, str] = {}
    for item in instances.list_all():
        try:
            info = find_window(item.title_match, item.match_index)
        except WindowNotFound:
            continue
        occupied[info.hwnd] = item.name
    return occupied


def _name_for(info: WindowInfo, taken: set[str]) -> str:
    """先用角色名做实例名；重名时追加序号。以后会支持手动命名。"""
    base = info.role
    if base not in taken:
        return base
    index = 2
    while f"{base}_{index}" in taken:
        index += 1
    return f"{base}_{index}"


def choose(name: str) -> int:
    """进入选择流程并写入配置。"""
    windows = list_game_windows()
    if not windows:
        print("没有找到阴阳师窗口（按进程名 onmyoji.exe 判定）")
        return 1

    occupied = _occupied_windows()
    print(f"共 {len(windows)} 个窗口\n")
    for line in render_table(windows):
        print(line)

    others = [info for info in windows if info.hwnd in occupied]
    if others:
        print("\n已被其他实例占用：")
        for info in others:
            print(f"  {pad(info.role, 18)}-> {occupied[info.hwnd]}")

    print()
    answer = input("请输入要绑定的序号（q = 取消）：").strip().lower()
    if answer in ("q", ""):
        print("已取消")
        return 0
    try:
        target = windows[int(answer)]
    except (ValueError, IndexError):
        print(f"无效的序号：{answer!r}")
        return 1

    if target.hwnd in occupied:
        owner = occupied[target.hwnd]
        print(f"注意：该窗口已被实例 {owner!r} 绑定")

    taken = {item.name for item in instances.list_all()}
    # 这个窗口如果已经属于某个实例，就更新那个实例，而不是新建一个带 _2 的副本
    existing_owner = occupied.get(target.hwnd)
    instance_name = name or existing_owner or _name_for(target, taken)

    same_role = [info for info in windows if info.role == target.role]
    match_index = next(i for i, info in enumerate(same_role) if info.hwnd == target.hwnd)

    item = instances.Instance(
        name=instance_name,
        title_match=target.role,
        match_index=match_index,
        client=target.client,
    )
    path = instances.save(item)

    print(f"\n已写入 {paths.rel(path)}")
    print(f"  实例名    {item.name}")
    print(f"  title_match {item.title_match!r} 第 {item.match_index + 1} 个")
    print(f"  客户区    {target.client[0]}x{target.client[1]}")
    x, y = target.position
    print(f"  屏幕位置  ({x}, {y})")

    # 回读验证：写进去的配置能不能真的找回这个窗口
    try:
        found = find_window(item.title_match, item.match_index)
    except WindowNotFound as exc:
        print(f"\n回读验证失败：{exc}")
        return 1
    status = "OK" if found.hwnd == target.hwnd else "绑到了别的窗口！"
    print(f"\n回读验证：{status}  标题={found.title}  位置={found.position}")
    return 0 if found.hwnd == target.hwnd else 1


def main(argv: list[str]) -> int:
    name: str | None = None
    if "--instance" in argv:
        index = argv.index("--instance")
        if index + 1 >= len(argv):
            print("--instance 后面要跟实例名")
            return 1
        name = argv[index + 1]

    if "--list" in argv:
        show_all()
        return 0

    if "--remove" in argv:
        index = argv.index("--remove")
        if index + 1 >= len(argv):
            print("--remove 后面要跟实例名")
            return 1
        target = argv[index + 1]
        print(f"已删除 {target}" if instances.delete(target) else f"没有找到实例 {target!r}")
        return 0

    # 指定了实例名：存在且没要求重选就直接用，不打扰（适合启动脚本调用）
    if name and "--rebind" not in argv:
        existing = instances.load(name)
        if existing is not None:
            try:
                info = find_window(existing.title_match, existing.match_index)
            except WindowNotFound as exc:
                print(f"实例 {name!r} 的配置还在，但窗口找不到了：{exc}")
                print("请用 --rebind 重新选择")
                return 1
            print(f"实例 {name!r} 已绑定：{info.title}  客户区 {info.client[0]}x{info.client[1]}")
            return 0

    # 没指定实例名：给一个可操作的提示，而不是直接退出
    if name is None and "--rebind" not in argv:
        return interactive()

    return choose(name)


def _describe(item: instances.Instance) -> str:
    try:
        info = find_window(item.title_match, item.match_index)
    except WindowNotFound:
        return f"{item.name}（窗口不在了）"
    return f"{item.name}（{info.title}  {info.client[0]}x{info.client[1]}）"


def _ask(prompt: str) -> str:
    """读一行输入；没有输入源（EOF）时返回空串，避免直接崩。"""
    try:
        return input(prompt).strip().lower()
    except EOFError:
        print()
        return ""


def interactive() -> int:
    """不带参数时的入口：先展示现状，再让你选「继续用 / 重新选」。"""
    items = instances.list_all()

    if not items:
        return choose(None)

    if len(items) == 1:
        item = items[0]
        print(f"当前绑定：{_describe(item)}")
        answer = _ask("回车继续用这个 / r 重新选择窗口 / q 退出：")
        if answer == "q":
            print("已退出")
            return 0
        if answer == "r":
            return choose(None)
        return _use(item)

    print(f"已有 {len(items)} 个实例配置：")
    for item in items:
        print(f"  {_describe(item)}")
    answer = _ask("输入实例名使用它 / r 重新选择窗口 / q 退出：")
    if answer == "q":
        print("已退出")
        return 0
    if not answer:
        print("没有输入，已退出（输入 r 可重新选择窗口）")
        return 1
    if answer == "r":
        return choose(None)

    picked = instances.load(answer)
    if picked is None:
        print(f"没有叫 {answer!r} 的实例")
        return 1
    return _use(picked)


def _use(item: instances.Instance) -> int:
    try:
        info = find_window(item.title_match, item.match_index)
    except WindowNotFound as exc:
        print(f"实例 {item.name!r} 的窗口找不到了：{exc}")
        return 1
    print(f"使用实例 {item.name!r}：{info.title}  客户区 {info.client[0]}x{info.client[1]}")
    x, y = info.position
    print(f"屏幕位置 ({x}, {y})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
