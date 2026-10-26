"""拟人化：让操作「像人」，而不是像脚本。

分三类，各自独立：
    position  点哪里   —— 点击位置的概率分布
    timing    什么时候 —— 操作间隔、按压时长
    path      怎么移动 —— 拖动轨迹（还没做）

共同点：这里全是**纯函数**，只算数字，不碰设备、不截图、不依赖游戏。
所以可以直接单测，不用开游戏。
"""

from core.humanize.position import point_in_box
from core.humanize.timing import delay, hold

__all__ = ["point_in_box", "delay", "hold"]
