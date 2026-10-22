"""调度器：基于 APScheduler 的每日定时登录任务管理。

定时策略模拟人类使用习惯：不固定在精确时刻，而是在基准时间 ±jitter_minutes
分钟内每天随机选一个时刻执行，每天不同。每个任务只排一次(DateTrigger)，
执行结束后自动续排下一个工作日。
"""
from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from . import config
from .config import SiteConfig
from .holiday import describe_today, is_workday, next_workday
from .login_runner import run_site

log = logging.getLogger("auto_login")

_JOB_PREFIX = "site_"  # job_id 前缀，避免与其它任务冲突


class Scheduler:
    def __init__(
        self,
        on_progress: Optional[Callable[[str, str], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
    ):
        # on_progress: (site_name, message) 回调，供 GUI 显示日志
        # on_complete: 一次定时任务成功写回配置后触发，供 GUI 刷新列表
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self._tz = self._scheduler.timezone
        self._on_progress = on_progress
        self._on_complete = on_complete

    @staticmethod
    def _job_id(site: SiteConfig) -> str:
        return f"{_JOB_PREFIX}{site.id}"

    def _run_job(self, site_id: str) -> None:
        """从配置加载最新站点信息并执行；执行后自动排程下一次(随机时刻)。"""
        try:
            sites = config.load_sites()
            site = next((s for s in sites if s.id == site_id), None)
            if site is None:
                log.warning("调度执行时找不到站点 id=%s，不再排程", site_id)
                return
            if not site.enabled:
                log.info("站点 %s 已禁用，跳过且不再排程", site.name)
                return

            # 节假日跳过：若启用 skip_holidays 且今日非工作日，则跳过执行
            if site.skip_holidays and not is_workday(date.today()):
                log.info("[%s] %s，跳过本次执行", site.name, describe_today())
                if self._on_progress:
                    self._on_progress(site.name, describe_today())
                return

            def emit(msg: str) -> None:
                if self._on_progress:
                    self._on_progress(site.name, msg)

            ok, msg = run_site(site, on_progress=emit)
            try:
                config.update_site(site)
            except ValueError:
                log.error("写回站点状态失败：找不到 id=%s", site_id)
            else:
                if self._on_complete:
                    self._on_complete()
        finally:
            # 无论成功失败，都为下一个工作日排一个随机时刻(除非站点被删/禁用)
            try:
                fresh = next(
                    (s for s in config.load_sites() if s.id == site_id), None
                )
                if fresh and fresh.enabled:
                    self._schedule_next(fresh)
            except Exception as e:  # noqa: BLE001
                log.error("重新排程失败 id=%s: %s", site_id, e)

    def _next_fire_time(self, site: SiteConfig) -> Optional[datetime]:
        """计算下次执行时刻：今天基准时间 ±jitter 随机偏移，若已过则顺延到明天。

        若站点启用 skip_holidays，则跳过节假日(法定放假+普通周末)，
        排到下一个工作日；调休补班日仍正常执行。
        """
        try:
            hour_s, minute_s = site.schedule_time.split(":")
            hour, minute = int(hour_s), int(minute_s)
        except (ValueError, AttributeError):
            log.error("站点 %s 定时格式非法: %s", site.name, site.schedule_time)
            return None

        jitter = max(0, int(site.jitter_minutes or 0))
        offset = random.randint(-jitter, jitter) if jitter > 0 else 0

        now = datetime.now(self._tz)
        # 确定候选日期：今天还是明天
        base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        target = base + timedelta(minutes=offset)
        if target <= now:
            target += timedelta(days=1)

        # 节假日跳过：若候选日是非工作日，顺延到下一个工作日
        if site.skip_holidays:
            cand_date = target.date()
            while not is_workday(cand_date):
                cand_date = next_workday(cand_date)
                # 把目标日期改到该工作日，保留时分
                target = target.replace(year=cand_date.year, month=cand_date.month, day=cand_date.day)
        return target

    def _schedule_next(self, site: SiteConfig) -> None:
        """为站点排程下一次执行(单次 DateTrigger，跑完自动续排)。"""
        # 已存在的同 id 任务先清掉
        existing = self._scheduler.get_job(self._job_id(site))
        if existing:
            self._scheduler.remove_job(existing.id)

        if not site.enabled:
            return

        target = self._next_fire_time(site)
        if target is None:
            return

        self._scheduler.add_job(
            self._run_job,
            trigger=DateTrigger(run_date=target, timezone=self._tz),
            args=[site.id],
            id=self._job_id(site),
            name=f"{site.name} @ {site.schedule_time}±{site.jitter_minutes}m",
            replace_existing=True,
            misfire_grace_time=600,
        )
        log.info(
            "已排程 %s 下次执行: %s",
            site.name,
            target.strftime("%Y-%m-%d %H:%M"),
        )

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            log.info("调度器已启动")
            self.reload_all()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("调度器已停止")

    def reload_all(self) -> None:
        """根据当前配置全量重建任务。"""
        for job in list(self._scheduler.get_jobs()):
            if job.id.startswith(_JOB_PREFIX):
                self._scheduler.remove_job(job.id)

        sites = config.load_sites()
        for site in sites:
            self._schedule_next(site)
        log.info("已载入 %d 个站点任务", len(sites))

    def upsert(self, site: SiteConfig) -> None:
        """新增或更新单个站点任务。"""
        self._schedule_next(site)

    def remove(self, site_id: str) -> None:
        job_id = f"{_JOB_PREFIX}{site_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            log.info("已移除任务: %s", job_id)
