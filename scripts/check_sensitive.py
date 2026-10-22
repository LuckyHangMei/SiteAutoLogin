#!/usr/bin/env python3
"""提交前敏感信息自检。

扫描 Git 已跟踪的文件，命中高危模式时以非零码退出，可直接用于 pre-commit。

用法::

    python scripts/check_sensitive.py            # 扫描已跟踪文件
    python scripts/check_sensitive.py --all      # 连同未跟踪文件一起扫描
    python scripts/check_sensitive.py path ...   # 只扫描指定路径

设计取舍：
  * 私钥、云厂商令牌、真实内网 IP、真实邮箱、带用户名的绝对路径 → 一律报错；
  * "password = ..." 这类字面量只在 tests/ 与 data/ 之外报错，因为测试里本来就
    需要假的账号密码；测试目录仍会参与上面的高危模式检查。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# 文本文件才需要扫描内容；其余按二进制跳过
TEXT_SUFFIXES = {
    ".py", ".toml", ".txt", ".md", ".json", ".spec", ".cfg", ".ini",
    ".yml", ".yaml", ".ps1", ".bat", ".cmd", ".sh", ".editorconfig",
    ".gitignore", ".gitattributes", ".env", ".example",
}

# 任何位置命中都要报错
HARD_PATTERNS = [
    ("私钥块", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub Token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("Slack Token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("内网 IP", re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")),
    ("真实邮箱", re.compile(r"\b[\w.+-]+@(?!example\.|localhost)[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")),
    # 源码中该路径常以转义或原始字符串书写，故允许出现连续反斜杠
    ("含用户名的绝对路径", re.compile(r"\b[A-Za-z]:[\\/]+(?:Users|Documents and Settings)[\\/]+(?!<)[^\\/\s\"']+")),
]

# 仅在非测试/非示例数据文件中报错
CREDENTIAL_PATTERNS = [
    ("硬编码凭据", re.compile(
        r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)"
        r"\s*[:=]\s*[\"']([^\"'\s]{3,})[\"']"
    )),
]

# 明显是占位符或测试数据的值，不算泄露
PLACEHOLDER = re.compile(
    r"(?i)^(?:$|<.*>|\*+|x+|\.\.\.|"
    r"test[-_].*|example.*|dummy.*|fake.*|sample.*|placeholder.*|"
    r"old|new|changeme|your[-_].*|redacted|secret|token|password|"
    r"[\u4e00-\u9fff].*)$"
)

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "build", "dist", ".pytest_cache", ".ruff_cache"}


def tracked_files() -> "list[Path]":
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], check=True, capture_output=True
        ).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.CalledProcessError):
        return []
    return [Path(p) for p in out.split("\0") if p]


def untracked_files() -> "list[Path]":
    files = []
    for path in Path(".").rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path not in files:
            files.append(path)
    return files


def is_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    if path.name in {".gitignore", ".editorconfig", ".gitattributes"}:
        return True
    try:
        chunk = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\0" not in chunk


def scan(path: Path) -> "list[tuple[int, str, str]]":
    """返回 [(行号, 类型, 命中片段)]。"""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    in_tests = "tests" in path.parts or "data" in path.parts
    findings = []
    for number, line in enumerate(lines, 1):
        for label, pattern in HARD_PATTERNS:
            for match in pattern.finditer(line):
                findings.append((number, label, match.group(0)[:80]))
        if not in_tests:
            for label, pattern in CREDENTIAL_PATTERNS:
                for match in pattern.finditer(line):
                    value = match.group(1)
                    if PLACEHOLDER.match(value):
                        continue
                    findings.append((number, label, match.group(0)[:80]))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描仓库中的敏感信息")
    parser.add_argument("paths", nargs="*", help="只扫描指定路径")
    parser.add_argument("--all", action="store_true", help="连同未跟踪文件一起扫描")
    args = parser.parse_args()

    if args.paths:
        targets = [Path(p) for p in args.paths]
    elif args.all:
        targets = untracked_files()
    else:
        targets = tracked_files()

    problems = 0
    for path in targets:
        if not path.is_file() or not is_text(path):
            continue
        for number, label, snippet in scan(path):
            problems += 1
            print(f"{path}:{number}: [{label}] {snippet}")

    if problems:
        print(f"\n发现 {problems} 处可疑内容，请确认后再提交。", file=sys.stderr)
        return 1
    print(f"已检查 {len(targets)} 个文件，未发现敏感信息。")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - 极老的 Python
            pass
    sys.exit(main())
