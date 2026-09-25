# Agenomics 0.9.3 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_ip.py. Авторство и происхождение: строка авторства в каждом .py,
реестр компонентов, NOTICE, целостность манифестов релизов.

Проект: Prizolov Lab
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ip_headers  # noqa: E402


def test_every_python_file_has_current_header():
    header = ip_headers.expected_header()
    missing = [str(p.relative_to(ROOT)) for p in ip_headers.python_files()
               if not ip_headers.has_header(p.read_text(encoding="utf-8"), header)]
    assert not missing, f"нет строки авторства: {missing}; python scripts/ip_headers.py --write"


def test_header_matches_manifest_and_package_version():
    import agenomics
    manifest = json.loads((ROOT / "IP" / "IP_MANIFEST.json").read_text(encoding="utf-8"))
    header = ip_headers.expected_header()
    assert header == (f"# Agenomics {agenomics.__version__} | Author: Dm.Andreyanov | "
                      f"Brand: Prizolov Lab | © 2026")
    assert manifest["author"] == "Dm.Andreyanov" and manifest["brand"] == "Prizolov Lab"


def test_apply_header_keeps_shebang_and_replaces_old_version():
    header = "# Agenomics 9.9.9 | Author: A | Brand: B | © 2026"
    old = "#!/usr/bin/env python3\n# Agenomics 0.1.0 | Author: A | Brand: B | © 2026\nprint(1)\n"
    new = ip_headers.apply_header(old, header)
    assert new.split("\n")[:3] == ["#!/usr/bin/env python3", header, "print(1)"]
    assert ip_headers.apply_header("x = 1\n", header).startswith(header + "\nx = 1")


def test_ip_manifest_components_point_to_existing_paths():
    manifest = json.loads((ROOT / "IP" / "IP_MANIFEST.json").read_text(encoding="utf-8"))
    missing = [p for c in manifest["components"] for p in c["paths"] if not (ROOT / p).exists()]
    assert not missing, missing
    ids = [c["id"] for c in manifest["components"]]
    assert len(ids) == len(set(ids))


def test_every_package_module_is_registered_as_component():
    manifest = json.loads((ROOT / "IP" / "IP_MANIFEST.json").read_text(encoding="utf-8"))
    registered = {p for c in manifest["components"] for p in c["paths"]}
    modules = {f"agenomics/{p.name}" for p in (ROOT / "agenomics").glob("*.py") if p.name != "__init__.py"}
    assert not modules - registered, f"модули без компонента в IP_MANIFEST.json: {sorted(modules - registered)}"


def test_notice_names_author_and_brand():
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Dm.Andreyanov" in notice and "Prizolov Lab" in notice and "Apache License" in notice


def test_release_manifests_are_self_consistent():
    """SHA256SUMS.txt совпадает с манифестом, а последняя строка — хэш
    самого манифеста. Сверка с Git по коммиту делается отдельно
    (release_manifest.py --verify): в CI клон неполный."""
    releases = sorted((ROOT / "release").glob("v*/SOURCE_MANIFEST.json"))
    assert releases, "нет ни одного манифеста релиза"
    for manifest_path in releases:
        text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(text)
        sums = (manifest_path.parent / "SHA256SUMS.txt").read_text(encoding="utf-8")
        expected = "".join(f"{f['sha256']}  {f['path']}\n" for f in manifest["files"])
        assert sums == expected + f"{hashlib.sha256(text.encode()).hexdigest()}  SOURCE_MANIFEST.json\n"
        assert manifest["source_sha256"] == hashlib.sha256(expected.encode()).hexdigest()
        assert manifest["author"] == "Dm.Andreyanov" and manifest["brand"] == "Prizolov Lab"
        assert manifest_path.parent.name == f"v{manifest['version']}"


def test_release_manifest_verifies_against_git_when_history_available():
    commit = json.loads((ROOT / "release" / "v0.9.2" / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))["git_commit"]
    if subprocess.run(["git", "cat-file", "-e", commit], cwd=ROOT, capture_output=True).returncode != 0:
        return  # неполный клон (CI): коммита нет локально
    import release_manifest
    assert release_manifest.verify(commit) == 0
