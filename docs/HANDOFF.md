# 交接说明

> 写给下一个接手这个项目的人（或 AI）。读完这一份，你应该知道：
> 项目现在能做什么、代码在哪、有哪些坑、下一步该干什么。
>
> 最后更新：2026-10-27 · 对应提交 `0838816`

---

## 0. 动手之前

**这个项目的用户有明确的协作规矩**（见仓库根 `AGENTS.md`）：

- 一律中文回答，技术名词保留英文原名
- **任何修改之前必须先问，拿到明确答复才能动手**
- 用户提问、咨询、讨论**都不构成修改授权**；只有「做 / 写 / 改 / 开始」才算
- 拿不准就问；不确定的事明说不确定，不要凭印象编游戏界面的细节

违反这条是本次会话里被反复纠正最多的问题。宁可多问一句。

---

## 1. 项目是什么

阴阳师的桌面版自动化：后台截图 + 模板匹配 + 后台点击，目标是多开、长期可维护。

**核心思路**：把「会随游戏更新变的东西」（模板图、roi、阈值）和「界面结构」（有哪些按钮、怎么判断在哪个界面）分开。
前者放 yaml + png，后者写 Python。

---

## 2. 环境与运行

```
C:\Users\Smh\Desktop\YYS_Scripts\
├─ docs/                 PROJECT.md（设计）/ CHANGELOG.md（变更）/ HANDOFF.md（本文）
└─ program/
   ├─ backend/           ← 代码根（有 .project-root 标记）
   │  ├─ .venv/          Python 3.14.7，依赖见 requirements.txt
   │  ├─ core/  game/  tools/
   │  ├─ assets/pages/   模板图与清单
   │  ├─ configs/instances/  实例绑定（不纳入版本控制）
   │  └─ artifacts/      截图与临时产物（不纳入版本控制）
   └─ temp_scripts/      一次性脚本
```

**所有命令都要在 `program/backend` 下执行，并用 `python -m tools.xxx` 的形式**
（`-m` 会让项目根进入 `sys.path`，否则 `import core` 失败）。

```powershell
cd C:\Users\Smh\Desktop\YYS_Scripts\program\backend
.\.venv\Scripts\python.exe -m tools.doctor          # 环境自检，先跑这个
```

### 需要管理员权限的操作

游戏以管理员身份运行，受 UIPI 限制：

| 操作 | 要提权吗 |
|---|---|
| 截图、模板匹配、判定页面 | 不要 |
| **后台点击** | **要** |
| **调整窗口尺寸** | **要** |

`tools/runner.py` 会自己弹 UAC 提权；其它工具不会。

---

## 3. 代码地图

| 层 | 目录 | 关键文件 | 职责 |
|---|---|---|---|
| 配置 | `core/config/` | `paths.py` | 路径唯一来源；页面名/元素名校验 |
| | | `templates.py` | 模板清单读写（一页面一个 yaml） |
| | | `instances.py` | 实例绑定（一实例一文件） |
| | | `errors.py` | `ConfigError` 一族：改文件才能好的错误 |
| 设备 | `core/device/` | `base.py` | `Device` 抽象接口 + `DeviceError` 一族 |
| | | `desktop.py` | pywin32 实现：枚举窗口、BitBlt 截图、PostMessage 点击 |
| 识别 | `core/vision/` | `roi.py` | 归一化 roi ↔ 像素坐标 |
| | | `match.py` | `best_match(frame, template, roi) -> (得分, 坐标)` |
| | | `io.py` | `load_image` / `save_image`（兼容中文路径）|
| | | `quality.py` | 纹理检查（拦纯色模板）|
| 页面 | `core/page/` | `base.py` | `Page`（key/page/anchors/priority）+ `El` 元素 |
| | | `registry.py` | 注册表；`evaluate()` 逐页检查、`detect()` 给结论 |
| 会话 | `core/session/` | `session.py` | `Session` 7 个原子动作 + `SessionError` 一族 |
| 拟人 | `core/humanize/` | `position.py` | `point_in_box`：正态分布取点击点 |
| | | `timing.py` | `delay` / `hold`：随机间隔与按压时长 |
| 页面定义 | `game/pages/` | `home.py` / `guild.py` | 每个界面一个类 |
| 流程 | `game/flows/` | `enter_guild.py` | 每个任务一个 `run(ctx)` 函数 |
| 工具 | `tools/` | 见下节 | 8 个命令 |

