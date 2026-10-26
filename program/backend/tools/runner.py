"""流程运行器：专门用来跑流程的一个小窗口。

双击或在 PyCharm 里直接运行本文件即可，它会：
    1. 检测自己是不是管理员——不是就自动弹 UAC 重新以管理员身份启动自己
    2. 打开一个小窗口：选实例、选流程、点运行
    3. 把流程里的 print 全部显示在窗口里（不需要控制台）

为什么单独一个文件而不是塞进工作台：
    工作台是「标模板、调 roi」的开发工具，日常跑的流程不应该每次都被
    一堆模板列表和截图按钮围着。职责分开，界面也简单。
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    # 允许「直接双击本文件」也能 import core：此时 sys.path[0] 是 tools/
    sys.path.insert(0, str(_BACKEND))

from core.config import instances  # noqa: E402
from core.config.errors import ConfigError  # noqa: E402
from core.device.base import DeviceError  # noqa: E402
from core.device.desktop import DesktopDevice, is_elevated  # noqa: E402
from core.session.session import Session, SessionError  # noqa: E402
from game import flows  # noqa: E402


def ensure_admin() -> None:
    """不是管理员就重新以管理员身份启动自己，然后退出当前进程。"""
    if is_elevated():
        return
    script = str(Path(__file__).resolve())
    params = " ".join(f'"{arg}"' for arg in [script, *sys.argv[1:]])
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, str(_BACKEND), 1
    )
    if result <= 32:
        # 用户点了「否」，或者 UAC 被禁用
        ctypes.windll.user32.MessageBoxW(
            None, "后台点击需要管理员权限，请允许提权后重试。", "无法启动", 0x10
        )
    sys.exit(0)


class LogWriter:
    """把 print 的输出导到窗口里的文本框。"""

    def __init__(self, sink) -> None:
        self.sink = sink

    def write(self, text: str) -> None:
        if text:
            self.sink(text)

    def flush(self) -> None:
        pass


class Runner:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.running = False

        root.title("阴阳师流程运行器")
        root.geometry("760x480")

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="实例").pack(side="left")
        self.instance_var = tk.StringVar()
        self.instance_box = ttk.Combobox(
            top, textvariable=self.instance_var, width=22, state="readonly"
        )
        self.instance_box.pack(side="left", padx=6)

        ttk.Label(top, text="流程").pack(side="left", padx=(12, 0))
        self.flow_var = tk.StringVar()
        self.flow_box = ttk.Combobox(
            top, textvariable=self.flow_var, width=18, state="readonly"
        )
        self.flow_box.pack(side="left", padx=6)

        self.run_button = ttk.Button(top, text="运行", command=self.run_flow)
        self.run_button.pack(side="left", padx=(12, 0))
        ttk.Button(top, text="清空日志", command=self.clear_log).pack(side="left", padx=6)

        self.status = ttk.Label(root, text="就绪", anchor="w", padding=(8, 0))
        self.status.pack(fill="x")

        frame = ttk.Frame(root, padding=(8, 4))
        frame.pack(fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical")
        self.log = tk.Text(frame, wrap="word", state="disabled", yscrollcommand=scroll.set)
        scroll.config(command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        self.refresh_instances()

        # 把 print 的输出去向重定向到窗口
        sys.stdout = LogWriter(self.append_log)
        sys.stderr = LogWriter(self.append_log)

    # ---------------------------------------------------------------- 界面

    def refresh_instances(self) -> None:
        names = [item.name for item in instances.list_all()]
        self.instance_box["values"] = names
        if names:
            self.instance_var.set(names[0])
        self.flow_box["values"] = list(flows.FLOWS)
        if flows.FLOWS:
            self.flow_var.set(next(iter(flows.FLOWS)))

    def append_log(self, text: str) -> None:
        def write() -> None:
            self.log.configure(state="normal")
            self.log.insert("end", text)
            self.log.see("end")
            self.log.configure(state="disabled")

        self.root.after(0, write)

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ---------------------------------------------------------------- 运行

    def run_flow(self) -> None:
        if self.running:
            return

        name = self.flow_var.get()
        flow = flows.FLOWS.get(name)
        if flow is None:
            messagebox.showinfo("没有流程", "没有可运行的流程", parent=self.root)
            return

        instance_name = self.instance_var.get()
        if not instance_name:
            messagebox.showwarning("没有实例", "请先选择实例", parent=self.root)
            return

        try:
            item = instances.load(instance_name)
        except OSError as exc:
            messagebox.showerror("读不了实例配置", str(exc), parent=self.root)
            return

        if item is None:
            # 配置文件可能在外部被删了，而下拉框还停在旧名字上
            messagebox.showerror(
                "实例配置不存在",
                f"找不到实例 {instance_name!r} 的配置。\n点右上角的「清空日志」旁边重新选一个，或重启本工具。",
                parent=self.root,
            )
            self.refresh_instances()
            return

        try:
            device = DesktopDevice(item.title_match, item.match_index)
        except DeviceError as exc:
            messagebox.showerror("找不到窗口", str(exc), parent=self.root)
            return

        ctx = Session(device)
        self.running = True
        self.run_button.config(state="disabled")
        self.status.config(text=f"运行中：{name}")
        print(f"=== 运行 {name}（实例 {instance_name}）{time.strftime('%H:%M:%S')} ===")

        def worker() -> None:
            started = time.monotonic()
            try:
                flow(ctx)
                message = f"完成：{name}   用时 {time.monotonic() - started:.1f}s"
                print(message)
            except (SessionError, DeviceError, ConfigError) as exc:
                # 预期内的失败：消息本身就是给人看的，不需要堆栈
                message = f"失败：{name} — {exc}"
                hint = getattr(exc, "hint", "")
                print(f"失败：{name}")
                print(f"  原因：{exc}")
                if hint:
                    print(f"  建议：{hint}")
            except Exception as exc:
                # 真的出 bug 了：堆栈是唯一线索
                message = f"失败：{name} — 未预期错误（见日志）"
                print(message)
                print(f"  原因：{type(exc).__name__}: {exc}")
                traceback.print_exc()
            print()

            def finish() -> None:
                self.running = False
                self.run_button.config(state="normal")
                self.status.config(text=message)

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()


def main() -> int:
    ensure_admin()
    root = tk.Tk()
    Runner(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
