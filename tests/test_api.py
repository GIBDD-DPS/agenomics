"""
test_api.py. Smoke-тесты веб-API (agenomics/api.py).

Проект: Prizolov Lab

Честная оговорка: эти тесты требуют fastapi и httpx (TestClient),
которых нет в ядре пакета (agenomics/api.py — опциональная часть,
устанавливается через requirements.txt для деплоя, не через pip
install agenomics). CI уже ставит requirements.txt перед pytest,
поэтому здесь эти тесты реально выполняются.
"""

from fastapi.testclient import TestClient

from agenomics.api import app
from agenomics import __version__

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_version_matches_package_version():
    """Регрессионный тест на реальный найденный баг: version в api.py
    был захардкожен как "0.3.0" и не менялся с v0.3, хотя ядро пакета
    ушло далеко вперёд (0.7.4 на момент находки). Явно сверяем со
    значением из __init__.py, а не с строковой константой, чтобы
    повторный дрейф версий сразу ломал тест."""
    response = client.get("/health")
    assert response.json()["version"] == __version__


def test_root_returns_endpoint_list():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "POST /score" in data["endpoints"]
    assert "POST /compatibility" in data["endpoints"]


def test_score_endpoint_returns_valid_trust_score():
    payload = {
        "id": "test-agent",
        "domain": "content",
        "autonomy": "advisory",
        "transparency": 80,
        "bias_control": 85,
        "data_safety": 90,
        "has_ledger": True,
    }
    response = client.post("/score", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-agent"
    assert 0 <= data["score"] <= 100
    assert data["label"] in ("Trusted", "Conditional", "High Risk")


def test_score_endpoint_rejects_invalid_autonomy():
    payload = {"id": "test-agent", "autonomy": "not-a-real-value"}
    response = client.post("/score", json=payload)
    assert response.status_code == 400


def test_compatibility_endpoint_returns_team_result():
    payload = {
        "agents": [
            {"id": "a", "bias_control": 85, "risk_tolerance": 50, "social_style": 40},
            {"id": "b", "bias_control": 82, "risk_tolerance": 55, "social_style": 45},
        ]
    }
    response = client.post("/compatibility", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["pairs"]) == 1
    assert 0 <= data["average_score"] <= 100


def test_compatibility_endpoint_requires_at_least_two_agents():
    payload = {"agents": [{"id": "solo", "bias_control": 85}]}
    response = client.post("/compatibility", json=payload)
    assert response.status_code == 422  # pydantic min_length validation


def test_cors_headers_present_on_preflight():
    """Найдено внешним разбором: CORS вообще не был настроен, любой
    запрос из браузера с другого origin был бы заблокирован политикой
    same-origin. Проверяем, что preflight OPTIONS-запрос теперь получает
    корректные CORS-заголовки."""
    response = client.options(
        "/score",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK:", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} passed")
