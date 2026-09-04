"""
run_benchmark.py — CLI-запуск Agenomics Synthetic Benchmark Suite.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.6.1

Запуск:
    PYTHONPATH=. python3 benchmark/run_benchmark.py
"""

from .metrics import run_all_benchmarks
from .sensitivity import run_sensitivity_suite


def print_report():
    results = run_all_benchmarks()
    sensitivity_results = run_sensitivity_suite()

    print("=" * 78)
    print("AGENOMICS SYNTHETIC BENCHMARK SUITE")
    print("Prizolov Lab · by Dm.Andreyanov")
    print("=" * 78)
    print()
    print(
        "ВНИМАНИЕ: этот отчёт проверяет внутреннюю согласованность формул "
        "методологии на синтетических данных, НЕ предсказательную силу "
        "относительно реальных production-инцидентов. См. benchmark/README.md."
    )
    print()

    for r in results:
        status_marker = "✅" if r.status == "computed" else "⛔"
        print(f"{status_marker} {r.metric}")
        print(f"   status: {r.status}")
        if r.value is not None:
            print(f"   value:  {r.value:.4f}")
        print(f"   detail: {r.detail}")
        print()

    computed = sum(1 for r in results if r.status == "computed")
    print("-" * 78)
    print(f"Итого: {computed}/{len(results)} метрик вычислено, "
          f"{len(results) - computed} честно помечены как not_computable.")

    print()
    print("=" * 78)
    print("EVIDENCE QUALITY (v0.6.1) — устойчивость метрик, не новый функционал")
    print("=" * 78)
    print()
    for r in sensitivity_results:
        print(f"✅ {r.metric}")
        print(f"   value:  {r.value}")
        print(f"   detail: {r.detail}")
        print()
    print("=" * 78)


if __name__ == "__main__":
    print_report()
