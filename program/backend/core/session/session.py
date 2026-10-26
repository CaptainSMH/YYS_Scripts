"""会话层：把「设备 + 识别 + 页面」组合成流程能直接用的动作。

流程层只跟它打交道，不直接碰截图、匹配、坐标：

    ctx = Session(device)
    ctx.require(HomePage)          # 确认停在主界面，不在就报错
    ctx.tap(HomePage.GUILD)        # 找到按钮并点击
    ctx.expect(GuildPage)          # 等阴阳寮界面出现（默认等 1 秒）

设计要点：
    · 所有等待都是「条件等待 + 轮询」，没有固定 sleep
    · 元素找不到、页面等不到，都抛明确的异常并带上当时的得分
    · 这一层不认识的游戏概念只有「页面」和「元素」两个
"""

from __future__ import annotations

import time

import numpy as np

from core.config import templates
from core.config.errors import TemplateImageMissing, TemplateMissing, TemplateRoiInvalid
from core.device.base import Device
from core.humanize import point_in_box
from core.humanize import hold as humanize_hold
from core.humanize.timing import DEFAULT_HOLD
from core.humanize.position import DEFAULT_SIGMA
from core.page import registry
from core.page.base import El, Page
from core.page.registry import PageMatch
from core.vision import match
from core.vision.io import load_image

DEFAULT_TIMEOUT = 1.0
"""expect / wait_any 的默认超时（秒）。

注意：1 秒对「页面加载」来说偏短——如果某个界面切过去要 1.5 秒才画完，
默认超时会误判失败。这类地方在调用时显式给大一点的 timeout，
不要靠改这个全局默认值去迁就特例。
"""
POLL_INTERVAL = 0.25


class SessionError(RuntimeError):
    """会话层的异常基类。"""


class PageTimeout(SessionError):
    """等到超时也没出现目标页面。"""

    hint = "界面没切过去：点击可能没生效、游戏卡住了，或者 timeout 给得太短"


class ElementNotFound(SessionError):
    """画面里找不到目标元素（得分低于阈值）。"""

    hint = "模板和画面不一致：可能不在这个界面、换了皮肤，或窗口尺寸变了"


class WrongPage(SessionError):
    """当前页面不是流程预期的那个。"""

    hint = "先手动切到该界面；或者让流程自己走回去再继续"


def owner_page(element: El) -> type[Page]:
    """找到这个元素属于哪个页面。

    用 `is` 比较对象身份——El 是类属性，全局只有一份，所以能可靠地反查。
    """
    for page_cls in registry.pages():
        for candidate in page_cls.elements().values():
            if candidate is element:
                return page_cls
    raise LookupError(f"元素 {element.name!r} 不属于任何已注册页面（页面模块 import 了吗）")


