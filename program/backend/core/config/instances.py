"""实例配置：一个实例一个文件，放在 `configs/instances/` 下。

文件名就是实例名（不含扩展名），所以不需要在文件里再写 name 字段，
也不存在重名问题——重名就是同一个文件。

为什么不是「一份注册表」：
    每个脚本进程只管自己那个窗口，读自己的文件即可。
    共用一份文件会引入共享状态：一个进程写、其他进程都在读，
    和「进程之间互不影响」的设计原则冲突。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.config import paths


@dataclass(frozen=True)
class Instance:
    """一个窗口的绑定信息。"""

    name: str
    """实例名，同时是配置文件名（不含 .yaml）。"""

    title_match: str
    """窗口标题需要包含的字符串。"""

    match_index: int = 0
    """标题匹配到多个窗口时取第几个（从 0 开始）。"""

    client: tuple[int, int] | None = None
    """绑定时的客户区尺寸，用于发现绑错窗口。"""

    @property
    def path(self) -> Path:
        return paths.INSTANCES_DIR / f"{self.name}.yaml"

    def to_dict(self) -> dict:
        data: dict = {"title_match": self.title_match, "match_index": self.match_index}
        if self.client:
            data["client"] = list(self.client)
        return data

    @classmethod
    def from_dict(cls, name: str, data: dict) -> Instance:
        client = data.get("client")
        return cls(
            name=name,
            title_match=str(data["title_match"]),
            match_index=int(data.get("match_index", 0)),
            client=tuple(client) if client else None,
        )


def instance_path(name: str) -> Path:
    return paths.INSTANCES_DIR / f"{name}.yaml"


def load(name: str) -> Instance | None:
    """按实例名读取；不存在返回 None。"""
    path = instance_path(name)
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or "title_match" not in data:
        raise ValueError(f"实例配置格式不对：{paths.rel(path)}")
    return Instance.from_dict(name, data)


def save(instance: Instance) -> Path:
    """写入该实例的文件（目录不存在时自动创建），返回文件路径。"""
    paths.ensure_dir(paths.INSTANCES_DIR)
    body = yaml.safe_dump(
        instance.to_dict(),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=None,
        width=200,
    )
    header = f"# 实例：{instance.name}\n# 由 python -m tools.pick_window 生成\n"
    path = instance_path(instance.name)
    path.write_text(header + body, encoding="utf-8")
    return path


def delete(name: str) -> bool:
    """删除该实例的配置文件；不存在返回 False。"""
    path = instance_path(name)
    if not path.exists():
        return False
    path.unlink()
    return True


def list_all() -> list[Instance]:
    """读取全部实例配置，按文件名排序。"""
    if not paths.INSTANCES_DIR.exists():
        return []
    result = []
    for path in sorted(paths.INSTANCES_DIR.glob("*.yaml")):
        try:
            item = load(path.stem)
        except ValueError:
            continue
        if item is not None:
            result.append(item)
    return result
