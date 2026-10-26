"""模板工作台：截图、框选生成模板、核对/调整 roi，全在一个窗口里完成。

用法（PyCharm 里直接运行本文件即可，不需要命令行参数）：
    python -m tools.workbench

窗口布局：
    顶部   实例下拉 + 截图 + 刷新列表
    左边   画面（可拖框；蓝框 = roi，红框 = 模板匹配位置）
    右边   模板列表 + 选中模板的信息
    底部   保存为新模板 / 更新选中模板的 roi / 删除模板

设计取舍：
    列表显示「所有页面」的模板，而不是只显示当前画面的。
    因为核对 roi 时关心的是「这个模板框在哪儿」，跟当前选的哪个实例无关。
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from dataclasses import replace
from tkinter import messagebox, simpledialog, ttk

import numpy as np

from core.config import instances, paths, templates
from core.device.base import DeviceError
from core.device.desktop import DesktopDevice
from core.vision import match
from core.vision.io import load_image, save_image
from core.vision.roi import clamp_box, expand_roi, pixels_to_roi, roi_to_pixels

HANDLE_TOL = 6  # 判定「点在框内」的容差（像素）
MIN_BOX = 8

# 标定阈值时采多少帧、每帧间隔多少秒、最低分之上留多少余量
SAMPLE_COUNT = 12
SAMPLE_INTERVAL = 0.15
THRESHOLD_MARGIN = 0.05


class PagePicker(tk.Toplevel):
    """选页面文件夹：点已有页面，或直接输入新名字（会自动新建文件夹）。"""

    def __init__(self, parent: tk.Misc, pages: list[str]) -> None:
        super().__init__(parent)
        self.result: str | None = None

        self.title("选择页面文件夹")
        self.transient(parent)
        self.resizable(False, False)

        tk.Label(
            self, text="选一个已有页面；或在下面输入新名字（会自动新建文件夹）："
        ).pack(padx=12, pady=(12, 4), anchor="w")

        self.listbox = tk.Listbox(self, height=max(3, min(8, len(pages) or 3)), exportselection=False)
        for page in pages:
            self.listbox.insert("end", page)
        self.listbox.pack(padx=12, fill="x")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        if pages:
            self.listbox.selection_set(0)

        self.entry = tk.Entry(self)
        self.entry.pack(padx=12, pady=8, fill="x")
        self.entry.bind("<Return>", lambda _event: self._ok())
        self.entry.focus_set()

        row = tk.Frame(self)
        row.pack(padx=12, pady=(0, 12), fill="x")
        tk.Button(row, text="取消", width=8, command=self._cancel).pack(side="right")
        tk.Button(row, text="确定", width=8, command=self._ok).pack(side="right", padx=6)

        self.bind("<Escape>", lambda _event: self._cancel())
        self.grab_set()

    def _on_select(self, _event=None) -> None:
        selected = self.listbox.curselection()
        if selected:
            self.entry.delete(0, "end")
            self.entry.insert(0, self.listbox.get(selected[0]))

    def _ok(self) -> None:
        self.result = self.entry.get().strip()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


def ask_page(parent: tk.Misc) -> str | None:
    picker = PagePicker(parent, templates.list_pages())
    parent.wait_window(picker)
    return picker.result


class Workbench:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.frame: np.ndarray | None = None
        self.device: DesktopDevice | None = None
        self.template_image: np.ndarray | None = None
        self.selected: templates.Template | None = None
        self.box: tuple[int, int, int, int] | None = None
        self.scale = 1
        self.photo: tk.PhotoImage | None = None
        self._drag_mode: str | None = None
        self._start: tuple[int, int] | None = None
        self._origin_box: tuple[int, int, int, int] | None = None
        self._last_score = 0.0

        self._build_ui()
        self.refresh_instances()
        self.refresh_templates()

    # ---------------------------------------------------------------- 界面

    def _build_ui(self) -> None:
        self.root.title("模板工作台")
        self.root.geometry("1400x820")

        top = ttk.Frame(self.root, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="实例").pack(side="left")
        self.instance_var = tk.StringVar()
        self.instance_box = ttk.Combobox(
            top, textvariable=self.instance_var, width=24, state="readonly"
        )
        self.instance_box.pack(side="left", padx=6)
        ttk.Button(top, text="截图", command=self.take_screenshot).pack(side="left")
        ttk.Button(top, text="刷新列表", command=self.refresh_templates).pack(side="left", padx=6)
        self.status = ttk.Label(top, text="就绪")
        self.status.pack(side="left", padx=12)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, background="#222222", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        right = ttk.Frame(body, width=320)
        right.pack(side="right", fill="y")
        ttk.Label(right, text="模板列表").pack(anchor="w", padx=6, pady=(6, 2))

        list_frame = ttk.Frame(right)
        list_frame.pack(fill="both", expand=True, padx=6)
        scroll = ttk.Scrollbar(list_frame, orient="vertical")
        self.tree = ttk.Treeview(
            list_frame, show="tree", selectmode="browse", yscrollcommand=scroll.set
        )
        scroll.config(command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_template)
        self._items: dict[str, templates.Template] = {}

        self.info = ttk.Label(right, text="", justify="left", anchor="w", wraplength=300)
        self.info.pack(fill="x", padx=6, pady=8)

        bottom = ttk.Frame(self.root, padding=6)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="保存为新模板", command=self.save_as_new).pack(side="left")
        ttk.Button(bottom, text="更新选中模板的 roi", command=self.update_selected_roi).pack(
            side="left", padx=6
        )
        ttk.Button(bottom, text="删除模板", command=self.delete_selected).pack(side="left")
        ttk.Label(bottom, text="在框外拖 = 新画；在框内拖 = 移动").pack(side="right")

    # ---------------------------------------------------------------- 数据

    def refresh_instances(self) -> None:
        names = [item.name for item in instances.list_all()]
        self.instance_box["values"] = names
        if names and not self.instance_var.get():
            self.instance_var.set(names[0])
        if not names:
            self.status.config(text="没有实例配置，请先运行 tools.pick_window")

    def refresh_templates(self) -> None:
        """按页面分组重建树：第一层是页面文件夹，展开才是模板。"""
        self.tree.delete(*self.tree.get_children())
        self._items = {}

        pages = templates.list_pages()
        for page in pages:
            members = sorted(templates.load_page(page), key=lambda t: t.name)
            node = self.tree.insert(
                "", "end", iid=f"page::{page}", text=f"{page}  ({len(members)})", open=True
            )
            for item in members:
                iid = f"tpl::{item.key}"
                self.tree.insert(node, "end", iid=iid, text=item.name)
                self._items[iid] = item

        self.status.config(text=f"{len(pages)} 个页面，共 {len(self._items)} 个模板")

    def select_template(self, key: str) -> None:
        """在树里选中某个模板并加载它。"""
        iid = f"tpl::{key}"
        if iid in self._items:
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self.on_select_template()

    def _current_instance(self) -> instances.Instance | None:
        name = self.instance_var.get()
        if not name:
            return None
        return instances.load(name)

    # ---------------------------------------------------------------- 截图

    def take_screenshot(self) -> None:
        item = self._current_instance()
        if item is None:
            messagebox.showwarning("没有实例", "请先选择实例（或运行 tools.pick_window 绑定）", parent=self.root)
            return
        try:
            device = DesktopDevice(item.title_match, item.match_index)
            frame = device.screenshot()
        except DeviceError as exc:
            messagebox.showerror("截图失败", str(exc), parent=self.root)
            return

        self.device = device
        self.frame = frame
        self.box = None
        self.selected = None
        self.template_image = None
        self.scale = self._fit_scale(frame)
        self._render()
        self.status.config(text=f"已截图 {item.name}  {frame.shape[1]}x{frame.shape[0]}")

    def _fit_scale(self, frame: np.ndarray) -> int:
        height, width = frame.shape[:2]
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        scale = 1
        while width // scale > screen_w * 0.9 or height // scale > screen_h * 0.8:
            scale += 1
        return scale

    # ---------------------------------------------------------------- 绘制

    def _s(self, value: int) -> int:
        return int(round(value / self.scale))

    def _render(self) -> None:
        self.canvas.delete("all")
        if self.frame is None:
            return

        preview = self.frame if self.scale == 1 else self.frame[:: self.scale, :: self.scale]
        temp = paths.ARTIFACTS_DIR / "workbench" / "preview.png"
        save_image(temp, preview)
        self.photo = tk.PhotoImage(file=str(temp))
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.config(width=preview.shape[1], height=preview.shape[0])

        if self.box is not None:
            x1, y1, x2, y2 = self.box
            self.canvas.create_rectangle(
                self._s(x1), self._s(y1), self._s(x2), self._s(y2), outline="#3399ff", width=2
            )

        best = self._best_match()
        if best is not None and self.template_image is not None:
            bx, by = best
            th, tw = self.template_image.shape[:2]
            self.canvas.create_rectangle(
                self._s(bx), self._s(by), self._s(bx + tw), self._s(by + th),
                outline="#ff3333", width=1,
            )

        self._update_info()

    def _best_match(self) -> tuple[int, int] | None:
        if self.box is None or self.template_image is None or self.frame is None:
            return None
        height, width = self.frame.shape[:2]
        roi = pixels_to_roi(self.box, width, height)
        self._last_score, location = match.best_match(self.frame, self.template_image, roi)
        return location

    def _update_info(self) -> None:
        if self.box is None or self.frame is None:
            self.info.config(text="（画面上拖一个框）")
            return
        x1, y1, x2, y2 = self.box
        height, width = self.frame.shape[:2]
        roi = pixels_to_roi(self.box, width, height)
        lines = [
            f"框选  {x2 - x1}×{y2 - y1}",
            f"roi   {roi}",
        ]
        if self.selected is not None:
            lines.append(f"当前模板  {self.selected.key}")
            lines.append(f"匹配得分  {self._last_score:.3f}   阈值 {self.selected.threshold}")
        else:
            lines.append("（未选中模板）")
        self.info.config(text="\n".join(lines))

    # ---------------------------------------------------------------- 鼠标

    def on_press(self, event) -> None:
        if self.frame is None:
            return
        px, py = event.x * self.scale, event.y * self.scale
        if self.box is not None:
            x1, y1, x2, y2 = self.box
            inside = (x1 - HANDLE_TOL <= px <= x2 + HANDLE_TOL) and (
                y1 - HANDLE_TOL <= py <= y2 + HANDLE_TOL
            )
        else:
            inside = False

        self._start = (px, py)
        self._drag_mode = "move" if inside else "new"
        self._origin_box = self.box if inside else None

    def on_drag(self, event) -> None:
        if self._start is None or self._drag_mode is None or self.frame is None:
            return
        px, py = event.x * self.scale, event.y * self.scale
        height, width = self.frame.shape[:2]

        if self._drag_mode == "new":
            self.box = clamp_box(
                (
                    int(min(self._start[0], px)),
                    int(min(self._start[1], py)),
                    int(max(self._start[0], px)),
                    int(max(self._start[1], py)),
                ),
                width,
                height,
            )
        elif self._origin_box is not None:
            dx, dy = px - self._start[0], py - self._start[1]
            ox1, oy1, ox2, oy2 = self._origin_box
            w, h = ox2 - ox1, oy2 - oy1
            nx1 = min(max(0, ox1 + dx), width - w)
            ny1 = min(max(0, oy1 + dy), height - h)
            self.box = (int(nx1), int(ny1), int(nx1 + w), int(ny1 + h))
        self._render()

    def on_release(self, _event) -> None:
        self._drag_mode = None
        self._start = None
        self._origin_box = None

    # ---------------------------------------------------------------- 列表

    def on_select_template(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        item = self._items.get(selection[0])
        if item is None:
            # 选中的是页面节点，不是模板
            self.status.config(text="（这是页面文件夹，展开选里面的模板）")
            return
        image = load_image(item.image_path)
        if image is None:
            messagebox.showerror("读图失败", f"找不到模板图：{item.image_path}", parent=self.root)
            return
        self.selected = item
        self.template_image = image
        if self.frame is not None:
            height, width = self.frame.shape[:2]
            self.box = roi_to_pixels(item.roi, width, height)
        self._render()
        self.status.config(text=f"已选中 {item.key}")

    # ---------------------------------------------------------------- 操作

    def _box_ok(self) -> bool:
        if self.box is None or self.frame is None:
            messagebox.showinfo("没有框", "请先在画面上拖出一个框", parent=self.root)
            return False
        x1, y1, x2, y2 = self.box
        if x2 - x1 < MIN_BOX or y2 - y1 < MIN_BOX:
            messagebox.showinfo("框太小", f"框至少要 {MIN_BOX}×{MIN_BOX} 像素", parent=self.root)
            return False
        return True

    def save_as_new(self) -> None:
        if not self._box_ok():
            return
        assert self.box is not None and self.frame is not None

        page = ask_page(self.root)
        if not page:
            return
        element = simpledialog.askstring(
            "元素命名", f"页面「{page}」里这个元素叫什么？（如 explore）", parent=self.root
        )
        if not element:
            return
        element = element.strip()

        if templates.find(f"{page}/{element}") is not None:
            if not messagebox.askyesno(
                "已存在", f"「{page}/{element}」已存在，覆盖吗？", parent=self.root
            ):
                return

        x1, y1, x2, y2 = self.box
        crop = self.frame[y1:y2, x1:x2]
        height, width = self.frame.shape[:2]
        roi = expand_roi(self.box, width, height)

        scores = [match.score(self.frame, crop, roi)]
        if self.device is not None:
            for _ in range(SAMPLE_COUNT - 1):
                time.sleep(SAMPLE_INTERVAL)
                try:
                    extra = self.device.screenshot()
                except DeviceError:
                    break
                if extra.shape != self.frame.shape:
                    break
                scores.append(match.score(extra, crop, roi))
        lowest = min(scores)
        threshold = round(max(0.5, lowest - THRESHOLD_MARGIN), 2)

        try:
            templates.save_image(page, element, crop)
            item = templates.Template(
                page=page,
                name=element,
                file=f"{element}.png",
                roi=roi,
                threshold=threshold,
            )
            templates.save(item)
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)
            return

        self.refresh_templates()
        self.select_template(item.key)
        self.status.config(
            text=f"已保存 {item.key}  采样 {len(scores)} 帧  最低 {lowest:.3f}  阈值 {threshold}"
        )

    def update_selected_roi(self) -> None:
        if self.selected is None:
            messagebox.showinfo("没有选中", "先在右边列表里选一个模板", parent=self.root)
            return
        if not self._box_ok():
            return
        assert self.box is not None and self.frame is not None
        height, width = self.frame.shape[:2]
        new_roi = pixels_to_roi(self.box, width, height)
        try:
            manifest = templates.save(replace(self.selected, roi=new_roi))
        except ValueError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)
            return
        self.selected = replace(self.selected, roi=new_roi)
        self.status.config(text=f"roi 已更新为 {new_roi} -> {paths.rel(manifest)}")
        self._render()

    def delete_selected(self) -> None:
        if self.selected is None:
            messagebox.showinfo("没有选中", "先在右边列表里选一个模板", parent=self.root)
            return
        key = self.selected.key
        if not messagebox.askyesno("确认删除", f"删除模板 {key} 吗？（图片保留）", parent=self.root):
            return
        if templates.remove(self.selected.page, self.selected.name):
            self.status.config(text=f"已删除 {key}")
            self.selected = None
            self.template_image = None
            self.box = None
            self.refresh_templates()
            self._render()


def main() -> int:
    root = tk.Tk()
    Workbench(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
