"""实例配置：一个游戏窗口 = 一条记录。

配置文件位置：`configs/instances.yaml`
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
    """实例名：用于日志目录、命令行参数，必须唯一。"""

    title_match: str
    """窗口标题需要包含的字符串。"""

    match_index: int = 0
    """标题匹配到多个窗口时取第几个（从 0 开始）。"""

    client: tuple[int, int] | None = None
    """绑定时的客户区尺寸，用于发现绑错窗口。"""

    def to_dict(self) -> dict:
        data = {
            "name": self.name,
            "title_match": self.title_match,
            "match_index": self.match_index,
        }
        if self.client:
            data["client"] = list(self.client)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Instance:
        client = data.get("client")
        return cls(
            name=str(data["name"]),
            title_match=str(data["title_match"]),
            match_index=int(data.get("match_index", 0)),
            client=tuple(client) if client else None,
        )


def load() -> list[Instance]:
    """读取全部实例；文件不存在时返回空列表。"""
    path = paths.INSTANCES_YAML
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = raw.get("instances") or []
    return [Instance.from_dict(item) for item in items]


def save(items: list[Instance]) -> Path:
    """写入配置文件（目录不存在时自动创建），返回文件路径。"""
    paths.ensure_dir(paths.CONFIGS_DIR)
    payload = {"instances": [item.to_dict() for item in items]}
    body = yaml.safe_dump(
        payload,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=None,  # 纯标量列表写成 [800, 450]，字典仍为块状
        width=200,
    )
    header = "# 实例绑定：一个游戏窗口一条记录\n# 由 python -m tools.pick_window 生成或更新\n"
    paths.INSTANCES_YAML.write_text(header + body, encoding="utf-8")
    return paths.INSTANCES_YAML


def find(name: str) -> Instance | None:
    """按实例名查找。"""
    for item in load():
        if item.name == name:
            return item
    return None


def upsert(new_items: list[Instance]) -> list[Instance]:
    """按 name 合并：同名替换，新名字追加，返回合并后的完整列表。"""
    merged = {item.name: item for item in load()}
    for item in new_items:
        merged[item.name] = item
    return list(merged.values())
