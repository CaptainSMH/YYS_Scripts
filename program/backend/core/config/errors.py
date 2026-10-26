"""配置层的异常。

和设备层、会话层的区别：
    设备层报错 = 这一次操作失败了，等一下/提权/换个窗口可能就好
    会话层报错 = 这一帧没认出目标，换一帧可能就好
    配置层报错 = 项目里的数据写错了或丢了，**重试多少次都不会好**

所以配置错误要单独一类：看到它就该去改文件，而不是重试。
"""

from __future__ import annotations


class ConfigError(RuntimeError):
    """配置有问题：实例配置、模板清单、模板图片。"""

    hint = "检查 configs/ 与 assets/pages/ 下的文件是否完整、名字是否对得上"


class TemplateMissing(ConfigError):
    """模板清单里没有这个 key。"""

    hint = "清单里没有这个模板：名字写错了，或者还没用 workbench 标注过"


class TemplateImageMissing(ConfigError):
    """清单里有条目，但图片文件读不出来。"""

    hint = "图片文件被删了或损坏了——重新标注这个模板，或者从 git 恢复"


class TemplateRoiInvalid(ConfigError):
    """roi 比模板图还小，永远匹配不到。"""

    hint = "roi 范围太小：用 workbench 选中这个模板，重新框一个更大的 roi"