class Session:
    """一次运行期间的上下文：一个设备 + 一套页面。"""

    def __init__(
        self,
        device: Device,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        poll: float = POLL_INTERVAL,
        tap_sigma: float = DEFAULT_SIGMA,
        tap_hold: tuple[float, float] = DEFAULT_HOLD,
    ) -> None:
        self.device = device
        self.timeout = timeout
        self.poll = poll
        self.tap_sigma = tap_sigma
        self.tap_hold = tap_hold

    # ---------------------------------------------------------------- 画面

    def shot(self) -> np.ndarray:
        """抓一帧。"""
        return self.device.screenshot()

    def detect(self, frame: np.ndarray | None = None) -> PageMatch | None:
        """当前是哪个页面；认不出返回 None。"""
        return registry.detect(frame if frame is not None else self.shot())

    # ---------------------------------------------------------------- 页面

    def require(self, page_cls: type[Page]) -> PageMatch:
        """确认当前就在这个页面；不是就抛 WrongPage。

        流程开头用它声明前置条件：
            ctx.require(HomePage)     # 不在主界面就直接失败，而不是去点主界面的按钮
        """
        found = self.detect()
        if found is None or found.page is not page_cls:
            current = found.key if found is not None else "未知界面"
            raise WrongPage(f"需要先停在 {page_cls.key}，当前是 {current}")
        return found

    def expect(self, page_cls: type[Page], timeout: float | None = None) -> PageMatch:
        """等到出现这个页面；超时抛 PageTimeout。"""
        limit = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + limit
        last: PageMatch | None = None
        while True:
            found = self.detect()
            last = found
            if found is not None and found.page is page_cls:
                return found
            if time.monotonic() >= deadline:
                current = last.key if last is not None else "未知"
                raise PageTimeout(
                    f"等了 {limit:.1f}s 没等到 {page_cls.key}，当前是 {current}"
                )
            time.sleep(self.poll)

    def wait_any(
        self, *page_classes: type[Page], timeout: float | None = None
    ) -> PageMatch:
        """等到其中任意一个页面出现，返回命中的那个。

        页面个数不限：
            ctx.wait_any(GuildPage, timeout=8)
            ctx.wait_any(BarrierPage, LevelPopup, timeout=8)
        """
        if not page_classes:
            raise ValueError("wait_any 至少要给一个页面")
        limit = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + limit
        wanted = set(page_classes)
        last: PageMatch | None = None
        while True:
            found = self.detect()
            last = found
            if found is not None and found.page in wanted:
                return found
            if time.monotonic() >= deadline:
                names = [p.key for p in page_classes]
                current = last.key if last is not None else "未知"
                raise PageTimeout(f"等了 {limit:.1f}s 没等到 {names} 中的任何一个，当前是 {current}")
            time.sleep(self.poll)

    # ---------------------------------------------------------------- 元素

    def _locate_rect(self, element: El) -> tuple[int, int, int, int, float]:
        """找到元素，返回它的矩形 (x1, y1, 宽, 高) 和得分。

        配置问题（模板不存在、图片缺失、roi 非法）抛 ConfigError；
        画面问题（得分不够）抛 ElementNotFound。两者处理方式完全不同。
        """
        page_cls = owner_page(element)
        key = element.key(page_cls.page)
        item = templates.find(key)
        if item is None:
            raise TemplateMissing(f"模板清单里没有 {key}")

        image = load_image(item.image_path)
        if image is None:
            raise TemplateImageMissing(f"读不出模板图：{item.image_path}")

        frame = self.shot()
        score, location = match.best_match(frame, image, item.roi)
        if location is None:
            raise TemplateRoiInvalid(f"{key} 的 roi 比模板图还小")

        if score < item.threshold:
            raise ElementNotFound(f"{key} 得分 {score:.3f} 低于阈值 {item.threshold:.2f}")

        height, width = image.shape[:2]
        return location[0], location[1], width, height, score

    def locate(self, element: El) -> tuple[int, int, float]:
        """找到元素，返回中心点像素坐标和得分；找不到抛 ElementNotFound。"""
        x, y, width, height, score = self._locate_rect(element)
        return x + width // 2, y + height // 2, score

    def tap(
        self,
        element: El,
        sigma: float | None = None,
        hold: tuple[float, float] | None = None,
    ) -> tuple[int, int]:
        """找到元素并点击，返回实际点击的坐标。

        两处拟人化：
            · 点哪里：交给 core.humanize.position 按正态分布随机
              （中心密、边缘疏，像人瞄准中心再手抖）
            · 按多久：交给 core.humanize.timing 随机 50~120 毫秒
              （真实的点击不是 0 毫秒）

        sigma=0 或 hold=(0, 0) 可以关掉对应的随机化，用于调试。
        """
        x1, y1, width, height, _score = self._locate_rect(element)
        ratio = self.tap_sigma if sigma is None else sigma
        target_x, target_y = point_in_box((x1, y1, x1 + width, y1 + height), sigma=ratio)

        hold_seconds = humanize_hold(self.tap_hold if hold is None else hold)
        self.device.tap(target_x, target_y, hold_ms=int(hold_seconds * 1000))
        return target_x, target_y
