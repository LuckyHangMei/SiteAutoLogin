"""Tkinter 图形界面：站点管理、立即执行、日志显示、托盘最小化。"""
from __future__ import annotations

import copy
import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from . import config
from .config import SiteConfig
from .login_runner import run_site
from .scheduler import Scheduler


class SiteEditorDialog(tk.Toplevel):
    """新增 / 编辑站点的对话框。"""

    def __init__(self, parent, site: Optional[SiteConfig] = None, title: Optional[str] = None):
        super().__init__(parent)
        self.title(title or ("编辑站点" if site else "新增站点"))
        self.geometry("520x620")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        # 工作副本：编辑时不影响主列表
        self.result: Optional[SiteConfig] = None
        self.site = site if site else SiteConfig()

        self._build()
        self._load()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        form = ttk.Frame(self)
        form.pack(fill="both", expand=True, padx=10, pady=10)

        self._entries: dict[str, tk.Entry] = {}

        def add_entry(row: int, label: str, key: str) -> tk.Entry:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="e", **pad)
            e = ttk.Entry(form, width=40)
            e.grid(row=row, column=1, sticky="we", **pad)
            self._entries[key] = e
            return e

        add_entry(0, "名称 *", "name")
        add_entry(1, "登录页网址 *", "url")
        add_entry(2, "用户名", "username")
        ttk.Label(form, text="密码").grid(row=3, column=0, sticky="e", **pad)
        password_row = ttk.Frame(form)
        password_row.grid(row=3, column=1, sticky="we", **pad)
        password_entry = ttk.Entry(password_row, width=28, show="*")
        self._entries["password"] = password_entry
        self.show_password_var = tk.BooleanVar(master=self, value=False)
        ttk.Checkbutton(
            password_row,
            text="显示密码",
            variable=self.show_password_var,
            command=lambda: password_entry.configure(
                show="" if self.show_password_var.get() else "*"
            ),
        ).pack(side="right", padx=(8, 0))
        password_entry.pack(side="left", fill="x", expand=True)
        add_entry(4, "用户名选择器 *", "username_selector")
        add_entry(5, "密码选择器 *", "password_selector")
        add_entry(6, "提交按钮选择器 *", "submit_selector")
        add_entry(7, "菜单间等待(秒)", "delay_between_clicks")
        add_entry(8, "每天定时(HH:MM)", "schedule_time")
        add_entry(9, "随机抖动分钟(±)", "jitter_minutes")

        # 菜单点击策略：每行一个 CSS 选择器
        ttk.Label(form, text="菜单点击策略").grid(row=10, column=0, sticky="ne", **pad)
        self.menu_text = tk.Text(form, width=40, height=8, undo=True)
        self.menu_text.grid(row=10, column=1, sticky="we", **pad)
        ttk.Label(form, text="每行一个 CSS 选择器，按顺序点击").grid(
            row=11, column=1, sticky="w", **pad
        )

        # 无头模式
        self.headless_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="无头模式(不显示浏览器窗口)", variable=self.headless_var).grid(
            row=12, column=1, sticky="w", **pad
        )
        # 节假日跳过
        self.skip_holidays_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            form,
            text="节假日跳过(法定放假+周末不执行，调休补班日仍执行)",
            variable=self.skip_holidays_var,
        ).grid(row=13, column=1, sticky="w", **pad)
        # 启用
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="启用定时执行", variable=self.enabled_var).grid(
            row=14, column=1, sticky="w", **pad
        )

        form.columnconfigure(1, weight=1)

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=8)
        ttk.Button(btns, text="保存", command=self._on_save).pack(side="right", padx=4)
        ttk.Button(btns, text="取消", command=self.destroy).pack(side="right", padx=4)

    def _load(self) -> None:
        s = self.site
        self._entries["name"].insert(0, s.name)
        self._entries["url"].insert(0, s.url)
        self._entries["username"].insert(0, s.username)
        self._entries["password"].insert(0, s.password)
        self._entries["username_selector"].insert(0, s.username_selector)
        self._entries["password_selector"].insert(0, s.password_selector)
        self._entries["submit_selector"].insert(0, s.submit_selector)
        self._entries["delay_between_clicks"].insert(0, str(s.delay_between_clicks))
        self._entries["schedule_time"].insert(0, s.schedule_time)
        self._entries["jitter_minutes"].insert(0, str(s.jitter_minutes))
        self.headless_var.set(s.headless)
        self.skip_holidays_var.set(s.skip_holidays)
        self.enabled_var.set(s.enabled)
        if s.menu_clicks:
            self.menu_text.insert("1.0", "\n".join(s.menu_clicks))

    def _collect(self) -> Optional[SiteConfig]:
        s = self.site
        s.name = self._entries["name"].get().strip()
        s.url = self._entries["url"].get().strip()
        s.username = self._entries["username"].get()
        s.password = self._entries["password"].get()
        s.username_selector = self._entries["username_selector"].get().strip()
        s.password_selector = self._entries["password_selector"].get().strip()
        s.submit_selector = self._entries["submit_selector"].get().strip()
        try:
            s.delay_between_clicks = float(self._entries["delay_between_clicks"].get() or 2.0)
        except ValueError:
            messagebox.showerror("错误", "菜单间等待秒数须为数字")
            return None
        s.schedule_time = self._entries["schedule_time"].get().strip()
        try:
            s.jitter_minutes = int(self._entries["jitter_minutes"].get() or 0)
        except ValueError:
            messagebox.showerror("错误", "随机抖动分钟须为整数")
            return None
        s.headless = self.headless_var.get()
        s.skip_holidays = self.skip_holidays_var.get()
        s.enabled = self.enabled_var.get()

        raw = self.menu_text.get("1.0", "end-1c")
        s.menu_clicks = [ln.strip() for ln in raw.splitlines() if ln.strip()]

        err = s.validate()
        if err:
            messagebox.showerror("校验失败", err)
            return None
        return s

    def _on_save(self) -> None:
        collected = self._collect()
        if collected is None:
            return
        self.result = collected
        self.destroy()


