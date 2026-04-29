#!/usr/bin/env python3
"""
Opcionális HTTP API az AIE csevegő logikája köré (Fázis 6).

- GET  /health  — {"ok": true}
- GET  /status  — Q, küszöb
- POST /chat    — JSON {"message": "..."} válasz: {"reply": "...", "ok": true}

Csak a process_chat_message útvonal (tanult / small talk / derive); REPL-parancsok nincsenek.

Példa:
  python aie_http_server.py --registry axioms_registry.json --port 8765
  python -c "import urllib.request,json; print(urllib.request.urlopen('http://127.0.0.1:8765/status').read())"
  python -c "import urllib.request,json; r=urllib.request.Request('http://127.0.0.1:8765/chat', data=json.dumps({'message':'szia'}).encode(), headers={'Content-Type':'application/json'}); print(urllib.request.urlopen(r).read().decode())"
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

import aie_chat
from axiom_kernel import AxiomaticInferenceEngine


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _send_json(handler: BaseHTTPRequestHandler, code: int, obj: dict[str, Any]) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any] | None:
    try:
        n = int(handler.headers.get("Content-Length", "0") or "0")
    except ValueError:
        n = 0
    if n <= 0:
        return None
    raw = handler.rfile.read(n)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def make_handler(
    engine: AxiomaticInferenceEngine,
    rules: dict,
    learned_pairs: list[dict],
    msgs: dict,
) -> type[BaseHTTPRequestHandler]:
    class ChatHTTPRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:
            p = urlparse(self.path).path
            if p == "/health":
                _send_json(self, 200, {"ok": True})
                return
            if p == "/status":
                q = engine.calculate_q()
                _send_json(
                    self,
                    200,
                    {
                        "q": q,
                        "q_threshold": engine.q_threshold,
                        "ok": True,
                    },
                )
                return
            _send_json(self, 404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:
            p = urlparse(self.path).path
            if p != "/chat":
                _send_json(self, 404, {"ok": False, "error": "not_found"})
                return
            data = _read_json_body(self)
            if not data:
                _send_json(self, 400, {"ok": False, "error": "invalid_json"})
                return
            msg = data.get("message")
            if not isinstance(msg, str):
                _send_json(self, 400, {"ok": False, "error": "missing_message"})
                return
            reply, _inf = aie_chat.process_chat_message(
                msg,
                engine=engine,
                rules=rules,
                learned_pairs=learned_pairs,
                msgs=msgs,
            )
            _send_json(self, 200, {"ok": True, "reply": reply})

    return ChatHTTPRequestHandler


def main() -> None:
    ap = argparse.ArgumentParser(description="AIE HTTP API (chat üzenetek)")
    ap.add_argument("--host", default="127.0.0.1", help="Bind cím")
    ap.add_argument("--port", type=int, default=8765, help="Port")
    ap.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "communication" / "hu_rules.yaml",
    )
    ap.add_argument(
        "--learned",
        type=Path,
        default=ROOT / "communication" / "hu_learned.yaml",
    )
    ap.add_argument("--registry", type=Path, default=None)
    ap.add_argument("--policy", type=Path, default=None)
    ap.add_argument("--q-threshold", type=float, default=0.02)
    ap.add_argument("--no-heuristic", action="store_true")
    args = ap.parse_args()

    if not args.rules.is_file():
        raise SystemExit(f"Nincs szabályfájl: {args.rules}")

    rules = _load_yaml(args.rules)
    msgs = rules.get("messages") or {}
    learned_pairs = aie_chat.load_learned(args.learned)

    registry_path = str(args.registry.resolve()) if args.registry else None
    policy_path = str(args.policy.resolve()) if args.policy else None

    engine = AxiomaticInferenceEngine(
        policy_enabled=policy_path is not None,
        policy_path=policy_path,
        registry_path=registry_path,
        use_heuristic_thinking=not args.no_heuristic,
        enable_self_optimization=False,
    )
    engine.q_threshold = float(args.q_threshold)

    handler_cls = make_handler(engine, rules, learned_pairs, msgs)
    httpd = ThreadingHTTPServer((args.host, args.port), handler_cls)
    print(
        f"AIE HTTP: http://{args.host}:{args.port}/  "
        f"(GET /health /status, POST /chat JSON)",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nLeállítás.", flush=True)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
