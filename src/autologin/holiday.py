"""节假日判断：基于本地 holidays.json 判断某日是否为工作日。

规则：
  - 周末(周六/周日)默认非工作日
  - holidays 列表中的日期 → 强制非工作日(法定节假日放假)
  - workdays 列表中的日期 → 强制工作日(周末调休补班)
  - 文件缺失或为空时退化为"仅周末判断"

holidays.json 结构：
  {"holidays": ["2026-10-01", ...], "workdays": ["2026-10-10", ...]}
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta

from .paths import BASE_DIR

log = logging.getLogger("auto_login")

HOLIDAYS_FILE = os.path.join(BASE_DIR, "holidays.json")


def _load() -> tuple[set[str], set[str]]:
    """加载节假日/调休日集合，失败返回空集。"""
    if not os.path.exists(HOLIDAYS_FILE):
        return set(), set()
    try:
        with open(HOLIDAYS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        holidays = {d.strip() for d in data.get("holidays", []) if d.strip()}
        workdays = {d.strip() for d in data.get("workdays", []) if d.strip()}
        return holidays, workdays
    except Exception as e:
        log.warning("加载 holidays.json 失败: %s", e)
        return set(), set()


def is_workday(d: date) -> bool:
    """判断给定日期是否为工作日(考虑节假日和调休补班)。"""
    ds = d.strftime("%Y-%m-%d")
    holidays, workdays = _load()
    # 调休补班日：周末但强制上班
    if ds in workdays:
        return True
    # 法定节假日：即使是工作日也放假
    if ds in holidays:
        return False
    # 默认按周末判断(周一=0 ... 周日=6)
    return d.weekday() < 5


def is_workday_now() -> bool:
    """今天是否为工作日。"""
    return is_workday(date.today())


def next_workday(d: date) -> date:
    """从给定日期起，找下一个工作日(不含当天)。"""
    cur = d + timedelta(days=1)
    while not is_workday(cur):
        cur += timedelta(days=1)
    return cur


def describe_today() -> str:
    """返回今天的工作日状态描述，用于日志。"""
    ds = date.today().strftime("%Y-%m-%d")
    holidays, workdays = _load()
    if ds in holidays:
        return f"今日 {ds} 为法定节假日，跳过执行"
    if ds in workdays:
        return f"今日 {ds} 为周末调休补班日，正常执行"
    if is_workday_now():
        return f"今日 {ds} 为工作日，正常执行"
    return f"今日 {ds} 为周末，跳过执行"
