"""
Kontroll-regiszterek generálása az AIE-tézis falszifikációjához.

Két baseline:
- random_registry: véletlen irányított gráf, minden tiltás/negáció eltávolítva.
  Itt sem topológiai mélység, sem aszimmetria nem kéne emergáljon a tézis szerint.
- symmetric_immunity_registry: a forbidden_edges szimmetrikussá téve (ha (i,j) tilos,
  (j,i) is tilos), a logical_negation_pairs megtartva. Az immunrendszer így nem
  preferálja az egyik irányt — a tézis szerint az ASYM nem nőhet 1.0-ig.

A kimenet az axioms_registry.json-nal kompatibilis (lásd axiom_registry.py).
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _node(idx: int, domain: str) -> Dict[str, Any]:
    return {
        "id": f"rand_{idx}",
        "domain": domain,
        "formula": "",
        "variables": [],
        "keywords": [f"rand_{idx}"],
    }


def random_registry(
    n_nodes: int,
    edge_density: float,
    seed: int,
    domains: Tuple[str, ...] = ("LOGIC", "QM", "INFO", "Newtoni-mechanika"),
) -> Dict[str, Any]:
    """
    Véletlen irányított gráf, kontroll baseline.

    - n_nodes csúcs, edge_density valószínűséggel él (i!=j) minden rendezett párra.
    - Nincs forbidden_edges, nincs logical_negation_pairs.
    - Domain címkék körkörösen kiosztva (a makro-mikro távolság értelmes maradjon).
    """
    rng = random.Random(seed)
    nodes = [_node(i, domains[i % len(domains)]) for i in range(n_nodes)]
    edges: List[List[str]] = []
    for i in range(n_nodes):
        for j in range(n_nodes):
            if i == j:
                continue
            if rng.random() < edge_density:
                edges.append([f"rand_{i}", f"rand_{j}"])
    return {
        "version": "control-random-1.0",
        "schema_version": 1,
        "description": (
            f"Random kontroll: {n_nodes} csúcs, density={edge_density}, seed={seed}"
        ),
        "nodes": nodes,
        "logical_negation_pairs": [],
        "causal_edges": edges,
        "forbidden_edges": [],
    }


def dense_synthetic_registry(
    n_nodes: int = 15,
    n_forbidden: int = 10,
    n_negation: int = 10,
    seed: int = 1,
) -> Dict[str, Any]:
    """
    Kicsi, sűrű, szintetikus tézis-regiszter B kísérlethez:
    - kauzális gerinc (lánc + néhány ág) ad strukturáltságot,
    - n_forbidden visszafelé-él tilalom (i+k -> i típusú visszamenés),
    - n_negation negáció-pár távoli csúcsok között,
      hogy a discovery hipotézis-élek ténylegesen aktiválják a contradiction-t.

    A fő kérdés: ezen a regiszteren ténylegesen aktiválódik-e az immunrendszer
    (RRR > 0)? Ha igen, akkor a no_immune / random_immune kar TOPO-eltérése
    értelmezhető. Ha nem, az immun-tézis empirikusan halott ezen a motoron.
    """
    rng = random.Random(seed)
    # Csak diagnosztika: használjuk a 15 csúcs azonosítóit
    # 4 domain ciklikusan, hogy makro-mikro távolság értelmezhető legyen
    domains = ("LOGIC", "QM", "INFO", "Newtoni-mechanika")
    nodes: List[Dict[str, Any]] = []
    for i in range(n_nodes):
        nodes.append({
            "id": f"d_{i}",
            "domain": domains[i % len(domains)],
            "formula": "",
            "variables": [],
            "keywords": [f"d_{i}"],
        })

    # Kauzális gerinc: lánc 0->1->...->n-1
    causal: List[List[str]] = [[f"d_{i}", f"d_{i+1}"] for i in range(n_nodes - 1)]
    # + néhány ág (i -> i+2) hogy a TOPO/branching interesting legyen
    for i in range(0, n_nodes - 2, 3):
        causal.append([f"d_{i}", f"d_{i+2}"])

    causal_set = {tuple(p) for p in causal}

    # Forbidden: visszafelé élek, i+k -> i, k>=2 — mindenképp ellentmondanának a gerincnek
    forbidden: List[List[str]] = []
    used_forbidden: set = set()
    candidates: List[Tuple[int, int]] = [
        (j, i) for i in range(n_nodes) for j in range(i + 2, n_nodes)
    ]
    rng.shuffle(candidates)
    for src, dst in candidates:
        if len(forbidden) >= n_forbidden:
            break
        pair = (f"d_{src}", f"d_{dst}")
        if pair in used_forbidden or pair in causal_set:
            continue
        forbidden.append(list(pair))
        used_forbidden.add(pair)

    # Negation pairs: távoli csúcsok (legalább 3 lépés távolságra a gerincben)
    negation: List[List[str]] = []
    used_neg: set = set()
    neg_candidates: List[Tuple[int, int]] = [
        (i, j)
        for i in range(n_nodes)
        for j in range(i + 3, n_nodes)
    ]
    rng.shuffle(neg_candidates)
    for a, b in neg_candidates:
        if len(negation) >= n_negation:
            break
        key = frozenset((a, b))
        if key in used_neg:
            continue
        negation.append([f"d_{a}", f"d_{b}"])
        used_neg.add(key)

    return {
        "version": f"dense-thesis-{n_nodes}n-{n_forbidden}f-{n_negation}neg-seed{seed}",
        "schema_version": 1,
        "description": (
            f"Sűrű szintetikus tézis-regiszter B kísérlethez: {n_nodes} csúcs, "
            f"{len(causal)} causal él, {n_forbidden} forbidden, {n_negation} negáció."
        ),
        "nodes": nodes,
        "logical_negation_pairs": negation,
        "causal_edges": causal,
        "forbidden_edges": forbidden,
    }


def no_immune_registry(source_path: Path) -> Dict[str, Any]:
    """
    Strukturált regiszter (timeless) MINDEN immun-mechanizmus nélkül:
    forbidden_edges és logical_negation_pairs = []. Ez a kontroll teszteli, hogy
    az immunrendszer MEGLÉTE szükséges-e a TOPO-mélyüléshez.
    """
    with source_path.open(encoding="utf-8") as f:
        data = json.load(f)
    data["forbidden_edges"] = []
    data["logical_negation_pairs"] = []
    data["version"] = data.get("version", "") + "+no-immune"
    data["schema_version"] = data.get("schema_version", 1)
    data["description"] = (
        (data.get("description", "") + " | Kontroll: immunrendszer kikapcsolva.").strip()
    )
    return data


def random_immune_registry(
    source_path: Path, seed: int
) -> Dict[str, Any]:
    """
    Strukturált regiszter (timeless) UGYANANNYI tilalommal, de RANDOM párokkal.
    Teszteli, hogy az immunrendszer SPECIFIKUSSÁGA számít-e (nem csak a megléte).

    - forbidden_edges: ugyanannyi pár, random módon kiválasztva (i!=j, nem már
      causal_edge, nem már negation_pair).
    - logical_negation_pairs: ugyanannyi pár, random módon (i!=j, nem ütközik
      a már kiosztott párokkal).
    """
    with source_path.open(encoding="utf-8") as f:
        data = json.load(f)
    rng = random.Random(seed)
    node_ids = [n["id"] for n in data["nodes"]]
    n_forbidden = len(data.get("forbidden_edges", []))
    n_negation = len(data.get("logical_negation_pairs", []))

    causal_set = {(a, b) for a, b in data.get("causal_edges", [])}
    used_ordered: set = set()  # foglalt irányított párok (forbidden)
    used_unordered: set = set()  # foglalt rendezetlen párok (negation)

    def _random_pair() -> Tuple[str, str]:
        for _ in range(10000):
            a, b = rng.sample(node_ids, 2)
            if (a, b) in causal_set or (b, a) in causal_set:
                continue
            if (a, b) in used_ordered:
                continue
            if frozenset((a, b)) in used_unordered:
                continue
            return a, b
        raise RuntimeError("Nem találtam szabad random párt — túl kevés csúcs?")

    new_forbidden: List[List[str]] = []
    for _ in range(n_forbidden):
        a, b = _random_pair()
        used_ordered.add((a, b))
        new_forbidden.append([a, b])

    new_negation: List[List[str]] = []
    for _ in range(n_negation):
        a, b = _random_pair()
        used_unordered.add(frozenset((a, b)))
        new_negation.append([a, b])

    data["forbidden_edges"] = new_forbidden
    data["logical_negation_pairs"] = new_negation
    data["version"] = data.get("version", "") + f"+random-immune-seed{seed}"
    data["schema_version"] = data.get("schema_version", 1)
    data["description"] = (
        (data.get("description", "") + f" | Kontroll: random immun (seed={seed}).").strip()
    )
    return data


def symmetric_immunity_registry(
    source_path: Path,
) -> Dict[str, Any]:
    """
    Az eredeti regiszterből indul, de minden forbidden_edge szimmetrikus lesz:
    ha (i,j) tilos, (j,i) is tilos. Ez kioltja az immunrendszer irány-preferenciáját.
    A logical_negation_pairs megmarad (azok eleve szimmetrikusak).
    """
    with source_path.open(encoding="utf-8") as f:
        data = json.load(f)
    forbidden: List[List[str]] = list(data.get("forbidden_edges", []))
    seen = {tuple(p) for p in forbidden}
    extra: List[List[str]] = []
    for a, b in forbidden:
        if (b, a) not in seen:
            extra.append([b, a])
            seen.add((b, a))
    data["forbidden_edges"] = forbidden + extra
    data["version"] = data.get("version", "") + "+symmetric-immunity"
    data["schema_version"] = data.get("schema_version", 1)
    data["description"] = (
        (data.get("description", "") + " | Kontroll: szimmetrikus immunrendszer.").strip()
    )
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Kontroll-regiszterek generálása.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_rand = sub.add_parser("random", help="Véletlen irányított gráf.")
    p_rand.add_argument("--n-nodes", type=int, default=40)
    p_rand.add_argument("--edge-density", type=float, default=0.04)
    p_rand.add_argument("--seed", type=int, required=True)
    p_rand.add_argument("--out", type=Path, required=True)

    p_sym = sub.add_parser("symmetric", help="Szimmetrikus immunrendszer baseline.")
    p_sym.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "axioms_registry.json",
    )
    p_sym.add_argument("--out", type=Path, required=True)

    p_noi = sub.add_parser("no_immune", help="Strukturált, immunrendszer nélkül.")
    p_noi.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "axioms_registry_timeless.json",
    )
    p_noi.add_argument("--out", type=Path, required=True)

    p_dense = sub.add_parser("dense_thesis", help="Kicsi, sűrű szintetikus tézis-regiszter (B kísérlet).")
    p_dense.add_argument("--n-nodes", type=int, default=15)
    p_dense.add_argument("--n-forbidden", type=int, default=10)
    p_dense.add_argument("--n-negation", type=int, default=10)
    p_dense.add_argument("--seed", type=int, default=1)
    p_dense.add_argument("--out", type=Path, required=True)

    p_rim = sub.add_parser("random_immune", help="Strukturált, random immunrendszer.")
    p_rim.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "axioms_registry_timeless.json",
    )
    p_rim.add_argument("--seed", type=int, required=True)
    p_rim.add_argument("--out", type=Path, required=True)

    args = ap.parse_args()
    if args.cmd == "random":
        data = random_registry(args.n_nodes, args.edge_density, args.seed)
    elif args.cmd == "symmetric":
        data = symmetric_immunity_registry(args.source)
    elif args.cmd == "no_immune":
        data = no_immune_registry(args.source)
    elif args.cmd == "random_immune":
        data = random_immune_registry(args.source, args.seed)
    elif args.cmd == "dense_thesis":
        data = dense_synthetic_registry(
            n_nodes=args.n_nodes,
            n_forbidden=args.n_forbidden,
            n_negation=args.n_negation,
            seed=args.seed,
        )
    else:
        ap.error(f"ismeretlen alparancs: {args.cmd}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