class App:
    """主窗口。"""

    COLUMNS = ("name", "url", "schedule_time", "enabled", "last_run", "last_status")

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.tray = None
        self._closing = False
        self._window_state = "normal"
        self._tray_actions = queue.SimpleQueue()
        self._tray_poll = None
        root.title("自动登录工具")
        root.geometry("900x600")
        root.minsize(800, 480)

        self.scheduler = Scheduler(
            on_progress=self._on_log_threadsafe,
            on_complete=lambda: self.root.after(0, self._refresh_list),
        )

        self._build()
        self._refresh_list()
        self.scheduler.start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.bind("<Unmap>", self._on_unmap, add="+")
        root.bind("<Configure>", self._remember_window_state, add="+")
        root.bind("<Destroy>", self._on_destroy, add="+")
        self._setup_tray()

    def _build(self) -> None:
        # 顶部按钮栏
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Button(top, text="新增", command=self._on_add).pack(side="left", padx=2)
        ttk.Button(top, text="复制", command=self._on_copy).pack(side="left", padx=2)
        ttk.Button(top, text="编辑", command=self._on_edit).pack(side="left", padx=2)
        ttk.Button(top, text="删除", command=self._on_delete).pack(side="left", padx=2)
        ttk.Button(top, text="授权", command=self._on_authorize).pack(side="left", padx=2)
        ttk.Button(top, text="立即执行", command=self._on_run_now).pack(side="left", padx=2)
        ttk.Button(top, text="刷新", command=self._refresh_list).pack(side="left", padx=2)
        ttk.Button(top, text="重载调度", command=self._on_reload).pack(side="left", padx=2)

        # 中部列表
        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, padx=8, pady=4)
        self.tree = ttk.Treeview(mid, columns=self.COLUMNS, show="headings", height=14)
        labels = {
            "name": "名称",
            "url": "网址",
            "schedule_time": "定时",
            "enabled": "启用",
            "last_run": "上次运行",
            "last_status": "状态",
        }
        for col in self.COLUMNS:
            self.tree.heading(col, text=labels[col])
        self.tree.column("name", width=120)
        self.tree.column("url", width=280)
        self.tree.column("schedule_time", width=70, anchor="center")
        self.tree.column("enabled", width=50, anchor="center")
        self.tree.column("last_run", width=150, anchor="center")
        self.tree.column("last_status", width=120, anchor="center")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 底部日志
        log_header = ttk.Frame(self.root)
        log_header.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(log_header, text="执行日志").pack(side="left", padx=2)
        ttk.Button(log_header, text="退出", command=self._on_exit).pack(side="right", padx=2)
        ttk.Button(log_header, text="最小化到托盘", command=self._hide_to_tray).pack(side="right", padx=2)
        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=False, padx=8, pady=(0, 8))
        self.log_text = tk.Text(log_frame, height=10, state="disabled")
        hsb = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        vsb2 = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(xscrollcommand=hsb.set, yscrollcommand=vsb2.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        vsb2.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")

    # ----- 列表数据 -----
    def _refresh_list(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for s in config.load_sites():
            self.tree.insert(
                "", "end",
                iid=s.id,
                values=(
                    s.name,
                    s.url,
                    s.schedule_time,
                    "是" if s.enabled else "否",
                    s.last_run or "",
                    s.last_status or "",
                ),
            )

    def _selected_site_id(self) -> Optional[str]:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def _selected_site(self) -> Optional[SiteConfig]:
        site_id = self._selected_site_id()
        if not site_id:
            messagebox.showinfo("提示", "请先选择一个站点")
            return None
        sites = config.load_sites()
        return next((s for s in sites if s.id == site_id), None)

    # ----- 事件 -----
    def _on_add(self) -> None:
        dlg = SiteEditorDialog(self.root, site=None)
        self.root.wait_window(dlg)
        if dlg.result:
            config.add_site(dlg.result)
            self.scheduler.upsert(dlg.result)
            self._refresh_list()
            self._log(f"已新增站点: {dlg.result.name}")

    def _on_edit(self) -> None:
        site = self._selected_site()
        if not site:
            return
        dlg = SiteEditorDialog(self.root, site=site)
        self.root.wait_window(dlg)
        if dlg.result:
            config.update_site(dlg.result)
            self.scheduler.upsert(dlg.result)
            self._refresh_list()
            self._log(f"已更新站点: {dlg.result.name}")

    def _on_copy(self) -> None:
        """复制选中站点：保留选择器和菜单策略，仅换网址/账号/密码即可用于同框架系统。"""
        site = self._selected_site()
        if not site:
            return
        dup = copy.deepcopy(site)
        dup.id = SiteConfig().id           # 生成新 id
        dup.name = site.name + " 副本"
        dup.last_run = None                 # 复制后清空运行状态
        dup.last_status = None
        dup.last_message = None
        dlg = SiteEditorDialog(self.root, site=dup, title="复制站点")
        self.root.wait_window(dlg)
        if dlg.result:
            config.add_site(dlg.result)
            self.scheduler.upsert(dlg.result)
            self._refresh_list()
            self._log(f"已复制站点: {dlg.result.name}（改网址/账号/密码后保存即可）")

    def _on_delete(self) -> None:
        site_id = self._selected_site_id()
        if not site_id:
            messagebox.showinfo("提示", "请先选择一个站点")
            return
        if not messagebox.askyesno("确认", "确定删除该站点配置？"):
            return
        self.scheduler.remove(site_id)
        config.delete_site(site_id)
        self._refresh_list()
        self._log("已删除站点")

    def _on_run_now(self) -> None:
        site = self._selected_site()
        if not site:
            return
        # 后台线程执行，避免界面卡死
        self._log(f"[{site.name}] 手动触发执行…")
        threading.Thread(target=self._run_in_background, args=(site,), daemon=True).start()

    def _run_in_background(self, site: SiteConfig) -> None:
        ok, msg = run_site(site, on_progress=lambda m: self._on_log_threadsafe(site.name, m))
        try:
            config.update_site(site)
        except ValueError:
            pass
        self.root.after(0, self._refresh_list)

    def _on_authorize(self) -> None:
        """打开可见浏览器手动登录(含验证码)，成功后保存会话供日常免登录执行。"""
        site = self._selected_site()
        if not site:
            return
        self._log(f"[{site.name}] 打开浏览器进行授权登录（请在窗口中手动完成，含验证码）…")
        threading.Thread(
            target=self._authorize_in_background, args=(site,), daemon=True
        ).start()

    def _authorize_in_background(self, site: SiteConfig) -> None:
        from .login_runner import authorize_site
        ok, msg = authorize_site(site, on_progress=lambda m: self._on_log_threadsafe(site.name, m))
        try:
            config.update_site(site)
        except ValueError:
            pass
        self.root.after(0, self._refresh_list)

    def _on_reload(self) -> None:
        self.scheduler.reload_all()
        self._refresh_list()
        self._log("调度已重新载入")

    # ----- 日志 -----
    def _on_log_threadsafe(self, site_name: str, message: str) -> None:
        self.root.after(0, lambda: self._log(f"[{site_name}] {message}"))

    def _log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ----- 托盘与关闭 -----
    def _setup_tray(self) -> None:
        try:
            from .tray import ICON_PATH, TrayIcon
            self.root.iconbitmap(default=str(ICON_PATH))
            self.tray = TrayIcon(
                on_show=lambda: self._tray_actions.put("show"),
                on_exit=lambda: self._tray_actions.put("exit"),
            )
        except Exception:
            logging.getLogger("auto_login").exception("系统托盘初始化失败")
            self._log("托盘不可用：最小化仍留在任务栏，关闭窗口会退出程序。")
        else:
            self._log("最小化或关闭窗口后，定时任务继续运行。彻底退出请使用“退出”按钮或托盘菜单。")
            self._tray_poll = self.root.after(100, self._poll_tray)

    def _poll_tray(self) -> None:
        # 原生窗口回调不能重入 Tcl，即使它与 Tk 位于同一个线程。
        self._tray_poll = None
        while not self._closing:
            try:
                action = self._tray_actions.get_nowait()
            except queue.Empty:
                self._tray_poll = self.root.after(100, self._poll_tray)
                return
            if action == "exit":
                self._on_exit()
                return
            self._show_window()

    def _remember_window_state(self, event) -> None:
        if event.widget is self.root and self.root.state() in ("normal", "zoomed"):
            self._window_state = self.root.state()

    def _on_unmap(self, event) -> None:
        if event.widget is self.root and self.root.state() == "iconic" and self.tray:
            self._hide_to_tray()

    def _hide_to_tray(self) -> None:
        if self._closing:
            return
        try:
            if self.tray is None:
                raise OSError("系统托盘不可用")
            self.tray.show()
        except OSError:
            logging.getLogger("auto_login").exception("无法最小化到托盘")
            self._show_window()
            messagebox.showwarning("托盘不可用", "无法创建托盘图标，窗口已保留。", parent=self.root)
            return
        self.root.withdraw()

    def _show_window(self) -> None:
        if self._closing:
            return
        self.root.deiconify()
        self.root.state(self._window_state)
        self.root.lift()
        self.root.focus_force()
        dialog = self.root.grab_current()
        if dialog is not None:
            dialog.lift()
            dialog.focus_force()

    def _on_close(self) -> None:
        if self.tray is not None:
            self._hide_to_tray()
        else:
            self._on_exit()

    def _on_exit(self) -> None:
        if not self._closing:
            self.root.destroy()

    def _on_destroy(self, event) -> None:
        if event.widget is not self.root or self._closing:
            return
        self._closing = True
        if self._tray_poll is not None:
            self.root.after_cancel(self._tray_poll)
            self._tray_poll = None
        try:
            self.scheduler.shutdown()
        except Exception:
            logging.getLogger("auto_login").exception("停止调度器失败")
        finally:
            if self.tray is not None:
                self.tray.close()
                self.tray = None


def run() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
