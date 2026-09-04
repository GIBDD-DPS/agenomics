"""
run_benchmark.py — CLI-запуск Agenomics Synthetic Benchmark Suite v0.1.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.5.0

Запуск:
    PYTHONPATH=. python3 benchmark/run_benchmark.py
"""

from .metrics import run_all_benchmarks


def print_report():
    results = run_all_benchmarks()

    print("=" * 78)
    print("AGENOMICS SYNTHETIC BENCHMARK SUITE v0.1")
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
    print("=" * 78)


if __name__ == "__main__":
    print_report()
