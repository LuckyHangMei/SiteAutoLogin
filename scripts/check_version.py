#!/usr/bin/env python3
"""校验版本号一致性，防止 tag 与代码里的版本号脱节。

版本号在两处重复出现，必须保持一致：

    src/autologin/__init__.py   __version__ = "2.0.0"
    pyproject.toml              [project] version = "2.0.0"

发版时还会比对 Git tag（``v2.0.0`` → ``2.0.0``）。任一不一致即以非零码退出。

用法::

    python scripts/check_version.py                 # 只比对代码内两处
    python scripts/check_version.py --tag v2.1.0    # 同时比对 tag
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT_FILE = ROOT / "src" / "autologin" / "__init__.py"
PYPROJECT_FILE = ROOT / "pyproject.toml"


def read_init_version() -> "str | None":
    text = INIT_FILE.read_text(encoding="utf-8")
    match = re.search(r"^__version__\s*=\s*[\"']([^\"']+)[\"']", text, re.MULTILINE)
    return match.group(1) if match else None


def read_pyproject_version() -> "str | None":
    """只读取 [project] 段里的 version，避免引入 TOML 解析依赖。"""
    section = None
    for line in PYPROJECT_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.strip("[]").strip()
            continue
        if section == "project":
            match = re.match(r"version\s*=\s*[\"']([^\"']+)[\"']", stripped)
            if match:
                return match.group(1)
    return None


def normalize(tag: str) -> str:
    """把 v2.0.0 / 2.0.0 统一成 2.0.0。"""
    tag = tag.strip()
    return tag[1:] if tag[:1] in ("v", "V") else tag


def main() -> int:
    parser = argparse.ArgumentParser(description="校验版本号一致性")
    parser.add_argument("--tag", default="", help="当前 Git tag，例如 v2.0.0")
    args = parser.parse_args()

    code_version = read_init_version()
    project_version = read_pyproject_version()

    if not code_version:
        print(f"无法从 {INIT_FILE} 读取 __version__", file=sys.stderr)
        return 2
    if not project_version:
        print(f"无法从 {PYPROJECT_FILE} 读取 [project].version", file=sys.stderr)
        return 2

    print(f"__version__        : {code_version}")
    print(f"pyproject [project]: {project_version}")
    if args.tag:
        print(f"tag                : {args.tag} -> {normalize(args.tag)}")

    problems = []
    if code_version != project_version:
        problems.append(
            f"两处版本号不一致：__init__.py={code_version}，pyproject.toml={project_version}"
        )
    if args.tag:
        tag_version = normalize(args.tag)
        if tag_version != code_version:
            problems.append(
                f"tag 与代码版本不一致：tag={args.tag}（{tag_version}），代码={code_version}；"
                f"请先把两处版本号改成 {tag_version} 再打 tag"
            )

    if problems:
        for problem in problems:
            print(f"✗ {problem}", file=sys.stderr)
        return 1

    print("✓ 版本号一致")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass
    sys.exit(main())
