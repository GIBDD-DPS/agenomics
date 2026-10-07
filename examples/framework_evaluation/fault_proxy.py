# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
fault_proxy.py — локальный прокси перед Groq для когорты stress_runtime.

Первый запрос модели в прогоне получает внедрённый сбой (503, 429 с
Retry-After или битый JSON с кодом 200), остальные запросы уходят к
настоящему Groq без изменений. Проверяется, справляется ли агент со
сбоем провайдера: повторяет запрос или падает.

Сам внедрённый сбой исходом не является. Исход один: прогон упал,
хотя настоящий апстрим ошибок не давал (FaultProxy.upstream_errors пуст).
Если настоящий Groq сам ответил ошибкой, прогон остаётся сбоем окружения
и исключается, как обычно.

    with FaultProxy() as proxy:
        proxy.arm("http_503_once")
        ... агент ходит на proxy.base_url ...
        proxy.injected, proxy.upstream_errors

Только stdlib.

Проект: Prizolov Lab
"""

import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Optional

UPSTREAM_DEFAULT = "https://api.groq.com"
FAULTS = ("http_503_once", "http_429_once", "malformed_json_once")
_HOP_HEADERS = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding"}


class FaultProxy:
    def __init__(self, upstream: Optional[str] = None, timeout: float = 120.0):
        self.upstream = (upstream or os.environ.get("AGENOMICS_FAULT_UPSTREAM") or UPSTREAM_DEFAULT).rstrip("/")
        self.timeout = timeout
        self._lock = threading.Lock()
        self.fault: Optional[str] = None
        self.injected = False
        self.upstream_errors: List[int] = []
        self.requests = 0
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        """OpenAI-совместимый адрес для клиентов: .../openai/v1."""
        return f"http://127.0.0.1:{self._server.server_address[1]}/openai/v1"

    @property
    def root_url(self) -> str:
        """Корень для Groq SDK (GROQ_BASE_URL), он сам добавляет /openai/v1."""
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def arm(self, fault: str) -> None:
        if fault not in FAULTS:
            raise ValueError(f"неизвестный сбой {fault!r}; допустимы {FAULTS}")
        with self._lock:
            self.fault, self.injected, self.upstream_errors, self.requests = fault, False, [], 0

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()

    def _take_fault(self) -> Optional[str]:
        with self._lock:
            self.requests += 1
            if self.fault and not self.injected:
                self.injected = True
                return self.fault
            return None

    def _handler(self):
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status: int, body: bytes, content_type="application/json", extra=None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _forward(self, method: str, body: Optional[bytes]):
                headers = {k: v for k, v in self.headers.items() if k.lower() not in _HOP_HEADERS}
                request = urllib.request.Request(proxy.upstream + self.path, data=body, headers=headers, method=method)
                try:
                    with urllib.request.urlopen(request, timeout=proxy.timeout) as resp:
                        payload = resp.read()
                        self._send(resp.status, payload, resp.headers.get("Content-Type", "application/json"))
                except urllib.error.HTTPError as err:
                    with proxy._lock:
                        proxy.upstream_errors.append(err.code)
                    self._send(err.code, err.read(), err.headers.get("Content-Type", "application/json"))
                except (urllib.error.URLError, TimeoutError, OSError):
                    with proxy._lock:
                        proxy.upstream_errors.append(0)  # нет связи с апстримом
                    self._send(502, b'{"error": {"message": "upstream unreachable"}}')

            def do_GET(self):
                self._forward("GET", None)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
                fault = proxy._take_fault()
                if fault == "http_503_once":
                    self._send(503, json.dumps({"error": {"message": "Service Unavailable (injected)",
                                                          "type": "internal_server_error"}}).encode())
                elif fault == "http_429_once":
                    self._send(429, json.dumps({"error": {"message": "Rate limit reached (injected), retry",
                                                          "type": "tokens", "code": "rate_limit_exceeded"}}).encode(),
                               extra={"Retry-After": "1"})
                elif fault == "malformed_json_once":
                    self._send(200, b'{"id": "chatcmpl-injected", "object": "chat.completion", "choices": [{"ind')
                else:
                    self._forward("POST", body)

        return Handler
