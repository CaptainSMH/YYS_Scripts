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

import re
from datetime import date
from pathlib import Path

from core.config.errors import ConfigError

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
PAGES_DIR: Path = ASSETS_DIR / "pages"
"""一个画面（页面）一个文件夹：模板图与 templates.yaml 都在里面。"""


SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")
"""页面名、元素名允许的字符：字母、数字、下划线、横线。

限制得这么死是因为它们直接变成文件夹名和文件名。
放行中文虽然可行，但路径、日志、代码引用里都会出现中文，排查时容易看花眼。
"""


def is_valid_segment(name: str) -> bool:
    """页面名/元素名是否合法（单段、只含字母数字下划线横线）。"""
    return bool(name) and bool(SEGMENT_PATTERN.match(name))


def page_dir(page: str) -> Path:
    """某个页面的资源目录：assets/pages/<page>/"""
    if not is_valid_segment(page):
        # 兜底：就算调用方忘了校验，也不允许拼出 ../ 这种路径
        raise ConfigError(
            f"页面名不合法：{page!r}，只允许字母、数字、下划线、横线"
        )
    return PAGES_DIR / page

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
