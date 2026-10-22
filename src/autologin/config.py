"""站点配置管理：JSON 持久化、增删改查与数据模型。"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from .paths import BASE_DIR

CONFIG_FILE = os.path.join(BASE_DIR, "sites.json")


@dataclass
class SiteConfig:
    """单个站点的登录与菜单点击策略。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    url: str = ""                        # 登录页地址
    username: str = ""
    password: str = ""
    username_selector: str = "#username"
    password_selector: str = "#password"
    submit_selector: str = "button[type=submit]"
    # 菜单点击策略：按顺序执行的 CSS 选择器列表
    menu_clicks: list[str] = field(default_factory=list)
    delay_between_clicks: float = 2.0    # 菜单之间等待秒数
    headless: bool = True
    schedule_time: str = "09:00"         # 格式 HH:MM
    jitter_minutes: int = 0              # 随机抖动分钟数(±)，0=精确时刻
    skip_holidays: bool = True           # 节假日(法定放假+周末)跳过，调休补班日仍执行
    enabled: bool = True
    # 运行状态记录（不属于策略，仅记录）
    last_run: Optional[str] = None
    last_status: Optional[str] = None    # "success" / "failed: ..."
    last_message: Optional[str] = None

    def validate(self) -> Optional[str]:
        """返回错误信息，None 表示通过。"""
        if not self.name.strip():
            return "名称不能为空"
        if not self.url.strip():
            return "网址不能为空"
        if not self.username_selector.strip() or not self.password_selector.strip() or not self.submit_selector.strip():
            return "用户名/密码/提交按钮选择器不能为空"
        if len(self.schedule_time) != 5 or self.schedule_time[2] != ":":
            return "定时格式须为 HH:MM"
        if self.jitter_minutes < 0 or self.jitter_minutes > 1440:
            return "随机抖动分钟数须在 0~1440 之间"
        return None


def load_sites() -> list[SiteConfig]:
    """读取全部站点配置；文件缺失或损坏时返回空列表。"""
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    sites = []
    for item in data.get("sites", []):
        try:
            sites.append(SiteConfig(**item))
        except TypeError:
            # 跳过字段不兼容的旧记录
            continue
    return sites


def save_sites(sites: list[SiteConfig]) -> None:
    data = {"sites": [asdict(s) for s in sites]}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_site(site: SiteConfig) -> SiteConfig:
    sites = load_sites()
    sites.append(site)
    save_sites(sites)
    return site


def update_site(site: SiteConfig) -> None:
    sites = load_sites()
    for i, s in enumerate(sites):
        if s.id == site.id:
            sites[i] = site
            save_sites(sites)
            return
    raise ValueError(f"未找到站点 id={site.id}")


def delete_site(site_id: str) -> None:
    sites = load_sites()
    sites = [s for s in sites if s.id != site_id]
    save_sites(sites)
