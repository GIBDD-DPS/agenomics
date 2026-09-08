"""
test_version_consistency.py. Регрессионный тест на реальный найденный
баг: agenomics/api.py не обновлялась с версии 0.3.0 несколько релизов
подряд, пока внешний разбор явно на это не указал. Этот тест делает
повторение того же класса бага невозможным незаметно.

Проект: Prizolov Lab
"""

import re
from pathlib import Path

import agenomics

_REPO_ROOT = Path(__file__).parent.parent


def _read(path: str) -> str:
    return (_REPO_ROOT / path).read_text(encoding="utf-8")


def test_pyproject_version_matches_package_version():
    pyproject = _read("pyproject.toml")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert match is not None, "version не найдена в pyproject.toml"
    assert match.group(1) == agenomics.__version__


def test_api_version_matches_package_version():
    api_source = _read("agenomics/api.py")
    match = re.search(r'version="([^"]+)"', api_source)
    assert match is not None, "version не найдена в FastAPI(...) в api.py"
    assert match.group(1) == agenomics.__version__, (
        f"agenomics/api.py заявляет версию {match.group(1)!r}, "
        f"а пакет на {agenomics.__version__!r}. Именно этот дрейф версий "
        f"был найден внешним разбором: api.py не обновлялась с 0.3.0 "
        f"несколько релизов подряд."
    )


def test_api_health_endpoint_version_matches_package_version():
    api_source = _read("agenomics/api.py")
    match = re.search(r'"version": "([^"]+)"', api_source)
    assert match is not None, 'литерал "version": "..." не найден в /health'
    assert match.group(1) == agenomics.__version__


def test_changelog_top_entry_matches_package_version():
    changelog = _read("CHANGELOG.md")
    match = re.search(r'^## \[([\d.]+)\]', changelog, re.MULTILINE)
    assert match is not None, "не найдена ни одна версия в CHANGELOG.md"
    assert match.group(1) == agenomics.__version__, (
        f"Верхняя запись CHANGELOG.md это {match.group(1)!r}, "
        f"а пакет на {agenomics.__version__!r}. Забыли добавить запись "
        f"о новом релизе?"
    )


def test_readme_version_badge_matches_package_version():
    readme = _read("README.md")
    match = re.search(r'status-v([\d.]+)-orange', readme)
    assert match is not None, "бейдж версии не найден в README.md"
    assert match.group(1) == agenomics.__version__


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK:", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} passed")
