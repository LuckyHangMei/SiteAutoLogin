"""AutoLogin 程序入口。

用法::

    python -m autologin                    启动图形界面
    python -m autologin --install          安装 Playwright 浏览器内核（首次使用前执行一次）
    python -m autologin --version          打印版本号
    python -m autologin --run-all          不开界面，执行全部启用站点后退出（适合任务计划程序）
    python -m autologin --run 名称 [名称…]  只执行指定站点
"""
from __future__ import annotations

import atexit
import logging
import os
import sys


def setup_logging() -> None:
    """把日志同时写入数据目录下的 auto_login.log（源码运行时再输出到控制台）。"""
    from .paths import ensure_data_dir

    log_path = os.path.join(str(ensure_data_dir()), "auto_login.log")
    handlers: list[logging.Handler] = [logging.FileHandler(log_path, encoding="utf-8")]
    # 打包成无控制台 exe 时 stdout 不可用，仅在非 frozen 模式下输出到控制台
    if not getattr(sys, "frozen", False):
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def _install_browsers() -> None:
    """安装 Playwright Chromium 内核。

    打包后 ``sys.executable`` 是 exe 本身，不能再走 ``python -m playwright``；
    此时直接调用随包分发的 driver（node.exe + cli.js）。
    """
    import subprocess

    if getattr(sys, "frozen", False):
        from playwright._impl._driver import compute_driver_executable

        result = compute_driver_executable()
        parts = result if isinstance(result, tuple) else (result,)
        subprocess.run([str(part) for part in parts if part] + ["install", "chromium"], check=True)
    else:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


def _say(text: str) -> None:
    """无控制台的窗口版 exe 里 stdout 可能不存在，输出失败不应影响流程。"""
    try:
        print(text, flush=True)
    except Exception:  # noqa: BLE001 - 仅用于兼容无控制台环境
        pass


def _run_cli(names: list[str]) -> int:
    """不启动界面，直接执行站点并返回退出码（0 全部成功 / 1 有失败 / 2 无匹配）。"""
    from .config import load_sites, update_site
    from .login_runner import run_site

    sites = load_sites()
    if names:
        wanted = [s for s in sites if s.name in names or s.id in names]
    else:
        wanted = [s for s in sites if s.enabled]

    if not wanted:
        _say("没有匹配的站点，请先在界面里添加，或用 --run 指定站点名称。")
        return 2

    failed = 0
    for site in wanted:
        ok, msg = run_site(site)
        _say(f"[{site.name}] {'成功' if ok else '失败'}: {msg}")
        try:
            update_site(site)
        except ValueError:
            pass
        failed += 0 if ok else 1
    return 0 if failed == 0 else 1


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if "--version" in args:
        from . import __version__
        _say(__version__)
        return 0

    if "--install" in args:
        setup_logging()
        _install_browsers()
        _say("Playwright 浏览器内核已就绪。")
        return 0

    if "--run-all" in args or "--run" in args:
        setup_logging()
        names: list[str] = []
        if "--run" in args:
            index = args.index("--run") + 1
            names = args[index:] if index < len(args) else []
        return _run_cli(names)

    from .single_instance import InstanceLock, activate_existing

    instance = InstanceLock()
    if not instance.acquired:
        # 已有实例在运行：把它唤到前台，本进程直接退出
        activate_existing()
        return 0
    # 等待后台线程收尾后才释放，避免窗口已关但任务尚未结束时启动第二个实例。
    atexit.register(instance.close)
    setup_logging()
    from .gui import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
