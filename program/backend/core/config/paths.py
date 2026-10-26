"""项目路径的唯一来源。

所有模块都从这里取路径，不要在别处硬编码或自己拼相对路径。

项目根是通过「从本文件向上查找 `.project-root` 标记文件」得到的，
所以无论从哪个目录运行、项目被挪到哪里，结果都一致。

为什么不用 `.git` 或 `requirements.txt` 当标记：
    `.git` 在仓库根（program/backend/app 的上面好几层），
    `requirements.txt` 在 program/backend（也在 app 之上），
    两者都会把代码根认成错误的目录。所以用 app 自己的标记文件。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

# 用来判定项目根的标记文件：只认 app 目录里的这个文件
_ROOT_MARKER = ".project-root"


def _find_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / _ROOT_MARKER).exists():
            return parent
    raise RuntimeError(
        f"找不到项目根目录：从 {start} 向上未发现 {_ROOT_MARKER} 标记文件，"
        "请确认 program/backend/app/.project-root 是否存在"
    )


# ---------------------------------------------------------------- 根目录

PROJECT_ROOT: Path = _find_root(Path(__file__).resolve().parent)

CORE_DIR: Path = PROJECT_ROOT / "core"
TOOLS_DIR: Path = PROJECT_ROOT / "tools"

# ---------------------------------------------------------------- 资源

ASSETS_DIR: Path = PROJECT_ROOT / "assets"
TEMPLATES_DIR: Path = ASSETS_DIR / "templates"
TEMPLATES_YAML: Path = ASSETS_DIR / "templates.yaml"

# ---------------------------------------------------------------- 配置

CONFIGS_DIR: Path = PROJECT_ROOT / "configs"
DEVICE_YAML: Path = CONFIGS_DIR / "device.yaml"
INSTANCES_DIR: Path = CONFIGS_DIR / "instances"
"""每个实例一个 yaml，文件名即实例名。"""
TASKS_YAML: Path = CONFIGS_DIR / "tasks.yaml"

# ---------------------------------------------------------------- 运行产物与测试

ARTIFACTS_DIR: Path = PROJECT_ROOT / "artifacts"
TESTS_DIR: Path = PROJECT_ROOT / "tests"
SCREENS_DIR: Path = TESTS_DIR / "screens"

REQUIREMENTS_FILE: Path = PROJECT_ROOT / "requirements.txt"


# ---------------------------------------------------------------- 工具函数

def ensure_dir(path: Path) -> Path:
    """确保目录存在，返回它本身，方便链式使用。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir(instance: str | None = None, *, today: date | None = None) -> Path:
    """本次运行的产物目录：artifacts/<日期>/<实例名>/（不会自动创建）。"""
    day = (today or date.today()).isoformat()
    path = ARTIFACTS_DIR / day
    if instance:
        path = path / instance
    return path


def rel(path: Path | str) -> str:
    """转成相对项目根的路径字符串，用于日志显示；不在项目内则原样返回。"""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)
