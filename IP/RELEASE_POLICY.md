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
   `Agenomics X.Y.Z · Dm.Andreyanov · Prizolov Lab · 2026` и отправляется
   на GitHub:

   ```
   git fetch origin
   git tag -a vX.Y.Z origin/main -m "Agenomics X.Y.Z · Dm.Andreyanov · Prizolov Lab · 2026"
   git push origin vX.Y.Z
   ```

Дальше всё делает `.github/workflows/publish.yml`:

5. Проверки: тег совпадает с версией в `pyproject.toml`, тег annotated,
   коммит тега входит в `main`. Затем тесты, `verify_release.py`,
   `ip_headers.py --check`.
6. Сборка и `twine check`, установка wheel в чистое окружение (smoke test).
7. Манифест строится по тегу: `release_manifest.py vX.Y.Z`, wheel
   сверяется с ним (`--verify-wheel`).
8. Публикация на PyPI через Trusted Publishing, без токена.
9. Пакет скачивается обратно с PyPI и сверяется с манифестом и побайтно
   с собранным файлом.
10. GitHub Release: пакет, `SOURCE_MANIFEST.json`, `SHA256SUMS.txt`, текст
    из `docs/releases/vX.Y.Z.md` или раздела CHANGELOG.
11. PR `release-record/vX.Y.Z` в `main`: `release/vX.Y.Z/` и строка версии
    в `CREATION_RECORD.md` (`release_manifest.py --record vX.Y.Z`).
    Описание версии в строке — черновик из CHANGELOG, его можно поправить
    в PR. Файлы релиза после слияния не меняются.

Если любая проверка до шага 8 не прошла, на PyPI ничего не уходит:
исправление идёт новой версией (тег сдвигать нельзя, PyPI не принимает
один номер дважды).

## Однократная настройка

- **PyPI** → проект agenomics → Publishing → Add a new publisher → GitHub:
  owner `GIBDD-DPS`, repository `agenomics`, workflow `publish.yml`,
  environment `pypi`.
- **GitHub** → Settings → Actions → General → Workflow permissions →
  «Allow GitHub Actions to create and approve pull requests» (для шага 11).
- По желанию: Settings → Environments → `pypi` → Required reviewers. Тогда
  публикация ждёт подтверждения в интерфейсе GitHub.

## Ручной выпуск

Если Actions недоступны, шаги 5–11 выполняются вручную из checkout тега:
`python -m build`, `twine check dist/*`,
`python scripts/release_manifest.py --verify-wheel dist/agenomics-X.Y.Z-py3-none-any.whl`
(манифест берётся из `origin/main`, перед этим `git fetch origin`),
`twine upload dist/*`, затем `release_manifest.py vX.Y.Z` и
`--record vX.Y.Z` отдельным PR.

Хэши считаются по содержимому с окончаниями строк LF: сборка пакета на
Windows даёт CRLF, код при этом тот же, и сверка не должна зависеть от
того, где собран пакет.