---

## 4. 现在能做什么（都验证过）

### 页面判定

| 页面 | 锚点 | 优先级 |
|---|---|---|
| `home`（庭院）| `shikigami_entry` + `friends_entry` | 10 |
| `guild`（阴阳寮）| `barrier` + `info` | 20 |

实测：主界面连抓 5 帧都是 `home`（锚点 1.000）；切到式神录后判为「未知」（锚点降到 0.40）。

### 模板

```
assets/pages/home/   explore、friends_entry、guild_entry、shikigami_entry、shop_entry
assets/pages/guild/  back、barrier、info
```

### 工具

| 命令 | 用途 |
|---|---|
| `python -m tools.doctor` | 环境自检：解释器、依赖、路径、管理员权限 |
| `python -m tools.list_windows` | 列出所有游戏窗口 |
| `python -m tools.pick_window` | 绑定窗口到实例（`--list` / `--remove` / `--rebind`）|
| `python -m tools.capture` | 截图存盘 |
| `python -m tools.workbench` | **图形界面**：截图、框选生成模板、核对 roi |
| `python -m tools.whereami` | 报告所有模板的得分/位置 + 页面判定（支持 `--file` 用历史截图）|
| `python -m tools.check_pages` | 检查页面定义与模板清单是否对得上 |
| `python -m tools.runner` | **图形界面**：跑流程（自动提权，日志在窗口里）|

### 唯一能跑的流程

`game/flows/enter_guild.py`：确认在主界面 → 点阴阳寮 → 等阴阳寮界面出现。
真机跑通过（锚点 barrier=0.998、info=0.989）。

---

## 5. 必须知道的约定与坑

1. **分辨率统一 1280×720**。模板是分辨率绑定的——1280 下采的模板在 800×450 画面上
   得分只有 0.25~0.53。
   客户区比例不是精确 16:9 时，构造 `DesktopDevice` 会自动改成 1280×720
   （需要管理员权限）。但**已经是 16:9 的小窗口（如 800×450）不会被改**。

2. **庭院皮肤固定**。换皮肤会让底部导航栏整体位移十几像素，0.95 阈值的模板会失配。

3. **阈值是采样出来的**：工作台保存模板时连采 12 帧，取「最低分 − 0.05」。
   静态元素约 0.95，有光效的元素约 0.85。

4. **纯色区域不能做模板**。`TM_CCOEFF_NORMED` 对常数模板恒返回 1.0，
   会在任何画面上「完美匹配」并点到错误位置。工作台和 `check_pages` 都会拦。

5. **命名规则**：页面名/元素名只允许字母、数字、下划线、横线（直接变成文件夹和文件名）。
   进入另一个界面的入口统一加 `_entry` 后缀（如 `guild_entry`）；页签不加（如 `guild/barrier`）。

6. **窗口绑定用 `title_match` + `match_index`，不用 hwnd/pid**（两者每次启动都变）。
   代价：`match_index` 是按屏幕位置排序后的序号，**挪动窗口位置可能导致绑到别的账号**。

7. **页面定义写 Python，参数写 yaml**。加一个界面 = 标 2 个锚点 + 写一个 `Page` 子类 +
   在 `game/pages/__init__.py` 里 import。

---

## 6. 设计决策（别轻易推翻）

| 决策 | 理由 |
|---|---|
| 会话层只有 7 个原子动作，没有 `goto`/`back`/`seen` | 能由现有动作组合出来的就不单独提供；用户明确要求过删掉 |
| 不提供 `goto(目标页面)` | 真实场景经常是「点一下看看出现什么」，并不知道目标 |
| 页面层用类而不是 yaml | 导入时就能校验；IDE 能跳转；结构不该随游戏更新变 |
| 拟人化只算数字，不碰设备 | 纯函数，不用开游戏就能测 |
| 异常分三层 + `hint` | 配置错误重试无用、会话错误换帧可能就好、设备错误是环境问题 |
| 流程用异常表达失败，不返回状态码 | 异常信息里带得分、当前页面，排查更快 |

