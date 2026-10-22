"""AutoLogin 程序入口。

用法::

    python -m autologin              启动图形界面
    python -m autologin --install    安装 Playwright 浏览器内核（首次使用前执行一次）
    python -m autologin --version    打印版本号
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


def main(argv: "list[str] | None" = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if "--version" in args:
        from . import __version__
        print(__version__)
        return 0

    if "--install" in args:
        setup_logging()
        # 安装 Playwright Chromium 浏览器内核（首次使用前执行一次）
        import subprocess
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("Playwright 浏览器内核已就绪。")
        return 0

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
