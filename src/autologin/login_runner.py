"""登录执行器：使用 Playwright 完成登录并按策略点击菜单。

支持会话持久化：优先复用已保存会话，过期后用账号密码重新登录。
需要验证码时可用 ``authorize_site`` 手动授权，成功后更新保存的会话。
所有路径都会校验是否真正登录成功（URL 离开登录页），避免"假成功"。
"""
from __future__ import annotations

import logging
import os
import random
import traceback
from datetime import datetime
from typing import Callable, Optional

from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

from .config import BASE_DIR, SiteConfig

log = logging.getLogger("auto_login")


def session_path(site_id: str) -> str:
    """该站点已保存会话(cookie/localStorage)的文件路径。"""
    return os.path.join(BASE_DIR, f"session_{site_id}.json")


def _launch_browser(p, site: SiteConfig, emit, *, headless: Optional[bool] = None):
    """启动浏览器：依次尝试 下载的 Chromium → 系统 Edge → 系统 Chrome。

    headless 为 None 时用 site.headless；authorize 场景可强制 False(可见)。
    """
    headless = site.headless if headless is None else headless
    candidates = [None, "msedge", "chrome"]
    last_err: Exception | None = None
    for ch in candidates:
        label = ch or "chromium(下载)"
        try:
            if ch:
                browser = p.chromium.launch(headless=headless, channel=ch)
            else:
                browser = p.chromium.launch(headless=headless)
            emit(f"浏览器就绪：{label}")
            return browser
        except Exception as e:
            last_err = e
            log.info("[%s] 浏览器 %s 启动失败: %s", site.name, label, e)
    raise RuntimeError(f"无可用浏览器（已尝试 chromium/msedge/chrome）: {last_err}")


def _logged_in(page) -> bool:
    """判断是否已离开登录页(登录成功的可靠信号)。"""
    try:
        return "/login" not in page.url
    except Exception:
        return False


def _click_menus(page, site: SiteConfig, emit) -> None:
    """按策略顺序点击菜单。"""
    if not site.menu_clicks:
        return
    for idx, selector in enumerate(site.menu_clicks, 1):
        try:
            page.wait_for_selector(selector, state="visible", timeout=15_000)
            page.click(selector, timeout=15_000)
            emit(f"已点击菜单 {idx}/{len(site.menu_clicks)}：{selector}")
        except PWTimeout:
            emit(f"菜单不可点击或不可见：{selector}（跳过）")
        except Exception as e:
            emit(f"点击菜单出错 {selector}: {e}（跳过）")
        if idx < len(site.menu_clicks):
            # 菜单间隔加 ±30% 随机抖动，模拟人类点击节奏
            wait_ms = int(site.delay_between_clicks * random.uniform(0.7, 1.3) * 1000)
            page.wait_for_timeout(wait_ms)


def _mark(site: SiteConfig, status: str, message: str) -> None:
    """记录本次运行结果（由调用方负责写回配置）。"""
    site.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    site.last_status = status
    site.last_message = message


def authorize_site(site: SiteConfig, on_progress: Optional[Callable[[str], None]] = None) -> tuple[bool, str]:
    """打开可见浏览器让用户手动登录(含滑块验证码)，成功后保存会话。

    适用于带验证码、无法自动登录的站点。之后 run_site 会复用此会话免登录。
    """
    def emit(msg: str) -> None:
        log.info("[%s] %s", site.name, msg)
        if on_progress:
            on_progress(msg)

    emit("正在打开浏览器，请在窗口中手动登录（含滑块验证码）...")
    try:
        with sync_playwright() as p:
            browser = _launch_browser(p, site, emit, headless=False)  # 强制可见
            context = browser.new_context()
            page = context.new_page()
            page.goto(site.url, wait_until="domcontentloaded", timeout=30_000)
            emit(f"登录页已打开：{site.url}（请在浏览器中完成登录）")

            # 轮询最多 5 分钟，等待用户完成登录(URL 离开 /login)
            for _ in range(300):
                page.wait_for_timeout(1000)
                if _logged_in(page):
                    break
            else:
                browser.close()
                msg = "授权超时：5 分钟内未完成登录"
                _mark(site, "failed", msg)
                emit(msg)
                return False, msg

            page.wait_for_timeout(3000)  # 等首页菜单加载
            sp = session_path(site.id)
            context.storage_state(path=sp)
            browser.close()

            msg = "授权成功，会话已保存"
            _mark(site, "success", msg)
            emit(f"{msg}：{sp}")
            return True, msg
    except Exception as e:
        err = f"授权失败: {e}"
        _mark(site, "failed", err)
        log.error("[%s] %s\n%s", site.name, err, traceback.format_exc())
        emit(err)
        return False, err


def run_site(site: SiteConfig, on_progress: Optional[Callable[[str], None]] = None) -> tuple[bool, str]:
    """对单个站点执行登录 + 菜单点击，返回 (是否成功, 消息)。

    优先使用已保存会话免登录；无会话或会话过期则用账号密码登录。
    两条路径都会校验是否真正登录成功，避免"假成功"。
    """
    def emit(msg: str) -> None:
        log.info("[%s] %s", site.name, msg)
        if on_progress:
            on_progress(msg)

    emit(f"开始执行：{site.url}")
    try:
        with sync_playwright() as p:
            browser = _launch_browser(p, site, emit)
            sp = session_path(site.id)
            use_session = os.path.exists(sp)

            context = browser.new_context(storage_state=sp) if use_session else browser.new_context()
            page = context.new_page()
            page.goto(site.url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2000)

            if _logged_in(page):
                emit("已免登录进入")
            else:
                if use_session:
                    emit("保存的会话已失效，尝试使用已保存的账号密码重新登录")
                else:
                    emit("登录页已加载")
                if not site.username or not site.password:
                    context.close()
                    browser.close()
                    raise RuntimeError("缺少账号或密码，请编辑站点填写凭据，或点『授权』手动登录")
                page.fill(site.username_selector, site.username, timeout=15_000)
                page.fill(site.password_selector, site.password, timeout=15_000)
                emit("凭据已填写")
                page.click(site.submit_selector, timeout=15_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=30_000)
                except PWTimeout:
                    pass
                emit("登录已提交")
                page.wait_for_timeout(2000)
                if not _logged_in(page):
                    # 仍停在登录页 → 登录失败(凭据错或被验证码拦)
                    msg = "登录未成功：仍停留在登录页（凭据错误或需先『授权』过验证码）"
                    _mark(site, "failed", msg)
                    emit(msg)
                    context.close()
                    browser.close()
                    return False, msg
                emit("登录成功")

            # 复用会话时网站也可能刷新令牌，需要保存更新后的状态。
            try:
                context.storage_state(path=sp)
                emit("会话已更新，下次优先复用")
            except Exception as e:
                log.info("[%s] 保存会话失败(不致命): %s", site.name, e)

            # 菜单点击(两条路径共用)
            _click_menus(page, site, emit)

            context.close()
            browser.close()

        msg = "执行完成"
        _mark(site, "success", msg)
        emit(msg)
        return True, msg

    except Exception as e:
        err = f"失败: {e}"
        _mark(site, "failed", err)
        log.error("[%s] %s\n%s", site.name, err, traceback.format_exc())
        emit(err)
        return False, err
