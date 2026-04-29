"""
Daemon think_loop indítása: a policy `discovery.max_runtime_seconds` határozza meg a plafont
(pl. 86400 = 24 óra; 0 = korlátlan).

Példa:
  python run_daemon_test.py
  python run_daemon_test.py --policy agi_policy_daemon.example.yaml
  python run_daemon_test.py --status-every 5
  python run_daemon_test.py --registry axioms_registry_timeless.json
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from axiom_kernel import AxiomaticInferenceEngine
from policy_manager import PolicyManager


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Daemon teszt: think_loop max. futási idő a policy max_runtime_seconds szerint."
    )
    ap.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "agi_policy_daemon.example.yaml",
        help="YAML policy (alap: agi_policy_daemon.example.yaml)",
    )
    ap.add_argument(
        "--status-every",
        type=float,
        default=0.0,
        metavar="SEC",
        help="Ennyi másodpercenként kiírja az utolsó think_step sort (THINK[...] mode=... pair=...). 0=kikapcs.",
    )
    ap.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Axióma JSON (alap: axioms_registry.json a projektben). Pl. axioms_registry_timeless.json",
    )
    args = ap.parse_args()
    policy_path = args.policy.resolve()
    if not policy_path.is_file():
        print(f"Hiba: nincs ilyen policy: {policy_path}", file=sys.stderr)
        sys.exit(1)

    registry_path: str | None = None
    if args.registry is not None:
        rp = args.registry.resolve()
        if not rp.is_file():
            print(f"Hiba: nincs ilyen registry: {rp}", file=sys.stderr)
            sys.exit(1)
        registry_path = str(rp)
        print(f"Registry: {rp}")

    pm = PolicyManager(policy_path)
    pm.load()
    max_s = pm.daemon_max_runtime_seconds
    print(f"Policy: {policy_path}")
    if max_s > 0:
        print(f"max_runtime_seconds: {max_s:.0f} (~{max_s / 3600:.2f} h)")
    else:
        print("max_runtime_seconds: 0 (korlatlan — allitsd 86400-ra 24h plafonhoz)")

    eng = AxiomaticInferenceEngine(
        policy_enabled=True,
        policy_path=str(policy_path),
        registry_path=registry_path,
    )
    print(f"PID={os.getpid()}  interpreter={sys.executable}", flush=True)
    print(
        "Naplok (policy szerint): telemetry.log — időnkénti összegzés; "
        "discovery_log.txt — csak keresztdomain él + magas Q, ha discovery.enabled. "
        "Utolsó lépés: engine.format_last_think_ascii() vagy --status-every.",
        flush=True,
    )
    stop_status = threading.Event()

    def status_loop() -> None:
        interval = float(args.status_every)
        while not stop_status.wait(timeout=interval):
            try:
                print(eng.format_last_think_ascii(), flush=True)
            except Exception:
                break

    status_thread: threading.Thread | None = None
    if args.status_every and args.status_every > 0:
        status_thread = threading.Thread(target=status_loop, daemon=True)
        status_thread.start()

    eng.start_autonomous_thinking()
    print("think_loop fut... (Ctrl+C: stop_thinking)", flush=True)
    try:
        eng.join_thinking()
    except KeyboardInterrupt:
        print("\nMegallitas...", flush=True)
        eng.stop_thinking()
        eng.join_thinking()
    finally:
        stop_status.set()


if __name__ == "__main__":
    main()
