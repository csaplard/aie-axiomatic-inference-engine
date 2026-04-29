"""
AIE szabályok és axiómák emberi olvasható összefoglalója (regiszter JSON alapján).
"""

from __future__ import annotations

from typing import Optional

from axiom_kernel import InferenceResult
from axiom_registry import AxiomRegistry


def explain_rules(registry: AxiomRegistry) -> str:
    """Negációs párok, tiltott élek — rövid magyar szöveg."""
    lines: list[str] = []
    lines.append("=== Logikai negációs párok ===")
    lines.append("(Ha mindkettő igaz lenne, ellentmondás — az immunrendszer ezt blokkolja.)")
    if not registry.logical_negation_pairs:
        lines.append("(nincs megadva)")
    else:
        for a, b in registry.logical_negation_pairs:
            sa = registry.get_spec(a)
            sb = registry.get_spec(b)
            ida = sa.id if sa else str(a)
            idb = sb.id if sb else str(b)
            lines.append(f"  • {ida}  <->  {idb}")

    lines.append("")
    lines.append("=== Tiltott irányított élek ===")
    lines.append("(Ezek az irányt soha nem vesszük fel explicit kauzális élként.)")
    if not registry.forbidden_edges:
        lines.append("(nincs megadva)")
    else:
        for i, j in sorted(registry.forbidden_edges):
            si = registry.get_spec(i)
            sj = registry.get_spec(j)
            idi = si.id if si else str(i)
            idj = sj.id if sj else str(j)
            lines.append(f"  • {idi} -> {idj}")

    lines.append("")
    lines.append("=== Kauzális élek (regiszter, induláskor) ===")
    lines.append(f"  • {len(registry.causal_edges)} darab explicit i->j él")
    return "\n".join(lines)


def list_axioms(registry: AxiomRegistry, domain: Optional[str] = None) -> str:
    """Összes axióma vagy egy domain szűréssel."""
    dom = (domain or "").strip().upper()
    lines: list[str] = []
    lines.append("=== Axiómák (csúcsok) ===")
    n = 0
    for spec in registry.nodes:
        if dom and spec.domain.upper() != dom:
            continue
        n += 1
        kw = ", ".join(spec.keywords[:5])
        if len(spec.keywords) > 5:
            kw += ", …"
        lines.append(f"  [{spec.id}] {spec.domain} — {spec.formula}")
        if kw:
            lines.append(f"      kulcsszavak: {kw}")
    if n == 0:
        return "Nincs ilyen domain vagy üres a regiszter." if dom else "Üres regiszter."
    lines.insert(1, f"Összesen: {n} csúcs" + (f" (domain={dom})" if dom else ""))
    return "\n".join(lines)


def roadmap_snippet() -> str:
    """Rövid útiter; részletek: ROADMAP.md"""
    return """=== Útiterv (rövid) ===
Fázis 1: szabályok (/szabályok) — KÉSZ
Fázis 2: válasz + /indoklás — KÉSZ
Fázis 3: JSONL + /hipotézis-sync — KÉSZ alap
Fázis 4: regiszter bővítése (matek/fizika + nyelv) — KÉSZ
Fázis 5: önjavítás (source_trust, /jó /rossz) — KÉSZ alap
Fázis 6: Fisher-sweep (tools/telemetry_fisher_sweep.py) + HTTP API (aie_http_server.py) — KÉSZ alap

Teljes leírás: ROADMAP.md
"""


def format_indoklas_hu(result: InferenceResult) -> str:
    """
    Utolsó sikeres derive_statement: lánc és formulák magyar magyarázata.
    (A teljes ASCII jelentés továbbra is: InferenceResult.format_report_ascii.)
    """
    qv = result.q_at_inference if result.q_at_inference is not None else result.q_density
    nv = result.n_star_at_inference if result.n_star_at_inference is not None else result.n_star
    lines: list[str] = []
    lines.append("=== Indoklás (utolsó következtetés) ===")
    lines.append("")
    lines.append(f"Bemenet: {result.input_text!r}")
    lines.append(f"Ítélet: {result.verdict}")
    lines.append("")
    lines.append(
        "A motor a gráf aktuális Q értéke alapján kijelölt egy axióma-láncot "
        "(rövid út a bemenethez kötött csúcstól egy cél felé)."
    )
    lines.append("")
    if result.path_axiom_ids:
        lines.append("Lánc (axióma-id-k és formulák):")
        ids = result.path_axiom_ids
        forms = result.path_formulas
        for i, axid in enumerate(ids):
            fm = forms[i] if i < len(forms) else ""
            lines.append(f"  {i + 1}. [{axid}]  {fm}")
    else:
        lines.append("(Nincs részletes út — csak lokális összegzés.)")
    lines.append("")
    lines.append(f"Fő formula (cél): {result.primary_formula or '(nincs)'}")
    lines.append(f"N* ~ {nv:.4f}  |  Q ~ {qv:.4f}  |  forrás megbízhatóság: {result.source_reliability:.3f}")
    lines.append("")
    lines.append("--- Technikai összegzés (ugyanaz, mint a válaszban) ---")
    lines.append(result.format_report_ascii())
    return "\n".join(lines)
