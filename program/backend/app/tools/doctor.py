"""环境自检：确认解释器、依赖、路径、权限都正常。

用法（在项目根目录下）：
    python -m tools.doctor
"""

from __future__ import annotations

import ctypes
import sys
import unicodedata
from importlib import metadata

from core.config import paths

# 需要检查的第三方包（显示名 -> 发行名）
_REQUIRED_PACKAGES = {
    "numpy": "numpy",
    "opencv-python-headless": "opencv-python-headless",
    "PyYAML": "pyyaml",
}


def _pad(text: str, width: int) -> str:
    """按显示宽度左对齐补空格（中文算 2 个宽度）。"""
    shown = sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)
    return text + " " * max(0, width - shown)


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _package_version(dist_name: str) -> str | None:
    try:
        return metadata.version(dist_name)
    except metadata.PackageNotFoundError:
        return None


def main() -> int:
    problems: list[str] = []
    label_width = 24

    def line(label: str, value: str) -> None:
        print(f"{_pad(label, label_width)}: {value}")

    print("=" * 60)
    print("环境自检")
    print("=" * 60)

    # ---- 解释器
    line("解释器", sys.executable)
    line("Python", sys.version.split()[0])

    in_venv = sys.prefix != sys.base_prefix
    line("虚拟环境", f"是（{sys.prefix}）" if in_venv else "否")
    if not in_venv:
        problems.append("没有在 .venv 中运行，可能缺少依赖")

    # ---- 依赖
    print("-" * 60)
    for display, dist in _REQUIRED_PACKAGES.items():
        version = _package_version(dist)
        line(display, version or "未安装")
        if version is None:
            problems.append(f"缺少依赖 {dist}")

    # 实际 import 一次，确认不是装了但坏了
    for module in ("numpy", "cv2", "yaml"):
        try:
            __import__(module)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"import {module} 失败：{exc}")

    # ---- 路径
    print("-" * 60)
    line("项目根", str(paths.PROJECT_ROOT))
    for name in ("ASSETS_DIR", "CONFIGS_DIR", "TEMPLATES_DIR", "ARTIFACTS_DIR"):
        path = getattr(paths, name)
        line(name, f"{'存在' if path.exists() else '不存在（需要时创建）'}  {paths.rel(path)}")

    # ---- 权限
    print("-" * 60)
    admin = _is_admin()
    line("管理员权限", "是" if admin else "否")
    if not admin:
        print(f"{_pad('', label_width)}  截图/识别可用；点击需要以管理员身份运行")

    # ---- 结论
    print("=" * 60)
    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("一切正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
