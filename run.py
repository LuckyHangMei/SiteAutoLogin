"""源码运行入口：``python run.py``（等价于 ``python -m autologin``）。

把 ``src`` 加入模块搜索路径，免去安装即可直接运行；打包时同样以本文件为入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from autologin.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
