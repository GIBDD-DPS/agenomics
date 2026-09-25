# Порядок выпуска версии

Каждая версия Agenomics фиксируется четырьмя независимыми следами:
история Git, annotated-тег, манифест исходников с SHA-256 и запись в
[CREATION_RECORD.md](CREATION_RECORD.md).

1. Версия поднимается в `pyproject.toml`, `agenomics/__init__.py`,
   `agenomics/api.py`, CHANGELOG и README (сверяет
   `tests/test_version_consistency.py`).
2. Заголовки файлов обновляются одной командой:
   `python scripts/ip_headers.py --write`. CI проверяет их через `--check`.
3. Изменение попадает в `main` через pull request.
4. На коммит слияния ставится annotated-тег `vX.Y.Z` с сообщением
   `Agenomics X.Y.Z · Dm.Andreyanov · Prizolov Lab · 2026`.
5. Манифест строится по тегу, а не по рабочей копии:
   `python scripts/release_manifest.py vX.Y.Z`. Он создаёт
   `release/vX.Y.Z/SOURCE_MANIFEST.json` и `SHA256SUMS.txt` и добавляется
   отдельным коммитом. Файлы релиза после этого не меняются.
6. В CREATION_RECORD дописывается строка версии.
7. Пакет публикуется на PyPI и сверяется с манифестом:
   `python scripts/release_manifest.py --verify-wheel dist/agenomics-X.Y.Z-py3-none-any.whl`.
   Пакет собирается из checkout тега, где манифеста ещё нет: скрипт берёт
   его из `origin/main` (перед этим `git fetch origin`).

Хэши считаются по содержимому с окончаниями строк LF: сборка пакета на
Windows даёт CRLF, код при этом тот же, и сверка не должна зависеть от
того, где собран пакет.
