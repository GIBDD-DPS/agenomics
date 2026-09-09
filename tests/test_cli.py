"""
test_cli.py. Тесты минимального CLI (agenomics/cli.py).

Проект: Prizolov Lab

Использует io.StringIO/redirect_stdout вместо pytest capsys, чтобы
тесты можно было запускать и без pytest (тот же принцип, что и во
всех остальных тестах этого проекта, каждый файл самодостаточен и
исполним напрямую через "python tests/test_cli.py").
"""

import contextlib
import io
import json
import os
import tempfile

from agenomics.cli import main


def _run_cli(args):
    """Запускает CLI, возвращает (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        exit_code = main(args)
    return exit_code, out.getvalue(), err.getvalue()


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_score_command_prints_valid_json():
    with tempfile.TemporaryDirectory() as tmp:
        genome_path = os.path.join(tmp, "genome.json")
        _write_json(genome_path, {"id": "x", "bias_control": 85, "transparency": 80})

        exit_code, out, err = _run_cli(["score", genome_path])
        assert exit_code == 0
        output = json.loads(out)
        assert output["id"] == "x"
        assert 0 <= output["score"] <= 100


def test_score_command_rejects_invalid_genome():
    with tempfile.TemporaryDirectory() as tmp:
        genome_path = os.path.join(tmp, "genome.json")
        _write_json(genome_path, {"id": "x", "bias_control": 999})

        exit_code, out, err = _run_cli(["score", genome_path])
        assert exit_code == 1
        assert "Ошибка" in err


def test_score_command_missing_file():
    exit_code, out, err = _run_cli(["score", "/tmp/does_not_exist_12345.json"])
    assert exit_code == 1


def test_report_command_prints_markdown():
    with tempfile.TemporaryDirectory() as tmp:
        genome_path = os.path.join(tmp, "genome.json")
        _write_json(genome_path, {"id": "support-bot", "bias_control": 85, "transparency": 80})

        exit_code, out, err = _run_cli(["report", genome_path])
        assert exit_code == 0
        assert "Trust Score" in out
        assert "support-bot" in out


def test_compatibility_command_requires_two_agents():
    with tempfile.TemporaryDirectory() as tmp:
        team_path = os.path.join(tmp, "team.json")
        _write_json(team_path, {"agents": [{"id": "solo", "bias_control": 85}]})

        exit_code, out, err = _run_cli(["compatibility", team_path])
        assert exit_code == 1


def test_compatibility_command_scores_team():
    with tempfile.TemporaryDirectory() as tmp:
        team_path = os.path.join(tmp, "team.json")
        _write_json(team_path, {"agents": [
            {"id": "a", "bias_control": 85, "risk_tolerance": 50, "social_style": 40},
            {"id": "b", "bias_control": 82, "risk_tolerance": 55, "social_style": 45},
        ]})

        exit_code, out, err = _run_cli(["compatibility", team_path])
        assert exit_code == 0
        assert "Compatibility Score" in out


def test_genome_validate_accepts_valid_genome():
    with tempfile.TemporaryDirectory() as tmp:
        genome_path = os.path.join(tmp, "genome.json")
        _write_json(genome_path, {"id": "x", "bias_control": 85})

        exit_code, out, err = _run_cli(["genome", "validate", genome_path])
        assert exit_code == 0
        assert "валиден" in out


def test_genome_validate_rejects_invalid_genome():
    with tempfile.TemporaryDirectory() as tmp:
        genome_path = os.path.join(tmp, "genome.json")
        _write_json(genome_path, {"id": "x", "bias_control": 999})

        exit_code, out, err = _run_cli(["genome", "validate", genome_path])
        assert exit_code == 1


def test_evidence_list_shows_observations():
    from agenomics import EvidenceStore

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "evidence.db")
        store = EvidenceStore(db_path)
        store.record_observation("agent-1", 80.0, "Trusted")
        store.close()

        exit_code, out, err = _run_cli(["evidence", "list", db_path])
        assert exit_code == 0
        assert "agent-1" in out
        assert "Всего: 1" in out


def test_evidence_list_missing_db_file():
    exit_code, out, err = _run_cli(["evidence", "list", "/tmp/does_not_exist_evidence_12345.db"])
    assert exit_code == 1


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK:", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} passed")
