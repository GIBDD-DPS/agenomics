#!/usr/bin/env python3
# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
ip_headers.py. Строка авторства в начале каждого .py файла проекта.

    python scripts/ip_headers.py --write   # проставить или обновить
    python scripts/ip_headers.py --check   # код выхода 1, если где-то нет или версия устарела

Строка собирается из IP/IP_MANIFEST.json (продукт, автор, бренд, год) и
версии из pyproject.toml, поэтому при выпуске версии её не нужно править
руками в десятках файлов. Shebang остаётся первой строкой.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEADER_RE = re.compile(r"^# \S+ \S+ \| Author: .* \| Brand: .* \| © \d{4}$")


def expected_header() -> str:
    manifest = json.loads((ROOT / "IP" / "IP_MANIFEST.json").read_text(encoding="utf-8"))
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    return (f"# {manifest['product']} {version} | Author: {manifest['author']} | "
            f"Brand: {manifest['brand']} | © {manifest['copyright_year']}")


def python_files() -> list:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line]


def _header_index(lines: list) -> int:
    return 1 if lines and lines[0].startswith("#!") else 0


def apply_header(text: str, header: str) -> str:
    lines = text.split("\n")
    i = _header_index(lines)
    if i < len(lines) and HEADER_RE.match(lines[i]):
        lines[i] = header
    else:
        lines.insert(i, header)
    return "\n".join(lines)


def has_header(text: str, header: str) -> bool:
    lines = text.split("\n")
    i = _header_index(lines)
    return i < len(lines) and lines[i] == header


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args not in (["--write"], ["--check"]):
        print(__doc__)
        return 2
    header = expected_header()
    bad = []
    for path in python_files():
        text = path.read_text(encoding="utf-8")
        if has_header(text, header):
            continue
        if args == ["--write"]:
            path.write_text(apply_header(text, header), encoding="utf-8")
        else:
            bad.append(str(path.relative_to(ROOT)))
    if bad:
        print(f"Нет строки авторства или устарела версия ({len(bad)}), ожидается:\n  {header}")
        for p in bad:
            print(f"  {p}")
        print("Исправить: python scripts/ip_headers.py --write")
        return 1
    print(f"Строка авторства на месте: {header}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
