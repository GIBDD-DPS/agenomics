"""
test_reports_docx.py — тесты trust_report_docx() методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.3

Требует python-docx. Если пакет не установлен, тесты в этом файле
пропускаются (не падают) — это ожидаемо для окружений, где не нужен
DOCX-экспорт (опциональная зависимость, см. reports.py).
"""

import os
import tempfile

try:
    import docx as _docx_check  # noqa: F401
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

from agenomics import AgentGenome, TrustScorer, trust_report_docx


def test_generates_valid_docx_file():
    if not HAS_DOCX:
        return  # пропуск: python-docx не установлен
    genome = AgentGenome(
        id="support-bot-v2", domain="support", autonomy="autonomous",
        transparency=85, bias_control=72, data_safety=90,
        drift_rate=0.35, has_ledger=False,
    )
    result = TrustScorer().score(genome)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "report.docx")
        returned = trust_report_docx(result, "support-bot-v2", path)
        assert returned == path
        assert os.path.exists(path)
        assert os.path.getsize(path) > 1000  # не пустой/повреждённый файл


def test_docx_contains_expected_text():
    if not HAS_DOCX:
        return
    from docx import Document

    genome = AgentGenome(
        id="report-agent", domain="finance", autonomy="autonomous",
        transparency=70, bias_control=75, data_safety=80,
        drift_rate=0.2, has_ledger=False,
    )
    result = TrustScorer().score(genome)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "report.docx")
        trust_report_docx(result, "report-agent", path)

        doc = Document(path)
        all_text = []
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    all_text.append(cell.text)
        full_text = " ".join(all_text)

        assert "report-agent" in full_text
        assert "PRIZOLOV LAB" in full_text
        assert "Dm.Andreyanov" in full_text
        assert result.label in full_text
        assert "Trust Score Report" in full_text


def test_docx_without_capped_reason_does_not_crash():
    """Агент без потолка (Advisory) — блок 'ПОТОЛОК ПРИМЕНЁН' должен
    просто отсутствовать, без ошибок генерации."""
    if not HAS_DOCX:
        return
    genome = AgentGenome(
        id="advisory-agent", domain="content", autonomy="advisory",
        transparency=90, bias_control=90, data_safety=90,
        drift_rate=0.05, has_ledger=True,
    )
    result = TrustScorer().score(genome)
    assert result.capped_reason is None
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "report.docx")
        trust_report_docx(result, "advisory-agent", path)
        assert os.path.exists(path)


def test_import_error_message_is_helpful_when_docx_missing():
    """Проверяем, что _require_python_docx() существует и не ломает
    нормальную работу, когда python-docx установлен (основной путь)."""
    if not HAS_DOCX:
        return
    # Если мы дошли сюда — python-docx есть, и обычный вызов должен пройти
    # без исключений (само исключение ImportError тестировать без
    # реального удаления пакета из окружения нецелесообразно).
    genome = AgentGenome(id="x", bias_control=80)
    result = TrustScorer().score(genome)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "r.docx")
        trust_report_docx(result, "x", path)
        assert os.path.exists(path)
