"""Loopback HTTP API for orchestration (handoff §5.2). Binds 127.0.0.1 only.

Endpoints:
- ``GET  /pending``           -> list of pending actions
- ``POST /execute``           -> {action_id} or {action, id, price, qty, slot?}
- ``POST /cancel-execution``  -> {action_id?}
"""

from __future__ import annotations

import json
import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from companion.execution_orchestrator import Orchestrator
from companion.flip_db import FlipDB

log = logging.getLogger("runeclaw.server")

_HOST = "127.0.0.1"  # loopback only — never bind a public interface


def make_server(port: int, orchestrator: Orchestrator, db: FlipDB) -> HTTPServer:
    return HTTPServer((_HOST, port), _build_handler(orchestrator, db))


def _build_handler(orchestrator: Orchestrator, db: FlipDB) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, Any] | None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            if self.path.split("?")[0] == "/pending":
                db.expire_stale(int(time.time()))
                self._send(200, [a.as_dict() for a in db.list_pending()])
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802 (http.server API)
            body = self._read_json()
            if body is None:
                self._send(400, {"error": "invalid json"})
                return
            path = self.path.split("?")[0]
            if path == "/execute":
                if body.get("action_id"):
                    self._send(200, orchestrator.execute(body["action_id"]))
                else:
                    self._send(200, orchestrator.execute_adhoc(body))
            elif path == "/cancel-execution":
                self._send(200, orchestrator.cancel(body.get("action_id")))
            else:
                self._send(404, {"error": "not found"})

        def log_message(self, fmt: str, *args: Any) -> None:
            log.debug("%s - %s", self.address_string(), fmt % args)

    return Handler
