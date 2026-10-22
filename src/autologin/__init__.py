"""AutoLogin —— 面向企业内网/校园门户的定时自动登录签到工具。

模块划分：
    config          站点配置的持久化与数据模型
    login_runner    Playwright 登录执行器（表单登录 / 会话复用 / 手动授权）
    scheduler       APScheduler 定时任务与随机抖动排程
    holiday         工作日判断（法定节假日 + 调休补班）
    gui             Tkinter 图形界面
    tray            Windows 系统托盘
    single_instance 单实例互斥锁
    paths           运行期数据目录解析
"""
from __future__ import annotations

__version__ = "2.0.0"
__all__ = ["__version__"]
