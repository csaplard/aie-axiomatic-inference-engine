"""
Gráf-metrikák: topológiai mélység (leghosszabb irányított út), aszimmetria-arány.
Kis n (axióma-mátrix) — O(n²) / SCC + DAG DP.
"""

from __future__ import annotations

from collections import deque
from typing import List, Set, Tuple

import numpy as np


def _build_adj_offdiag(A: np.ndarray) -> Tuple[int, List[List[int]]]:
    m = np.asarray(A, dtype=np.float64).copy()
    np.fill_diagonal(m, 0.0)
    n = m.shape[0]
    adj: List[List[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j and m[i, j] > 0:
                adj[i].append(j)
    return n, adj


def _longest_path_vertex_count_dag(n: int, adj: List[List[int]]) -> int:
    """Irányított körmentes gráf: leghosszabb út csúcsszáma."""
    indeg = [0] * n
    for u in range(n):
        for v in adj[u]:
            indeg[v] += 1
    q = deque([i for i in range(n) if indeg[i] == 0])
    indeg2 = indeg[:]
    topo: List[int] = []
    while q:
        u = int(q.popleft())
        topo.append(u)
        for v in adj[u]:
            indeg2[v] -= 1
            if indeg2[v] == 0:
                q.append(v)
    if len(topo) != n:
        return -1  # nem DAG
    dp = [1] * n
    for u in topo:
        for v in adj[u]:
            dp[v] = max(dp[v], dp[u] + 1)
    return int(max(dp)) if n else 0


def _kosaraju_components(n: int, adj: List[List[int]]) -> Tuple[List[int], int]:
    """comp[u] = SCC azonosító; vissza: comp, n_comp."""
    visited = [False] * n
    order: List[int] = []

    def dfs1(u: int) -> None:
        visited[u] = True
        for v in adj[u]:
            if not visited[v]:
                dfs1(v)
        order.append(u)

    for u in range(n):
        if not visited[u]:
            dfs1(u)

    radj: List[List[int]] = [[] for _ in range(n)]
    for u in range(n):
        for v in adj[u]:
            radj[v].append(u)

    comp = [-1] * n
    cid = 0

    def dfs2(u: int, c: int) -> None:
        comp[u] = c
        for v in radj[u]:
            if comp[v] == -1:
                dfs2(v, c)

    for u in reversed(order):
        if comp[u] == -1:
            dfs2(u, cid)
            cid += 1
    return comp, cid


def _condensation_longest_weighted_path(n: int, adj: List[List[int]], comp: List[int], n_comp: int) -> int:
    """SCC kondenzáció: súly = |SCC|, leghosszabb súlyozott út a DAG-on."""
    sizes = [0] * n_comp
    for u in range(n):
        sizes[comp[u]] += 1

    cadj: List[Set[int]] = [set() for _ in range(n_comp)]
    for u in range(n):
        for v in adj[u]:
            cu, cv = comp[u], comp[v]
            if cu != cv:
                cadj[cu].add(cv)

    indeg = [0] * n_comp
    for u in range(n_comp):
        for v in cadj[u]:
            indeg[v] += 1
    q = deque([i for i in range(n_comp) if indeg[i] == 0])
    indeg2 = indeg[:]
    topo: List[int] = []
    while q:
        u = int(q.popleft())
        topo.append(u)
        for v in cadj[u]:
            indeg2[v] -= 1
            if indeg2[v] == 0:
                q.append(v)
    if len(topo) != n_comp:
        return max(sizes) if n_comp else 0

    w = sizes
    dp = [w[i] for i in range(n_comp)]
    for u in topo:
        for v in cadj[u]:
            dp[v] = max(dp[v], dp[u] + w[v])
    return int(max(dp)) if n_comp else 0


def topological_depth(A: np.ndarray) -> int:
    """
    Leghosszabb irányított út hossza (csúcsok száma) — becslés.
    DAG esetén pontos; kör esetén SCC kondenzáció + |SCC| súlyokkal (heurisztika).
    Üres élhalmaz: 1 (egyetlen csúcs).
    """
    n, adj = _build_adj_offdiag(A)
    if n == 0:
        return 0
    edge_count = sum(len(adj[u]) for u in range(n))
    if edge_count == 0:
        return 1
    d = _longest_path_vertex_count_dag(n, adj)
    if d >= 0:
        return d
    comp, n_comp = _kosaraju_components(n, adj)
    return _condensation_longest_weighted_path(n, adj, comp, n_comp)


def asymmetry_ratio(A: np.ndarray) -> float:
    """
    Egyirányú irányított élek aránya az összes (i!=j) él között:
    csak akkor számít 'aszimmetrikusnak', ha a fordított irány nincs meg.
    """
    m = np.asarray(A, dtype=np.float64).copy()
    np.fill_diagonal(m, 0.0)
    n = m.shape[0]
    tot = 0
    asym = 0
    for i in range(n):
        for j in range(n):
            if i == j or m[i, j] <= 0:
                continue
            tot += 1
            if m[j, i] <= 0:
                asym += 1
    if tot == 0:
        return 1.0
    return float(asym / tot)


def reverse_rejection_rate(attempts: int, rejects: int) -> float:
    """Visszafordíthatósági ellenállás: elutasítás / próba (0..1)."""
    if attempts <= 0:
        return 0.0
    return float(min(1.0, rejects / attempts))
