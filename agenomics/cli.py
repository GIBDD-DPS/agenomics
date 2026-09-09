"""
cli.py. Минимальный командный интерфейс методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.7.10

Не полный набор команд из гипотетического roadmap (agenomics audit,
agenomics drift и т.д.) - только то, что реально можно построить сейчас
поверх уже существующих, протестированных функций, без придумывания
новой логики специально для CLI. Пять команд: score, report,
compatibility, evidence list, genome validate.

Использование:
    agenomics score genome.json
    agenomics report genome.json --language en
    agenomics compatibility team.json
    agenomics evidence list agenomics_evidence.db --agent-id support-bot
    agenomics genome validate genome.json
"""

import argparse
import json
import sys
from pathlib import Path

from .trust_score import AgentGenome, TrustScorer
from .compatibility import CompatibilityScorer
from .reports import trust_report, compatibility_report
from .evidence import EvidenceStore


def _load_genome_dict(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _genome_from_dict(data: dict) -> AgentGenome:
    return AgentGenome(**data)


def cmd_score(args) -> int:
    try:
        data = _load_genome_dict(args.genome_file)
        genome = _genome_from_dict(data)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1

    scorer = TrustScorer(weight_profile=args.weight_profile, language=args.language)
    result = scorer.score(genome)

    print(json.dumps({
        "id": genome.id, "score": result.score, "label": result.label,
        "confidence": result.confidence, "breakdown": result.breakdown,
        "capped_reason": result.capped_reason,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_report(args) -> int:
    try:
        data = _load_genome_dict(args.genome_file)
        genome = _genome_from_dict(data)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1

    scorer = TrustScorer(weight_profile=args.weight_profile, language=args.language)
    result = scorer.score(genome)
    print(trust_report(result, agent_id=genome.id, language=args.language))
    return 0


def cmd_compatibility(args) -> int:
    try:
        with open(args.team_file, encoding="utf-8") as f:
            team_data = json.load(f)
        genomes = [_genome_from_dict(g) for g in team_data["agents"]]
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1

    if len(genomes) < 2:
        print("Ошибка: нужно минимум 2 агента в поле 'agents'", file=sys.stderr)
        return 1

    scorer = CompatibilityScorer(weight_profile=args.weight_profile)
    result = scorer.score_team(genomes)
    print(compatibility_report(result))
    return 0


def cmd_evidence_list(args) -> int:
    if not Path(args.db_path).exists():
        print(f"Ошибка: файл базы не найден: {args.db_path}", file=sys.stderr)
        return 1

    store = EvidenceStore(args.db_path)
    observations = store.get_observations(args.agent_id)
    store.close()

    if not observations:
        print("Наблюдений не найдено" + (f" для agent_id={args.agent_id}" if args.agent_id else ""))
        return 0

    for obs in observations:
        n_incidents = len(obs.incidents)
        print(f"[{obs.id}] {obs.agent_id}: {obs.timestamp}, score={obs.declared_score}, "
              f"label={obs.declared_label}, status={obs.execution_status}, инцидентов={n_incidents}")
    print(f"\nВсего: {len(observations)}")
    return 0


def cmd_genome_validate(args) -> int:
    try:
        data = _load_genome_dict(args.genome_file)
        genome = _genome_from_dict(data)
    except json.JSONDecodeError as e:
        print(f"Невалидный JSON: {e}", file=sys.stderr)
        return 1
    except (ValueError, TypeError) as e:
        print(f"Геном невалиден: {e}", file=sys.stderr)
        return 1

    print(f"Геном валиден: id={genome.id}, tier={genome.tier}, autonomy={genome.autonomy}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="agenomics", description="Agenomics CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_score = subparsers.add_parser("score", help="Рассчитать Trust Score для генома из JSON-файла")
    p_score.add_argument("genome_file")
    p_score.add_argument("--weight-profile", default="default")
    p_score.add_argument("--language", default="ru", choices=["ru", "en"])
    p_score.set_defaults(func=cmd_score)

    p_report = subparsers.add_parser("report", help="Показать полный Markdown-отчёт по геному")
    p_report.add_argument("genome_file")
    p_report.add_argument("--weight-profile", default="default")
    p_report.add_argument("--language", default="ru", choices=["ru", "en"])
    p_report.set_defaults(func=cmd_report)

    p_compat = subparsers.add_parser("compatibility", help="Рассчитать совместимость команды из JSON-файла")
    p_compat.add_argument("team_file", help='JSON с полем "agents": [геном, геном, ...]')
    p_compat.add_argument("--weight-profile", default="default")
    p_compat.set_defaults(func=cmd_compatibility)

    p_evidence = subparsers.add_parser("evidence", help="Команды работы с EvidenceStore")
    evidence_sub = p_evidence.add_subparsers(dest="evidence_command", required=True)
    p_evidence_list = evidence_sub.add_parser("list", help="Показать наблюдения из файла базы")
    p_evidence_list.add_argument("db_path")
    p_evidence_list.add_argument("--agent-id", default=None)
    p_evidence_list.set_defaults(func=cmd_evidence_list)

    p_genome = subparsers.add_parser("genome", help="Команды работы с геномом")
    genome_sub = p_genome.add_subparsers(dest="genome_command", required=True)
    p_genome_validate = genome_sub.add_parser("validate", help="Проверить валидность генома из JSON-файла")
    p_genome_validate.add_argument("genome_file")
    p_genome_validate.set_defaults(func=cmd_genome_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
