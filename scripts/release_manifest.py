#!/usr/bin/env python3
# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
release_manifest.py. Манифест исходников релиза с SHA-256 по состоянию Git.

    python scripts/release_manifest.py v0.9.2              # по тегу или коммиту
    python scripts/release_manifest.py --verify v0.9.2     # пересчитать и сверить с release/v0.9.2/
    python scripts/release_manifest.py --verify-wheel dist/agenomics-0.9.2-py3-none-any.whl
    python scripts/release_manifest.py --record v0.9.2     # дописать строку в IP/CREATION_RECORD.md

Манифест строится по коммиту из Git, а не по рабочей копии: он описывает
то, что было выпущено, даже если рабочая копия уже ушла вперёд.

Хэши считаются по содержимому с окончаниями строк LF. Пакет, собранный на
Windows, содержит CRLF, код при этом тот же, и сверка не должна зависеть
от того, где собран пакет.

Результат: release/vX.Y.Z/SOURCE_MANIFEST.json и SHA256SUMS.txt (формат
sha256sum; последней строкой хэш самого манифеста).
"""

import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Что входит в зафиксированное состояние релиза: код пакета и документы,
# которые описывают продукт и права на него.
INCLUDED_PREFIXES = ("agenomics/", "docs/", "IP/", "prompts/")
INCLUDED_FILES = ("LICENSE", "NOTICE", "README.md", "CHANGELOG.md", "pyproject.toml")


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def sha256_lf(content: bytes) -> str:
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def _included(path: str) -> bool:
    if path in INCLUDED_FILES:
        return True
    if not path.startswith(INCLUDED_PREFIXES):
        return False
    return not path.startswith("docs/releases/")  # заметки к релизам пишутся после релиза


def build_manifest(ref: str) -> dict:
    commit = git("rev-parse", f"{ref}^{{commit}}").decode().strip()
    commit_date = git("show", "-s", "--format=%cI", commit).decode().strip()
    paths = sorted(p for p in git("ls-tree", "-r", "--name-only", commit).decode().splitlines() if _included(p))
    files = []
    for path in paths:
        content = git("show", f"{commit}:{path}")
        files.append({"path": path, "sha256": sha256_lf(content), "bytes": len(content.replace(b"\r\n", b"\n"))})

    ip = json.loads(git("show", f"{commit}:IP/IP_MANIFEST.json")) if "IP/IP_MANIFEST.json" in paths else \
        json.loads((ROOT / "IP" / "IP_MANIFEST.json").read_text(encoding="utf-8"))
    version = re.search(rb'^version = "([^"]+)"', git("show", f"{commit}:pyproject.toml"), re.M).group(1).decode()
    tag_commit = subprocess.run(["git", "rev-parse", f"refs/tags/v{version}^{{commit}}"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip()
    sums = "".join(f"{f['sha256']}  {f['path']}\n" for f in files)
    return {
        "release_id": f"AGN-{version}",
        "product": ip["product"],
        "version": version,
        "author": ip["author"],
        "brand": ip["brand"],
        "copyright": ip["copyright"],
        "license": ip["license"],
        "git_commit": commit,
        "commit_date": commit_date,
        "tag": f"v{version}" if tag_commit == commit else None,
        "hash_algorithm": "SHA-256",
        "line_endings": "LF-normalized",
        "source_sha256": hashlib.sha256(sums.encode()).hexdigest(),
        "files": files,
    }


def write_release(manifest: dict) -> Path:
    out = ROOT / "release" / f"v{manifest['version']}"
    out.mkdir(parents=True, exist_ok=True)
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (out / "SOURCE_MANIFEST.json").write_text(manifest_text, encoding="utf-8")
    sums = "".join(f"{f['sha256']}  {f['path']}\n" for f in manifest["files"])
    sums += f"{hashlib.sha256(manifest_text.encode()).hexdigest()}  SOURCE_MANIFEST.json\n"
    (out / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    return out


def verify(ref: str) -> int:
    rebuilt = build_manifest(ref)
    path = ROOT / "release" / f"v{rebuilt['version']}" / "SOURCE_MANIFEST.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    problems = [k for k in ("git_commit", "source_sha256", "files") if stored[k] != rebuilt[k]]
    if problems:
        print(f"Не совпадает с {ref}: {problems}")
        return 1
    print(f"{path.relative_to(ROOT)} совпадает с {ref} ({len(stored['files'])} файлов, "
          f"source_sha256 {stored['source_sha256'][:16]}…)")
    return 0


# Манифест добавляется в main после тега, поэтому в checkout тега его ещё
# нет: сборка пакета идёт как раз оттуда. Тогда он берётся из main.
MANIFEST_REFS = ("origin/main", "main")


def load_manifest(version: str) -> dict:
    rel = f"release/v{version}/SOURCE_MANIFEST.json"
    if (ROOT / rel).exists():
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))
    for ref in MANIFEST_REFS:
        found = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=ROOT, capture_output=True)
        if found.returncode == 0:
            return json.loads(found.stdout)
    raise SystemExit(f"Нет {rel} ни в рабочей копии, ни в {', '.join(MANIFEST_REFS)}. "
                     f"Сначала: git fetch origin")


def verify_wheel(wheel: str) -> int:
    with zipfile.ZipFile(wheel) as zf:
        dist_version = re.search(r"-(\d+\.\d+\.\d+)-", Path(wheel).name).group(1)
        manifest = load_manifest(dist_version)
        expected = {f["path"]: f["sha256"] for f in manifest["files"] if f["path"].startswith("agenomics/")}
        actual = {n: sha256_lf(zf.read(n)) for n in zf.namelist() if n.startswith("agenomics/") and n.endswith(".py")}
    mismatched = sorted(p for p in expected if actual.get(p) != expected[p])
    extra = sorted(set(actual) - set(expected))
    if mismatched or extra:
        print(f"Пакет расходится с манифестом {manifest['release_id']}: не совпадают {mismatched}, лишние {extra}")
        return 1
    print(f"{Path(wheel).name}: все {len(expected)} модулей совпадают с манифестом {manifest['release_id']}")
    return 0


def creation_record_row(tag: str) -> str:
    """Строка IP/CREATION_RECORD.md для версии по тегу: дата из CHANGELOG,
    коммит версии, коммит слияния и PR, краткое описание из CHANGELOG
    (первая фраза вступления до двоеточия, точки или скобки; нет
    вступления — заголовок PR). Описание — черновик: строка попадает в
    main через PR, где её можно поправить."""
    commit = git("rev-parse", f"{tag}^{{commit}}").decode().strip()
    version = re.search(rb'^version = "([^"]+)"', git("show", f"{commit}:pyproject.toml"), re.M).group(1).decode()
    changelog = git("show", f"{commit}:CHANGELOG.md").decode("utf-8")
    section = re.search(rf"^## \[{re.escape(version)}\] - (\S+)\n(.*?)(?=^## \[|\Z)", changelog, re.M | re.S)
    date, body = section.group(1), section.group(2)
    introduced = git("log", commit, "--reverse", "--format=%h", "-S", f'version = "{version}"',
                     "--", "pyproject.toml").decode().split()
    version_commit = f"`{introduced[0]}`" if introduced else "—"
    message = git("log", "-1", "--format=%B", commit).decode("utf-8").strip().split("\n")
    pr = re.match(r"Merge pull request #(\d+)", message[0])
    merge = f"`{commit[:7]}` (PR #{pr.group(1)})" if pr else f"`{commit[:7]}`"
    intro = body.strip().split("\n")[0]
    if intro and not intro.startswith("#"):
        summary = re.split(r"[:.](?:\s|$)| \(", intro, maxsplit=1)[0].strip()
    else:
        summary = message[-1].strip() if pr and len(message) > 1 else f"Версия {version}"
        summary = re.sub(r"^Release \S+:\s*", "", summary)
    return f"| {version} | {date} | {version_commit} | {merge} | {summary} |"


def append_record(tag: str) -> bool:
    """Дописывает строку версии, если её ещё нет. Записи только добавляются."""
    path = ROOT / "IP" / "CREATION_RECORD.md"
    text = path.read_text(encoding="utf-8")
    row = creation_record_row(tag)
    if re.search(rf"^\| {re.escape(row.split(' | ')[0][2:])} \|", text, re.M):
        return False
    path.write_text(text.rstrip("\n") + "\n" + row + "\n", encoding="utf-8")
    return True


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) == 2 and args[0] == "--verify":
        return verify(args[1])
    if len(args) == 2 and args[0] == "--verify-wheel":
        return verify_wheel(args[1])
    if len(args) == 2 and args[0] == "--record":
        print("Дописано" if append_record(args[1]) else "Строка версии уже есть", "в IP/CREATION_RECORD.md")
        return 0
    if len(args) == 1 and not args[0].startswith("-"):
        out = write_release(build_manifest(args[0]))
        print(f"Записано: {out.relative_to(ROOT)}/SOURCE_MANIFEST.json, SHA256SUMS.txt")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
