#!/usr/bin/env python3
"""
AIE magyar csevegő — stdin/stdout (chat-szerű REPL).

- ``communication/hu_rules.yaml`` — alap small talk és üzenetek
- ``communication/hu_learned.yaml`` — /learn által bővített párok (tanítás)
- ``communication/hu_grammar.yaml`` — nyelvtani jegyzet (/nyelvtan)
- ``aie_knowledge.py`` — /szabályok, /axiómák (regiszter)
- ``ROADMAP.md`` — közös cél fázisokban (/útiter)

Példa:
  python aie_chat.py --registry axioms_registry.json
  python aie_chat.py --discovery-log discovery_log_relaxed.txt --trust-store hypotheses/edge_trust.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows konzol: UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

import aie_knowledge
import edge_trust
import hypothesis_sync
from axiom_kernel import AxiomaticInferenceEngine, InferenceResult, STRUCTURAL_GAP_MSG


def load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_learned(path: Path) -> list[dict]:
    data = load_yaml(path)
    return list(data.get("learned_pairs") or [])


def save_learned(path: Path, pairs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(
            "# Tanult párok — /learn paranccsal bővül. UTF-8.\n"
            "# trigger: részegyezés a felhasználó szövegében (kis/nagybetű nélkül)\n\n"
        )
        yaml.dump(
            {"learned_pairs": pairs},
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )


def match_learned(text: str, pairs: list[dict]) -> str | None:
    """Leghosszabb trigger egyezés nyer (specifikusabb szabály)."""
    t = text.strip().lower()
    best_resp: str | None = None
    best_len = 0
    for p in pairs:
        tr = str(p.get("trigger", "")).strip().lower()
        if len(tr) < 2:
            continue
        if tr in t and len(tr) > best_len:
            best_resp = str(p.get("response", "")).strip()
            best_len = len(tr)
    return best_resp


def match_small_talk(text: str, rules: dict) -> str | None:
    t = text.strip().lower()
    if not t:
        return None
    for block in rules.get("small_talk") or []:
        for kw in block.get("keywords") or []:
            if kw.lower() in t:
                return str(block.get("response", "")).strip()
    return None


def format_nyelvtan(grammar: dict, key: str | None) -> str:
    if not grammar:
        return "Nincs betöltve hu_grammar.yaml."
    sections = grammar.get("sections") or {}
    tips = grammar.get("tips") or {}
    if key:
        k = key.strip().lower()
        for name, body in sections.items():
            if name.lower() == k:
                return f"[{name}]\n{str(body).strip()}"
        for name, body in tips.items():
            if name.lower() == k:
                return f"[tip: {name}]\n{body}"
        return f"Nincs ilyen kulcs: {key}. Elérhető: {', '.join(list(sections) + list(tips))}"
    lines = ["=== Nyelvtani jegyzet (szerkeszd: communication/hu_grammar.yaml) ===\n"]
    for name, body in sections.items():
        lines.append(f"--- {name} ---\n{str(body).strip()}\n")
    if tips:
        lines.append("--- tippek ---\n")
        for name, body in tips.items():
            lines.append(f"{name}: {body}\n")
    return "\n".join(lines)


def parse_learn_arg(rest: str) -> tuple[str, str] | None:
    rest = rest.strip()
    if "|" not in rest:
        return None
    a, b = rest.split("|", 1)
    a, b = a.strip(), b.strip()
    if not a or not b:
        return None
    return a, b


def process_chat_message(
    raw: str,
    *,
    engine: AxiomaticInferenceEngine,
    rules: dict,
    learned_pairs: list[dict],
    msgs: dict,
) -> tuple[str, InferenceResult | None]:
    """
    Egy szöveges üzenet (REPL-parancs nélkül): tanult -> small talk -> derive_statement.
    HTTP API és külső hívások számára; vissza: (kimeneti szöveg, InferenceResult vagy None).
    """
    text = raw.strip()
    if not text:
        return ("", None)
    learned_hit = match_learned(text, learned_pairs)
    if learned_hit:
        return (learned_hit, None)
    st = match_small_talk(text, rules)
    if st:
        return (st, None)
    out = engine.derive_statement(text, source_id="chat")
    if isinstance(out, str):
        if out == STRUCTURAL_GAP_MSG:
            return (str(msgs.get("structural_gap", out)), None)
        return (out, None)
    if isinstance(out, InferenceResult):
        return (out.format_report_ascii(), out)
    return (str(out), None)


def main() -> None:
    ap = argparse.ArgumentParser(description="AIE magyar csevegő (REPL)")
    ap.add_argument(
        "--rules",
        type=Path,
        default=ROOT / "communication" / "hu_rules.yaml",
        help="Alap szabályok YAML",
    )
    ap.add_argument(
        "--learned",
        type=Path,
        default=ROOT / "communication" / "hu_learned.yaml",
        help="Tanult párok fájl (írható)",
    )
    ap.add_argument(
        "--grammar",
        type=Path,
        default=ROOT / "communication" / "hu_grammar.yaml",
        help="Nyelvtani jegyzet (/nyelvtan)",
    )
    ap.add_argument("--registry", type=Path, default=None, help="Axióma JSON (opcionális)")
    ap.add_argument(
        "--policy",
        type=Path,
        default=None,
        help="Policy YAML (opcionális; bekapcsolja a policy-t)",
    )
    ap.add_argument(
        "--q-threshold",
        type=float,
        default=0.02,
        help="Küszöb a derive_statement-hez",
    )
    ap.add_argument(
        "--no-heuristic",
        action="store_true",
        help="think_step véletlen pár mód",
    )
    ap.add_argument(
        "--discovery-log",
        type=Path,
        default=ROOT / "discovery_log.txt",
        help="/hipotézis és /hipotézis-sync: discovery napló útvonal (pl. discovery_log_relaxed.txt)",
    )
    ap.add_argument(
        "--hypotheses-jsonl",
        type=Path,
        default=ROOT / "hypotheses" / "discovered_edges.jsonl",
        help="/hipotézis-sync: ide írja a JSONL-t",
    )
    ap.add_argument(
        "--trust-store",
        type=Path,
        default=ROOT / "hypotheses" / "edge_trust.json",
        help="Fázis 5: /jó /rossz per-él trust (discovery napló szűrése policy-vel)",
    )
    args = ap.parse_args()

    if not args.rules.is_file():
        raise SystemExit(f"Nincs szabályfájl: {args.rules}")
    rules = load_yaml(args.rules)
    msgs = rules.get("messages") or {}
    learned_pairs = load_learned(args.learned)
    grammar_doc = load_yaml(args.grammar)

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

    print(msgs.get("banner", "AIE chat"), flush=True)
    if msgs.get("welcome"):
        print(msgs["welcome"], flush=True)

    prompt = msgs.get("prompt", "Te> ")
    last_inference: InferenceResult | None = None

    while True:
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\n" + msgs.get("goodbye", "Viszlát."), flush=True)
            break

        raw = line.strip()
        if not raw:
            continue

        if raw.startswith("/"):
            parts = raw.split(maxsplit=1)
            cmd = parts[0].lower()
            rest = parts[1] if len(parts) > 1 else ""

            if cmd in ("/quit", "/exit", "/q"):
                print(msgs.get("goodbye", "Viszlát."), flush=True)
                break

            if cmd == "/help":
                print(msgs.get("help", "/help"), flush=True)
                continue

            if cmd == "/status":
                q = engine.calculate_q()
                print(f"Q={q:.4f}  küszöb={engine.q_threshold:.4f}", flush=True)
                try:
                    print(engine.format_last_think_ascii(), flush=True)
                except Exception:
                    pass
                continue

            if cmd == "/warmup":
                n = 500
                if rest.strip().isdigit():
                    n = min(int(rest.strip()), 500_000)
                print(f"  … {n} think_step …", flush=True)
                for _ in range(n):
                    engine.think_step()
                print(f"Q={engine.calculate_q():.4f}", flush=True)
                continue

            if cmd in ("/learn", "/tanul"):
                parsed = parse_learn_arg(rest)
                if not parsed:
                    print(
                        'Használat: /learn trigger szöveg | válasz szöveg\n'
                        'Példa: /learn mi az aie | Az AIE egy axiomatikus következtető mag.',
                        flush=True,
                    )
                    continue
                trig, resp = parsed
                learned_pairs.append({"trigger": trig, "response": resp})
                save_learned(args.learned, learned_pairs)
                print(f"Eltárolva ({len(learned_pairs)} pár): [{trig}] -> …", flush=True)
                continue

            if cmd == "/learned":
                if not learned_pairs:
                    print("Még nincs tanult pár. /learn trigger | válasz", flush=True)
                else:
                    for i, p in enumerate(learned_pairs, 1):
                        print(
                            f"  {i}. [{p.get('trigger','')}] -> {p.get('response','')}",
                            flush=True,
                        )
                continue

            if cmd == "/nyelvtan":
                key = rest.strip() or None
                print(format_nyelvtan(grammar_doc, key), flush=True)
                continue

            if cmd in ("/szabályok", "/szabalyok"):
                reg = engine._registry
                if reg is None:
                    print(
                        "Nincs betöltött axióma-regiszter. Futtasd pl.: "
                        "python aie_chat.py --registry axioms_registry.json",
                        flush=True,
                    )
                else:
                    print(aie_knowledge.explain_rules(reg), flush=True)
                continue

            if cmd in ("/axiómák", "/axiomak", "/axiomák"):
                reg = engine._registry
                if reg is None:
                    print(
                        "Nincs regiszter. --registry axioms_registry.json",
                        flush=True,
                    )
                else:
                    dom = rest.strip() or None
                    print(aie_knowledge.list_axioms(reg, dom), flush=True)
                continue

            if cmd in ("/útiter", "/utiter", "/cel", "/cél"):
                print(aie_knowledge.roadmap_snippet(), flush=True)
                continue

            if cmd in ("/indoklás", "/indoklas"):
                if last_inference is None:
                    print(
                        "Még nincs sikeres következtetés (InferenceResult). "
                        "Írj be egy mondatot, amihez a regiszterben van kulcsszó, "
                        "és a Q legyen a küszöb felett — próbáld: /warmup 5000 majd újra a mondatot.",
                        flush=True,
                    )
                else:
                    print(aie_knowledge.format_indoklas_hu(last_inference), flush=True)
                continue

            if cmd in ("/hipotézis-sync", "/hipotezis-sync"):
                p = args.discovery_log
                out = args.hypotheses_jsonl
                n = hypothesis_sync.sync_discovery_to_jsonl(
                    p, out, trust_path=args.trust_store
                )
                print(f"Szinkronizálva: {n} él -> {out}", flush=True)
                continue

            if cmd in ("/jó", "/jo"):
                rest_parts = rest.strip().split()
                if len(rest_parts) >= 2 and rest_parts[0].isdigit() and rest_parts[1].isdigit():
                    ei, ej = int(rest_parts[0]), int(rest_parts[1])
                else:
                    parsed = edge_trust.parse_last_discovery_edge(args.discovery_log)
                    if parsed is None:
                        print(
                            "Nincs utolsó discovery él: állíts --discovery-log-ot, "
                            "vagy: /jó i j (indexek).",
                            flush=True,
                        )
                        continue
                    ei, ej = parsed
                new = edge_trust.bump_edge_trust(args.trust_store, ei, ej, 0.5)
                print(
                    f"Trust +0.5: {ei}->{ej}  most: {new:.3f}  ({args.trust_store})",
                    flush=True,
                )
                continue

            if cmd == "/rossz":
                rest_parts = rest.strip().split()
                if len(rest_parts) >= 2 and rest_parts[0].isdigit() and rest_parts[1].isdigit():
                    ei, ej = int(rest_parts[0]), int(rest_parts[1])
                else:
                    parsed = edge_trust.parse_last_discovery_edge(args.discovery_log)
                    if parsed is None:
                        print(
                            "Nincs utolsó discovery él: --discovery-log vagy /rossz i j.",
                            flush=True,
                        )
                        continue
                    ei, ej = parsed
                new = edge_trust.bump_edge_trust(args.trust_store, ei, ej, -0.5)
                removed = engine.remove_direct_edge(ei, ej)
                extra = " (helyi gráfból törölve i->j)" if removed else ""
                print(
                    f"Trust -0.5: {ei}->{ej}  most: {new:.3f}{extra}  ({args.trust_store})",
                    flush=True,
                )
                continue

            if cmd == "/trust":
                rest_parts = rest.strip().split()
                if len(rest_parts) >= 2 and rest_parts[0].isdigit() and rest_parts[1].isdigit():
                    ei, ej = int(rest_parts[0]), int(rest_parts[1])
                else:
                    parsed = edge_trust.parse_last_discovery_edge(args.discovery_log)
                    if parsed is None:
                        print(
                            "Nincs utolsó él a discovery naplóban; használat: /trust i j",
                            flush=True,
                        )
                        continue
                    ei, ej = parsed
                data = edge_trust.load_trust_store(args.trust_store)
                t = edge_trust.get_edge_trust(data, ei, ej)
                reg = engine._registry
                la = reg.get_spec(ei).id if reg and reg.get_spec(ei) else f"#{ei}"
                lb = reg.get_spec(ej).id if reg and reg.get_spec(ej) else f"#{ej}"
                print(
                    f"source_trust({ei}->{ej}) = {t:.3f}   [{la} -> {lb}]",
                    flush=True,
                )
                print(f"Fájl: {args.trust_store}", flush=True)
                continue

            if cmd in ("/hipotézis", "/hipotezis"):
                p = args.discovery_log
                if not p.is_file():
                    print(
                        "Nincs discovery napló (vagy más útvonal): "
                        f"{p}\n"
                        "Indíts daemon discovery móddal, vagy: --discovery-log FÁJL",
                        flush=True,
                    )
                else:
                    try:
                        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                        tail = lines[-12:] if len(lines) > 12 else lines
                        print("=== Discovery / hipotézis (utolsó sorok) ===", flush=True)
                        for ln in tail:
                            print(ln, flush=True)
                    except OSError as e:
                        print(f"Olvasási hiba: {e}", flush=True)
                continue

            print("Ismeretlen parancs. /help", flush=True)
            continue

        out_text, inf = process_chat_message(
            raw,
            engine=engine,
            rules=rules,
            learned_pairs=learned_pairs,
            msgs=msgs,
        )
        if inf is not None:
            last_inference = inf
        print(out_text, flush=True)
        if inf is not None:
            print("(Részletes magyar indoklás: /indoklás)", flush=True)
        elif out_text == str(msgs.get("structural_gap", STRUCTURAL_GAP_MSG)):
            print(
                "(Tipp: /status — ha Q a küszöb alatt van, /warmup N. Utána: /indoklás ha sikerült.)",
                flush=True,
            )


if __name__ == "__main__":
    main()
