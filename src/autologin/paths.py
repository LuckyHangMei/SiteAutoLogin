"""运行期数据目录解析。

`sites.json`、`session_*.json`、`holidays.json`、`auto_login.log` 都存放在
同一个数据目录里。选择顺序：

1. 环境变量 ``AUTOLOGIN_DATA_DIR``（便于测试与多套配置并存）；
2. 打包运行（PyInstaller frozen）→ 可执行文件所在目录，保持便携；
3. 源码检出（仓库根目录存在 ``pyproject.toml``）→ 仓库根目录；
4. 其它情况（已安装到 site-packages）→ ``%APPDATA%/AutoLogin``。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "AutoLogin"


def _repo_root() -> "Path | None":
    """若当前文件位于源码仓库的 src/autologin/ 下，返回仓库根目录。"""
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "pyproject.toml").is_file():
        return candidate
    return None


def resolve_data_dir() -> Path:
    """按优先级返回数据目录（不保证已存在）。"""
    override = os.environ.get("AUTOLOGIN_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    root = _repo_root()
    if root is not None:
        return root

    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / APP_NAME


def ensure_data_dir() -> Path:
    """返回数据目录并确保其存在。"""
    directory = resolve_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


BASE_DIR = str(resolve_data_dir())