---

## 7. 已知问题（按优先级）

| 优先级 | 问题 | 位置 | 备注 |
|---|---|---|---|
| 高 | 窗口位置变化会导致绑定错账号 | `desktop.list_game_windows()` 按位置排序 + `match_index` | 需要更稳的标识（如标题里的服务器名组合）|
| 中 | 800×450 窗口不会被自动统一到 1280×720 | `desktop._ensure_aspect()` | 只改比例不对的；要不要改规则需问用户 |
| 中 | 换皮肤后静态模板失配 | 阈值 0.95 太严 | 用户已决定「固定使用当前皮肤」|
| 低 | `_arg(argv, flag)` 复制了两份 | `tools/capture.py`、`tools/whereami.py` | 可抽到 `tools/_cli.py` |
| 低 | `expect` / `wait_any` 的轮询循环重复 | `core/session/session.py` | 可抽 `_wait_until(predicate)` |
| 低 | 「读实例 → 建设备」重复 4 处 | capture / whereami / runner / workbench | 可抽 `tools/_device.py` |
| 低 | `tests/` 目录还不存在 | — | 目前靠 `whereami --file` 手工回归 |

---

## 8. 下次从哪里开始

### 路线上的位置

`docs/PROJECT.md` 第 11 节的开发路线：P0 ✅、P1 ✅、P2 ✅（页面层 + 判定）、
**P3 单任务闭环进行中**（会话层和运行器有了，但只有一个 10 行的流程）。

### 建议的下一步（按价值排序）

**A. 把「进阴阳寮」扩成一个真任务**
现在 `enter_guild` 只是「点进去看一眼」。可以接着做：
阴阳寮界面里的页签（神社 `shrine` / 祈愿 `wish` / 结界 `barrier` / 寮信息 `info`，
后两个已标）+ 一个实际动作（签到 / 捐献 / 领取）。

**B. 补第二个界面（式神录）**
进式神录 → 认出来 → 返回。这会第一次用到「从子界面回到主界面」的完整链路，
能暴露恢复策略的缺口。

**C. 加「等待画面稳定」**
现在 `expect` 是第一帧匹配上就返回。战斗/切界面有动画，容易截到中间帧导致误判。
做法：连续两帧都匹配上才算命中（多一次截图，约 40ms）。

**D. 截图复用**
一次操作里连续 `locate` 多个元素会重复截图（每次约 40ms）。
需要 `attach()` / `detach()` 式的帧缓存，但要显式管理，避免点到过期画面。

### 开始前先做的三件事

```powershell
cd C:\Users\Smh\Desktop\YYS_Scripts\program\backend
.\.venv\Scripts\python.exe -m tools.doctor        # 环境是否就绪
.\.venv\Scripts\python.exe -m tools.check_pages   # 页面定义与模板是否还对得上
.\.venv\Scripts\python.exe -m tools.whereami --instance 随便玩玩002   # 当前画面能否判定
```

`check_pages` 退出码为 1 说明有断链，先修断链再谈新功能。

---

## 9. 没有测试框架时怎么验证

项目里还没有 `tests/`，但有三种可靠的验证手段：

1. **`whereami --file <历史截图>`**：不用开游戏就能验证识别逻辑。
   `artifacts/captures/` 下已经存了几张不同时刻的截图（含换皮肤前后的对比）。

2. **假设备跑流程**：写一个继承 `Device` 的类，`screenshot()` 返回固定帧、
   `tap()` 记录坐标，就能离线跑完整流程：

   ```python
   class Fake(Device):
       def client_size(self): return (1280, 720)
       def _grab(self): return frame
       def tap(self, x, y, hold_ms=0): self.calls.append((x, y, hold_ms))
       def swipe(self, *a, **k): pass
   ```

3. **合成画面**：把模板图贴到主界面截图的对应位置上，就能造出「假的阴阳寮界面」，
   用来测页面判定和流程分支，完全不碰游戏。

纯函数（`core/vision`、`core/humanize`）可以直接单测，不需要任何前提。
