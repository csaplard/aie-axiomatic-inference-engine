"""
AXIOM-KERNEL-BETA-0.77 — Axiomatikus következtető gép (AIE) vázlat.
Q-sűrűség: szomszédsági mátrix alapján; küszöb: 0.77 (konfigurálható).
"""

from __future__ import annotations

import hashlib
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional, Tuple, Union

import numpy as np

import graph_metrics

import edge_trust

from axiom_registry import AxiomRegistry
from policy_manager import PolicyManager
from self_optimization import (
    OptimizationSuggestion,
    SelfOptimizationAdvisor,
    SystemMetrics,
)


class AxiomDomain(str, Enum):
    LOGIC = "LOGIC"
    ZFC = "ZFC"
    THERMO = "Termodinamika"
    NEWTON = "Newtoni-mechanika"
    CLASSICAL_MECH = "CLASSICAL_MECH"
    MAXWELL = "Maxwell-egyenletek"
    RELATIVITY = "RELATIVITY"
    QM = "QM"
    INFO = "INFO"
    UNSUPPORTED = "nem_horgonyozott"


# Makro (klasszikus kontinuum) vs mikro (kvantum / információ) — feszültségmérő csoportosítás.
MACRO_DOMAIN_LABELS: Tuple[str, ...] = (
    AxiomDomain.CLASSICAL_MECH.value,
    AxiomDomain.NEWTON.value,
    AxiomDomain.RELATIVITY.value,
)
MICRO_DOMAIN_LABELS: Tuple[str, ...] = (
    AxiomDomain.QM.value,
    AxiomDomain.INFO.value,
)


STRUCTURAL_GAP_MSG = (
    "Strukturális hiány: Nincs elegendő összefüggés a küszöb (N*) átlépéséhez."
)


def calculate_q_density(matrix: np.ndarray) -> float:
    """
    Irányított élek sűrűsége: csak i≠j cellák (a diagonális axióma-önhivatkozás nem él).
    Nevező: n*(n-1) lehetséges irányított él.
    """
    m = np.asarray(matrix, dtype=np.float64).copy()
    np.fill_diagonal(m, 0.0)
    edges = np.count_nonzero(m)
    nodes = m.shape[0]
    total_possible = nodes * (nodes - 1)
    if total_possible <= 0:
        return 0.0
    return float(edges / total_possible)


def input_entropy_h0(text: str) -> float:
    """Egyszerű normalizált entrópia-proxi (karakter-szintű bitek / 8)."""
    if not text:
        return 0.0
    counts: Dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(text)
    h_bits = 0.0
    for c in counts.values():
        p = c / n
        h_bits -= p * math.log2(p)
    return min(1.0, h_bits / 8.0)


def input_entropy_shannon_h0(text: str) -> float:
    """Shannon H(X) = -sum p_i log2(p_i); 0..1 a H_max = log2(K) normalizálással (K szimbólum)."""
    if not text:
        return 0.0
    counts: Dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(text)
    h = 0.0
    for c in counts.values():
        p = c / n
        h -= p * math.log2(p)
    k = len(counts)
    if k <= 1:
        return 0.0
    h_max = math.log2(k)
    return min(1.0, h / h_max)


@dataclass
class InferenceResult:
    """Strukturált igazolás: lánc, formulák, Q/N* (ASCII statement mező)."""

    statement: str
    q_density: float
    n_star: float
    causal_chain: List[Tuple[int, int]]
    h0: float
    b_eff: float
    c_coherence: float
    input_text: str = ""
    verdict: str = ""
    path_indices: List[int] = field(default_factory=list)
    path_axiom_ids: List[str] = field(default_factory=list)
    path_formulas: List[str] = field(default_factory=list)
    primary_formula: str = ""
    q_at_inference: Optional[float] = None
    n_star_at_inference: Optional[float] = None
    source_reliability: float = 1.0

    def format_report_ascii(self) -> str:
        """Egybefüggő jelentés: INPUT / RESULT / PATH / N* és Q / FORMULA."""
        qv = self.q_at_inference if self.q_at_inference is not None else self.q_density
        nv = self.n_star_at_inference if self.n_star_at_inference is not None else self.n_star
        path_s = " -> ".join(self.path_axiom_ids) if self.path_axiom_ids else "(nincs ut)"
        lines = [
            f"INPUT: {self.input_text!r}",
            f"RESULT: {self.verdict}",
            f"PATH: {path_s}",
            f"N / Q: {nv:.4f} / {qv:.4f}",
            f"FORMULA: {self.primary_formula}",
        ]
        return "\n".join(lines)


@dataclass
class ThinkStepSnapshot:
    """Utolsó befejezett think_step: mit próbált, sikerült-e tranzitív igazolás, lett-e él."""

    tick: int = 0
    mode: str = "init"  # heuristic | random_pair | idle_sparse
    i: Optional[int] = None
    j: Optional[int] = None
    verified: Optional[bool] = None
    edge_added: bool = False
    # discovery.enabled: verify nem, de immun OK → hipotézis él (add_edge_if_proven)
    abductive: bool = False
    # new_edge=nem esetén: forbidden | exists | contradiction | no_hypothesis | None (idle)
    edge_reject: Optional[str] = None
    q: float = 0.0


@dataclass
class _ThinkPending:
    mode: str = "init"
    i: Optional[int] = None
    j: Optional[int] = None
    verified: Optional[bool] = None
    edge_added: bool = False
    abductive: bool = False
    edge_reject: Optional[str] = None


def _domain_from_string(s: str) -> AxiomDomain:
    try:
        return AxiomDomain(s)
    except ValueError:
        return AxiomDomain.UNSUPPORTED


@dataclass
class AxiomaticInferenceEngine:
    """
    AIE: axióma-mátrix + Q-küszöb + belső gondolkodási hurok.
    B: backend hatékonyság (0..1), C: koherencia (0..1) — N* = H0*B*C/sqrt(Q).
    """

    n_nodes: int = 64
    q_threshold: float = 0.77
    backend_efficiency_b: float = 0.85
    coherence_c: float = 0.9
    sleep_s: float = 0.01
    use_axiom_registry: bool = True
    registry_path: Optional[str] = None
    use_shannon_entropy: bool = True
    use_heuristic_thinking: bool = True
    source_trust_penalty: float = 0.85
    enable_self_optimization: bool = False
    policy_enabled: bool = False
    policy_path: Optional[str] = None

    knowledge_matrix: np.ndarray = field(init=False)
    axiom_labels: Dict[int, AxiomDomain] = field(default_factory=dict)
    _registry: Optional[AxiomRegistry] = field(init=False, default=None)
    # priority_weight csúcsonként (np.array, len=n_nodes); None, ha nincs regiszter
    _node_priority: Optional[np.ndarray] = field(init=False, default=None)
    _negation: Dict[int, int] = field(init=False, default_factory=dict)
    _source_trust: Dict[str, float] = field(init=False, default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _think_thread: Optional[threading.Thread] = None
    _is_thinking: bool = False
    _on_awakening: Optional[Callable[[float], None]] = None
    _opt: Optional[SelfOptimizationAdvisor] = field(init=False, default=None)
    _policy: Optional[PolicyManager] = field(init=False, default=None)
    _seed_hamilton_ring: bool = field(init=False, default=True)
    _think_step_counter: int = field(init=False, default=0)
    _last_think_snapshot: ThinkStepSnapshot = field(init=False)
    _think_pending: _ThinkPending = field(init=False, default_factory=_ThinkPending)

    def __post_init__(self) -> None:
        self._load_registry()
        self._build_negation_map()
        if self._registry is not None:
            override = getattr(self._registry, "n_nodes_override", None)
            if override is not None and override > 0:
                # A regiszter explicit méretet ír elő (pl. confound-free kísérlet)
                self.n_nodes = max(int(override), self._registry.n_axioms)
            else:
                self.n_nodes = max(self.n_nodes, self._registry.n_axioms)
        self.knowledge_matrix = np.eye(self.n_nodes, dtype=np.float64)
        self._seed_hamilton_ring = True
        self._think_step_counter = 0
        self._last_think_snapshot = ThinkStepSnapshot()
        self._think_pending = _ThinkPending()
        self._reverse_attempt_count = 0
        self._reverse_reject_contradiction_count = 0
        self._load_policy()
        if self._policy is not None:
            self._seed_hamilton_ring = self._policy.seed_hamilton_ring
            seed = self._policy.random_seed
            if seed is not None:
                np.random.seed(int(seed))
                import random as _py_random
                _py_random.seed(int(seed))
        self._seed_axioms()
        if self.enable_self_optimization:
            self._opt = SelfOptimizationAdvisor(
                q_threshold=self.q_threshold,
                policy=self._policy,
            )
            if self._policy is not None:
                self._opt.sync_from_policy(self._policy)

    def _load_policy(self) -> None:
        self._policy = None
        if not self.policy_enabled:
            return
        p = (
            Path(self.policy_path)
            if self.policy_path
            else Path(__file__).resolve().parent / "agi_policy.yaml"
        )
        self._policy = PolicyManager(p)
        self._policy.load()
        self.q_threshold = self._policy.q_threshold_base
        self.sleep_s = self._policy.sleep_s_base

    def _apply_policy_from_manager(self) -> None:
        if self._policy is None:
            return
        self.q_threshold = self._policy.q_threshold_base
        self.sleep_s = self._policy.sleep_s_base
        if self._opt is not None:
            self._opt.sync_from_policy(self._policy)

    def _build_negation_map(self) -> None:
        self._negation = {}
        if self._registry is None:
            return
        for a, b in self._registry.logical_negation_pairs:
            self._negation[a] = b
            self._negation[b] = a

    def _load_registry(self) -> None:
        self._registry = None
        if not self.use_axiom_registry:
            return
        try:
            if self.registry_path:
                self._registry = AxiomRegistry(Path(self.registry_path))
            else:
                p = Path(__file__).resolve().parent / "axioms_registry.json"
                if p.exists():
                    self._registry = AxiomRegistry(p)
        except (OSError, ValueError, KeyError):
            self._registry = None

    def _weighted_pair_choice(
        self, candidates: np.ndarray
    ) -> Optional[np.ndarray]:
        """Két csúcs választása a candidates-ból, súlyozva _node_priority szerint.
        Ha nincs priority, vagy minden súly nulla, uniformra esik vissza."""
        if candidates.size < 2:
            return None
        if self._node_priority is None:
            return np.random.choice(candidates, size=2, replace=False)
        weights = self._node_priority[candidates]
        s = float(weights.sum())
        if s <= 0:
            return np.random.choice(candidates, size=2, replace=False)
        p = weights / s
        return np.random.choice(candidates, size=2, replace=False, p=p)

    def _weighted_index_pick(self, candidates: np.ndarray) -> int:
        """Egy csúcs súlyozott választása (heurisztika high/low partícióinak).
        Uniformra esik vissza priority hiányában vagy nulla-súlyú esetén."""
        if candidates.size == 0:
            return -1
        if self._node_priority is None:
            return int(np.random.choice(candidates))
        weights = self._node_priority[candidates]
        s = float(weights.sum())
        if s <= 0:
            return int(np.random.choice(candidates))
        p = weights / s
        return int(np.random.choice(candidates, p=p))

    def _seed_axioms(self) -> None:
        """Regiszter: kauzális élek + címkék + Hamilton-gyűrű; egyébként alap domain + gyűrű."""
        n = self.n_nodes
        if self._registry is not None:
            for spec in self._registry.nodes:
                self.axiom_labels[spec.index] = _domain_from_string(spec.domain)
            for i, j in self._registry.causal_edges:
                if i < n and j < n:
                    self.knowledge_matrix[i, j] = 1.0
            # priority_weight betöltése (default 0.5 ott, ahol hiányzik)
            pri = np.full(n, 0.5, dtype=np.float64)
            for spec in self._registry.nodes:
                if spec.index < n:
                    pri[spec.index] = float(spec.priority_weight)
            self._node_priority = pri
        else:
            domains = [
                AxiomDomain.ZFC,
                AxiomDomain.THERMO,
                AxiomDomain.NEWTON,
                AxiomDomain.MAXWELL,
            ]
            for i, d in enumerate(domains):
                if i < n:
                    self.axiom_labels[i] = d
        if self._seed_hamilton_ring:
            for i in range(n):
                j = (i + 1) % n
                self.knowledge_matrix[i, j] = 1.0

    def _resolve_policy_relative_path(self, rel: str) -> Path:
        if self._policy is None:
            return Path(rel)
        p = Path(rel)
        if p.is_absolute():
            return p
        return self._policy.path.parent / p

    def _build_system_metrics(self) -> SystemMetrics:
        with self._lock:
            m = self.knowledge_matrix.copy()
            np.fill_diagonal(m, 0.0)
            nnz = int(np.count_nonzero(m))
            q = calculate_q_density(self.knowledge_matrix)
            ra = self._reverse_attempt_count
            rr = self._reverse_reject_contradiction_count
            A = self.knowledge_matrix.copy()
        topo = graph_metrics.topological_depth(A)
        asym = graph_metrics.asymmetry_ratio(A)
        rrr = graph_metrics.reverse_rejection_rate(ra, rr)
        tps = self._opt.think_steps_per_second() if self._opt else 0.0
        dd: Optional[float] = None
        if self._registry is not None:
            dd = self.calculate_domain_distance(list(MACRO_DOMAIN_LABELS), list(MICRO_DOMAIN_LABELS))
        return SystemMetrics(
            q=q,
            q_threshold=self.q_threshold,
            n_nodes=self.n_nodes,
            nnz_offdiag=nnz,
            backend_efficiency_b=self.backend_efficiency_b,
            sleep_s=self.sleep_s,
            think_steps_per_sec=tps,
            domain_distance_macro_micro=dd,
            topological_depth=topo,
            asymmetry_ratio=asym,
            reverse_rejection_rate=rrr,
            reverse_attempts=ra,
            reverse_rejects_contradiction=rr,
        )

    def _after_think_step_record(self) -> None:
        if self._opt is None:
            return
        self._opt.record(self._build_system_metrics())

    def _finalize_think_step(self, q: float) -> None:
        self._think_step_counter += 1
        with self._lock:
            self._last_think_snapshot = ThinkStepSnapshot(
                tick=self._think_step_counter,
                mode=self._think_pending.mode,
                i=self._think_pending.i,
                j=self._think_pending.j,
                verified=self._think_pending.verified,
                edge_added=self._think_pending.edge_added,
                abductive=self._think_pending.abductive,
                edge_reject=self._think_pending.edge_reject,
                q=q,
            )
        self._after_think_step_record()
        self._maybe_telemetry_log(q)

    def _maybe_telemetry_log(self, q: float) -> None:
        if self._policy is None or not self._policy.telemetry_enabled:
            return
        every = max(1, self._policy.telemetry_every_n_steps)
        if self._think_step_counter % every != 0:
            return
        d = self.calculate_domain_distance(list(MACRO_DOMAIN_LABELS), list(MICRO_DOMAIN_LABELS))
        ds = "inf" if math.isinf(d) else str(int(d))
        with self._lock:
            A = self.knowledge_matrix.copy()
            ra = self._reverse_attempt_count
            rr = self._reverse_reject_contradiction_count
        topo = graph_metrics.topological_depth(A)
        asym = graph_metrics.asymmetry_ratio(A)
        rrr = graph_metrics.reverse_rejection_rate(ra, rr)
        # Priority partíció — csak akkor logoljuk, ha van priority-vektor
        partition_part = ""
        if self._node_priority is not None:
            try:
                topo_h, topo_l, ratio = graph_metrics.topological_depth_partition(
                    A, self._node_priority
                )
                partition_part = (
                    f" | TOPO_HIGH={topo_h} | TOPO_LOW={topo_l} | "
                    f"TOPO_RATIO={ratio:.4f}"
                )
            except Exception:
                partition_part = ""
        line = (
            f"PID={os.getpid()} [TICK: {self._think_step_counter}] Q={q:.4f} | "
            f"DIST(MACRO->MICRO)={ds} | B_EFFICIENCY={self.backend_efficiency_b:.2f} | "
            f"TOPO={topo} | RRR={rrr:.4f} | ASYM={asym:.4f}{partition_part}\n"
        )
        path = self._resolve_policy_relative_path(self._policy.telemetry_log_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def evaluate_self_optimization(self) -> List[OptimizationSuggestion]:
        """Q / mátrix / ütemezés alapján javaslatok (ritka tárolás, sleep, B emelés)."""
        if self._opt is None:
            return []
        if self._policy is not None:
            if self._policy.check_and_reload():
                self._apply_policy_from_manager()
        m = self._build_system_metrics()
        return self._opt.collect_suggestions(m, self.knowledge_matrix)

    def apply_backend_efficiency_suggestions(
        self, suggestions: List[OptimizationSuggestion]
    ) -> float:
        """A javasolt dB összegek alkalmazása backend_efficiency_b-re (max 1.0)."""
        if self._opt is None:
            return self.backend_efficiency_b
        new_b = self._opt.apply_suggested_b_delta(self.backend_efficiency_b, suggestions)
        self.backend_efficiency_b = new_b
        return new_b

    def is_edge_forbidden(self, i: int, j: int) -> bool:
        """Ellentmondás / időnyíl: tiltott irányított él (pl. jövő → múlt entrópia)."""
        if self._policy is not None and self._policy.ignore_forbidden_edges:
            return False
        if self._registry is not None and (i, j) in self._registry.forbidden_edges:
            return True
        return False

    def _has_path_unlocked(self, A: np.ndarray, start: int, end: int) -> bool:
        """Irányított út BFS (zároló nélkül)."""
        if start == end:
            return True
        n = A.shape[0]
        seen = {start}
        q = deque([start])
        while q:
            u = int(q.popleft())
            for v in np.nonzero(A[u, :] > 0)[0]:
                v = int(v)
                if v == end:
                    return True
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        return False

    def has_path(self, start: int, end: int) -> bool:
        with self._lock:
            return self._has_path_unlocked(self.knowledge_matrix, start, end)

    def shortest_path(self, start: int, goal: int) -> Optional[List[int]]:
        """Legrövidebb irányított út (BFS)."""
        with self._lock:
            A = self.knowledge_matrix
            n = A.shape[0]
            if start == goal:
                return [start]
            pred = [-1] * n
            pred[start] = start
            q = deque([start])
            found = False
            while q:
                u = int(q.popleft())
                for v in np.nonzero(A[u, :] > 0)[0]:
                    v = int(v)
                    if pred[v] != -1:
                        continue
                    pred[v] = u
                    if v == goal:
                        found = True
                        break
                    q.append(v)
                if found:
                    break
            if not found:
                return None
            out: List[int] = []
            cur = goal
            while cur != start:
                out.append(cur)
                cur = pred[cur]
            out.append(start)
            out.reverse()
            return out

    def calculate_domain_distance(
        self,
        domains_a: Union[str, List[str]],
        domains_b: Union[str, List[str]],
    ) -> float:
        """
        Feszültségmérő: legrövidebb irányított út (él-lépések száma) bármely
        domains_a-beli csúcsból bármely domains_b-beli csúcsba. Nem módosítja a gráfot.
        domains_* lehet egy domain vagy lista (pl. makro vs mikro csoport).
        Vissza: lépésszám, 0 ha van közös csúcs, inf ha nincs út vagy üres domain.
        """
        if isinstance(domains_a, str):
            domains_a = [domains_a]
        if isinstance(domains_b, str):
            domains_b = [domains_b]
        if self._registry is None:
            return float("inf")
        n = self.n_nodes
        set_a = set(domains_a)
        set_b = set(domains_b)
        nodes_a = [
            spec.index
            for spec in self._registry.nodes
            if spec.domain in set_a and spec.index < n
        ]
        nodes_b_set = {
            spec.index
            for spec in self._registry.nodes
            if spec.domain in set_b and spec.index < n
        }
        if not nodes_a or not nodes_b_set:
            return float("inf")
        sa, sb = set(nodes_a), nodes_b_set
        if sa & sb:
            return 0.0
        with self._lock:
            A = self.knowledge_matrix
            visited: Dict[int, int] = {}
            q: deque[int] = deque()
            for s in nodes_a:
                visited[s] = 0
                q.append(s)
            while q:
                u = int(q.popleft())
                if u in nodes_b_set:
                    return float(visited[u])
                for v in np.nonzero(A[u, :] > 0)[0]:
                    v = int(v)
                    if v not in visited:
                        visited[v] = visited[u] + 1
                        q.append(v)
        return float("inf")

    def get_tension_report_ascii(self) -> str:
        """Q + makro <-> mikro domain-távolság (egy soros napló)."""
        q = self.calculate_q()
        d = self.calculate_domain_distance(list(MACRO_DOMAIN_LABELS), list(MICRO_DOMAIN_LABELS))
        if math.isinf(d):
            ds = "inf (nincs iranyitott ut)"
        else:
            ds = f"{int(d)} lepes"
        return f"TENSION_Q={q:.6f} DIST(MACRO->MICRO)={ds}"

    def get_think_snapshot(self) -> ThinkStepSnapshot:
        """Pillanatkép az utolsó lezárt think_step-ről (szál biztonságos másolat)."""
        with self._lock:
            return ThinkStepSnapshot(
                tick=self._last_think_snapshot.tick,
                mode=self._last_think_snapshot.mode,
                i=self._last_think_snapshot.i,
                j=self._last_think_snapshot.j,
                verified=self._last_think_snapshot.verified,
                edge_added=self._last_think_snapshot.edge_added,
                abductive=self._last_think_snapshot.abductive,
                edge_reject=self._last_think_snapshot.edge_reject,
                q=self._last_think_snapshot.q,
            )

    def _axiom_id_for_index(self, idx: Optional[int]) -> str:
        if idx is None:
            return "-"
        if self._registry is not None:
            ax = self._registry.get_axiom_by_index(idx)
            if ax is not None:
                return ax.id
        return str(idx)

    def format_last_think_ascii(self) -> str:
        """Egy sor: utolsó lépés + new_edge=nem oka (reject)."""
        s = self.get_think_snapshot()
        ai = self._axiom_id_for_index(s.i)
        aj = self._axiom_id_for_index(s.j)
        v = "n/a" if s.verified is None else ("igen" if s.verified else "nem")
        e = "igen" if s.edge_added else "nem"
        hyp = "igen" if s.abductive else "nem"
        if s.mode == "idle_sparse":
            rej = "n/a"
        elif s.edge_added:
            rej = "-"
        else:
            rej = s.edge_reject or "?"
        return (
            f"THINK[{s.tick}] mode={s.mode} pair={ai}->{aj} "
            f"verify={v} hyp_edge={hyp} new_edge={e} reject={rej} Q={s.q:.6f}"
        )

    def _would_contradict_edge(self, A: np.ndarray, i: int, j: int) -> bool:
        """Ellentmondás: i->j nem vehető fel, ha már van i->...->neg(j) (A -> B es A -> neg B)."""
        if self._policy is not None and self._policy.ignore_negation_contradictions:
            return False
        neg_j = self._negation.get(j)
        if neg_j is not None and self._has_path_unlocked(A, i, neg_j):
            return True
        return False

    def get_source_reliability(self, source_id: str) -> float:
        return self._source_trust.get(source_id, 1.0)

    def _penalize_source(self, source_id: str) -> float:
        prev = self.get_source_reliability(source_id)
        new = max(0.01, prev * self.source_trust_penalty)
        self._source_trust[source_id] = new
        return new

    def propose_edge_with_source(
        self, source_id: str, i: int, j: int
    ) -> Literal["added", "exists", "forbidden", "contradiction"]:
        """Külső javaslat: ellentmondás esetén a forrás megbízhatósága csökken."""
        if self.is_edge_forbidden(i, j):
            return "forbidden"
        with self._lock:
            A = self.knowledge_matrix
            if A[i, j] > 0:
                return "exists"
            if self._would_contradict_edge(A, i, j):
                self._penalize_source(source_id)
                return "contradiction"
            A[i, j] = 1.0
        self._discovery_log_edge(i, j)
        return "added"

    def map_input_to_axiom(self, raw: str) -> Optional[int]:
        """
        Először kulcsszó → regiszter csúcs; egyébként SHA-256 → index (horgony nélküli bemenet).
        """
        if not raw.strip():
            return None
        if self._registry is not None:
            kw = self._registry.match_keyword(raw)
            if kw is not None:
                return kw
        h = int(hashlib.sha256(raw.encode("utf-8")).hexdigest(), 16)
        return h % self.n_nodes

    def fits_causal_graph(self, i: int, j: int) -> bool:
        """Ellentmondás-mentes illeszkedés: ha már van út vagy explicit él."""
        with self._lock:
            if self.knowledge_matrix[i, j] > 0 or self.knowledge_matrix[j, i] > 0:
                return True
            # Tranzitív út 1 lépésben (köztes csúcs)
            row = self.knowledge_matrix[i, :]
            col = self.knowledge_matrix[:, j]
            return bool(np.any(row * col > 0))

    def filter_input(self, raw: str) -> Tuple[float, Optional[int]]:
        """
        Bemeneti szűrő: H0 + axióma-hozzárendelés. Nem illeszkedő → (H0, None), ne tároljuk.
        """
        h0 = (
            input_entropy_shannon_h0(raw)
            if self.use_shannon_entropy
            else input_entropy_h0(raw)
        )
        idx = self.map_input_to_axiom(raw)
        if idx is None:
            return h0, None
        # Egyszerű szabály: csak nem üres és koherens index
        return h0, idx

    def verify_logic(self, i: int, j: int) -> bool:
        """
        Deduktív szimuláció: tranzitív záró lépés — ha van k közös, i→k és k→j, akkor i→j.
        """
        if i == j:
            return False
        with self._lock:
            A = self.knowledge_matrix
            intermediates = np.where((A[i, :] > 0) & (A[:, j] > 0))[0]
            if intermediates.size == 0:
                return False
            k = int(intermediates[0])
            return bool(A[i, k] > 0 and A[k, j] > 0)

    def deductive_saturate(self) -> int:
        """Tranzitivitás (implies): i→k és k→j ⇒ i→j; tiltott / ellentmondó élek kihagyása."""
        added = 0
        with self._lock:
            A = self.knowledge_matrix
            n = A.shape[0]
            changed = True
            while changed:
                changed = False
                for i in range(n):
                    for j in range(n):
                        if i == j or A[i, j] > 0:
                            continue
                        if self.is_edge_forbidden(i, j):
                            continue
                        if self._would_contradict_edge(A, i, j):
                            continue
                        for k in range(n):
                            if A[i, k] > 0 and A[k, j] > 0:
                                A[i, j] = 1.0
                                added += 1
                                changed = True
                                self._discovery_log_edge(i, j)
                                break
        return added

    def n_star(self, h0: float, q: float) -> float:
        if q <= 1e-12:
            return float("inf") if h0 > 0 else 0.0
        return (h0 * self.backend_efficiency_b * self.coherence_c) / math.sqrt(q)

    def calculate_q(self) -> float:
        with self._lock:
            return calculate_q_density(self.knowledge_matrix)

    def _try_add_edge_with_reason(self, i: int, j: int) -> Tuple[bool, Optional[str]]:
        """
        Él felvétele tiltás/negáció nélkül. Vissza: (True, None) ha felkerült;
        (False, 'forbidden'|'exists'|'contradiction') ha nem.
        „Vissza” próba: ha már van j→…→i út és i→j-et próbálunk — reverse számlálók (RRR).
        """
        if self.is_edge_forbidden(i, j):
            return False, "forbidden"
        with self._lock:
            A = self.knowledge_matrix
            if A[i, j] > 0:
                return False, "exists"
            is_reverse = self._has_path_unlocked(A, j, i)
            if is_reverse:
                self._reverse_attempt_count += 1
            if self._would_contradict_edge(A, i, j):
                if is_reverse:
                    self._reverse_reject_contradiction_count += 1
                return False, "contradiction"
            A[i, j] = 1.0
        self._discovery_log_edge(i, j)
        return True, None

    def remove_direct_edge(self, i: int, j: int) -> bool:
        """Közvetlen él (i->j) törlése a mátrixból; vissza: volt-e nemnulla él."""
        with self._lock:
            if self.knowledge_matrix[i, j] <= 0:
                return False
            self.knowledge_matrix[i, j] = 0.0
        return True

    def add_edge_if_proven(self, i: int, j: int) -> bool:
        ok, _ = self._try_add_edge_with_reason(i, j)
        return ok

    def _discovery_log_edge(self, i: int, j: int) -> None:
        """discovery policy: keresztdomain él + Q küszöb → discovery_log.txt."""
        if self._policy is None or not self._policy.discovery_enabled:
            return
        di = self.axiom_labels.get(i)
        dj = self.axiom_labels.get(j)
        if self._policy.discovery_log_cross_domain_only and di is not None and dj is not None:
            if di == dj:
                return
        q = self.calculate_q()
        disc = self._policy.discovery_policy()
        trust_path = self._resolve_policy_relative_path(disc.trust_store_path)
        tr = edge_trust.get_edge_trust(edge_trust.load_trust_store(trust_path), i, j)
        if tr <= disc.discovery_skip_log_trust_below:
            return
        q_eff = q * (1.0 + disc.discovery_trust_weight * tr)
        if q_eff < self._policy.discovery_log_q_threshold:
            return
        log_path = Path(self._policy.discovery_log_path)
        if not log_path.is_absolute():
            log_path = Path(__file__).resolve().parent / log_path
        line = (
            f"{time.time():.3f} pid={os.getpid()} Q={q:.6f} edge {i}->{j} "
            f"domain {di!s}->{dj!s}\n"
        )
        try:
            with log_path.open("a", encoding="utf-8") as lf:
                lf.write(line)
        except OSError:
            pass

    def _derivation_path_for_display(
        self, start: int, goal: int
    ) -> Optional[List[int]]:
        """Legrövidebb út; termo-láncnál Boltzmann -> II. főtétel -> időnyíl, ha így is összeáll a lánc."""
        if self._registry is None:
            return self.shortest_path(start, goal)
        e2 = self._registry.resolve_id("entropy_2nd")
        b = self._registry.resolve_id("boltzmann_entropy")
        t = self._registry.resolve_id("time_arrow")
        if (
            e2 is not None
            and b is not None
            and t is not None
            and goal == t
            and start == b
        ):
            p0 = self.shortest_path(b, e2)
            p1 = self.shortest_path(e2, t)
            if p0 and p1:
                return p0[:-1] + p1
        qds = self._registry.resolve_id("quantum_data_stream")
        sem = self._registry.resolve_id("shannon_entropy_max_q")
        brp = self._registry.resolve_id("born_rule_probability")
        qma = self._registry.resolve_id("quantum_mechanics_axiom")
        sch = self._registry.resolve_id("schrodinger")
        if (
            qds is not None
            and sem is not None
            and brp is not None
            and qma is not None
            and sch is not None
            and start == qds
            and goal == sch
        ):
            chain = [qds, sem, brp, qma, sch]
            acc: List[int] = []
            for i in range(len(chain) - 1):
                sp = self.shortest_path(chain[i], chain[i + 1])
                if sp is None:
                    return self.shortest_path(start, goal)
                if i == 0:
                    acc.extend(sp)
                else:
                    acc.extend(sp[1:])
            return acc
        return self.shortest_path(start, goal)

    def _pick_derivation_goal(
        self, start: int, goal_hint: Optional[int]
    ) -> Optional[int]:
        """Cél: explicit jelölés; egyébként első elérhető 'mély' süllyedés (időnyíl > II. tétel > Boltzmann)."""
        if goal_hint is not None:
            return goal_hint
        if self._registry is None:
            return (start + 1) % self.n_nodes
        qds = self._registry.resolve_id("quantum_data_stream")
        sch = self._registry.resolve_id("schrodinger")
        if qds is not None and sch is not None and start == qds:
            if self.shortest_path(start, sch) is not None:
                return sch
        sink_ids = ["time_arrow", "entropy_2nd", "boltzmann_entropy"]
        for sid in sink_ids:
            gid = self._registry.resolve_id(sid)
            if gid is None:
                continue
            if self.shortest_path(start, gid) is not None:
                return gid
        return None

    def think_step(self) -> Tuple[bool, float]:
        """
        Belső lépés: heurisztika (magas fokszám -> alacsony fokszám) vagy véletlen pár.
        discovery.enabled: ha verify_logic nem igazol, de tiltás/negáció nem lép — hipotézis él (add_edge_if_proven).
        """
        if self._opt is not None:
            self._opt.record_think_step()
        if self.use_heuristic_thinking:
            return self._think_step_heuristic()
        with self._lock:
            nonzero_rows = np.where(self.knowledge_matrix.sum(axis=1) > 0)[0]
        if nonzero_rows.size < 2:
            self._think_pending = _ThinkPending(
                mode="idle_sparse",
                i=None,
                j=None,
                verified=None,
                edge_added=False,
                abductive=False,
                edge_reject=None,
            )
            q = self.calculate_q()
            self._finalize_think_step(q)
            return False, q
        pair = self._weighted_pair_choice(nonzero_rows)
        if pair is None:
            q = self.calculate_q()
            self._finalize_think_step(q)
            return False, q
        i, j = int(pair[0]), int(pair[1])
        ok = self.verify_logic(i, j)
        added = False
        abductive = False
        reject: Optional[str] = None
        if ok:
            added, rj = self._try_add_edge_with_reason(i, j)
            reject = None if added else rj
        elif self._policy is not None and self._policy.discovery_enabled:
            added, rj = self._try_add_edge_with_reason(i, j)
            abductive = bool(added)
            reject = None if added else rj
        else:
            reject = "no_hypothesis"
        self._think_pending = _ThinkPending(
            mode="random_pair",
            i=i,
            j=j,
            verified=ok,
            edge_added=added,
            abductive=abductive,
            edge_reject=reject,
        )
        q = self.calculate_q()
        self._finalize_think_step(q)
        return True, q

    def _think_step_heuristic(self) -> Tuple[bool, float]:
        """Magas Q-szerű fokszámú csúcsok és „zajos” alacsony fokszámú csúcsok összekapcsolása; discovery mellett abduktív hipotézis."""
        self._think_pending = _ThinkPending(
            mode="heuristic",
            i=None,
            j=None,
            verified=None,
            edge_added=False,
            abductive=False,
            edge_reject=None,
        )
        with self._lock:
            n = self.n_nodes
            deg = np.zeros(n, dtype=np.int32)
            for u in range(n):
                deg[u] = int((self.knowledge_matrix[u, :] > 0).sum()) + int(
                    (self.knowledge_matrix[:, u] > 0).sum()
                )
        high = np.argsort(deg)[::-1]
        low = np.argsort(deg)
        k = max(1, n // 4)
        # Súlyozott pickelés a top-k high és top-k low csúcsból.
        high_pool = high[: min(k, n)]
        low_pool = low[: min(k, n)]
        for _ in range(min(12, n * 2)):
            i = self._weighted_index_pick(high_pool)
            j = self._weighted_index_pick(low_pool)
            if i < 0 or j < 0:
                continue
            if i == j:
                continue
            ok = self.verify_logic(i, j)
            if ok:
                added, rj = self._try_add_edge_with_reason(i, j)
                self._think_pending = _ThinkPending(
                    mode="heuristic",
                    i=i,
                    j=j,
                    verified=True,
                    edge_added=added,
                    abductive=False,
                    edge_reject=None if added else rj,
                )
                break
            if self._policy is not None and self._policy.discovery_enabled:
                added, rj = self._try_add_edge_with_reason(i, j)
                self._think_pending = _ThinkPending(
                    mode="heuristic",
                    i=i,
                    j=j,
                    verified=False,
                    edge_added=added,
                    abductive=bool(added),
                    edge_reject=None if added else rj,
                )
                if added:
                    break
            else:
                self._think_pending = _ThinkPending(
                    mode="heuristic",
                    i=i,
                    j=j,
                    verified=False,
                    edge_added=False,
                    abductive=False,
                    edge_reject="no_hypothesis",
                )
        q = self.calculate_q()
        self._finalize_think_step(q)
        return True, q

    def think_loop(self) -> None:
        t0 = time.monotonic()
        while self._is_thinking:
            if self._policy is not None:
                if self._policy.check_and_reload():
                    self._apply_policy_from_manager()
                max_s = self._policy.daemon_max_runtime_seconds
                if max_s > 0 and (time.monotonic() - t0) >= max_s:
                    self._is_thinking = False
                    break
            _, q = self.think_step()
            if q >= self.q_threshold:
                if self._on_awakening:
                    self._on_awakening(q)
                daemon = (
                    self._policy is not None and self._policy.discovery_daemon_mode
                )
                if not daemon:
                    self._is_thinking = False
                    break
            sleep_d = self.sleep_s
            if self._policy is not None:
                sleep_d = self._policy.effective_sleep_s(self.sleep_s)
            time.sleep(sleep_d)

    def start_autonomous_thinking(
        self, on_awakening: Optional[Callable[[float], None]] = None
    ) -> None:
        if self._think_thread and self._think_thread.is_alive():
            return
        self._on_awakening = on_awakening
        self._is_thinking = True

        def run() -> None:
            self.think_loop()

        self._think_thread = threading.Thread(target=run, daemon=True)
        self._think_thread.start()

    def stop_thinking(self) -> None:
        self._is_thinking = False
        if self._think_thread:
            self._think_thread.join(timeout=2.0)

    def join_thinking(self, timeout: Optional[float] = None) -> None:
        """Várakozás a háttér think_loop szálra (pl. max_runtime_seconds után kilép)."""
        if self._think_thread and self._think_thread.is_alive():
            self._think_thread.join(timeout=timeout)

    def run_think_steps_sync(self, max_steps: int) -> Tuple[float, bool]:
        """Szinkron demó: max_steps belső lépés, visszaadja (utolsó Q, elérte-e a küszöböt)."""
        last_q = self.calculate_q()
        for _ in range(max_steps):
            _, last_q = self.think_step()
            if last_q >= self.q_threshold:
                return last_q, True
        return last_q, False

    def derive_statement(
        self,
        user_text: str,
        target_j: Optional[int] = None,
        source_id: str = "default",
    ) -> InferenceResult | str:
        """
        Igazolt kimenet: legrövidebb lánc az axiómákhoz, formulák, N*/Q; küszöb alatt strukturális hiány.
        """
        h0, i = self.filter_input(user_text)
        if i is None:
            return STRUCTURAL_GAP_MSG

        q = self.calculate_q()
        if q < self.q_threshold:
            return STRUCTURAL_GAP_MSG

        goal = self._pick_derivation_goal(i, target_j)
        if goal is None:
            goal = (i + 1) % self.n_nodes

        path_idx = self._derivation_path_for_display(i, goal)
        if path_idx is None:
            path_idx = [i]

        chain: List[Tuple[int, int]] = []
        for a, b in zip(path_idx[:-1], path_idx[1:]):
            chain.append((a, b))

        path_axiom_ids = ["input_data"] + [
            (self._registry.get_axiom_by_index(j).id if self._registry else str(j))
            for j in path_idx
        ]
        path_formulas: List[str] = []
        if self._registry:
            for j in path_idx:
                sp = self._registry.get_axiom_by_index(j)
                path_formulas.append(sp.formula if sp else "")
        else:
            path_formulas = ["" for _ in path_idx]

        primary = path_formulas[-1] if path_formulas else ""
        rel = self.get_source_reliability(source_id)
        ns = self.n_star(h0, q)
        verdict = (
            "Igazolt (Struktura stabil)"
            if q >= self.q_threshold
            else "Nem igazolt"
        )
        stmt = (
            f"[AIE] Lokalis Q={q:.4f} >= {self.q_threshold}; "
            f"N*={ns:.4f}; path_len={len(path_idx)}."
        )
        return InferenceResult(
            statement=stmt,
            q_density=q,
            n_star=ns,
            causal_chain=chain,
            h0=h0,
            b_eff=self.backend_efficiency_b,
            c_coherence=self.coherence_c,
            input_text=user_text,
            verdict=verdict,
            path_indices=list(path_idx),
            path_axiom_ids=path_axiom_ids,
            path_formulas=path_formulas,
            primary_formula=primary,
            q_at_inference=q,
            n_star_at_inference=ns,
            source_reliability=rel,
        )


def default_awakening(q: float) -> None:
    print(f"KRITIKUS KÜSZÖB ÁTLÉPVE! Q = {q:.4f}")
    print("Az idő-struktúra megjelent. A rendszer stabilizált összefüggést jelez.")


if __name__ == "__main__":
    demo = AxiomaticInferenceEngine(
        n_nodes=21,
        q_threshold=0.77,
        sleep_s=0.001,
        enable_self_optimization=True,
        policy_enabled=True,
    )
    print("Regiszter:", demo._registry is not None, "| csúcsok:", demo.n_nodes)
    if demo._registry:
        s = "Minden hatásnak van ellenhatása."
        idx = demo.map_input_to_axiom(s)
        spec = demo._registry.get_spec(idx) if idx is not None else None
        print("Kulcsszó teszt:", repr(s), "->", idx, spec.id if spec else None)
    print("Q indul:", f"{demo.calculate_q():.4f}")
    demo.deductive_saturate()
    print("Q tranzitív lezárás után:", f"{demo.calculate_q():.4f}")
    q_end, hit = demo.run_think_steps_sync(max_steps=50_000)
    print("Q vége (heurisztikus lépések után):", f"{q_end:.4f}", "| küszöb:", hit)
    if hit:
        default_awakening(q_end)
    therm = "A homerseklet kiegyenlodik a szobaban."
    out2 = demo.derive_statement(therm, source_id="user")
    if isinstance(out2, InferenceResult):
        print(out2.format_report_ascii())
    out = demo.derive_statement("teszt bemenet 42")
    print("Hash-mapped:", out)
    if demo._registry:
        p_i = demo._registry.resolve_id("literal_P")
        np_i = demo._registry.resolve_id("literal_not_P")
        if p_i is not None and np_i is not None:
            with demo._lock:
                demo.knowledge_matrix[p_i, np_i] = 0.0
            r = demo.propose_edge_with_source("demo_src", p_i, np_i)
            print(
                "Ellentmondas teszt P->notP (él törölve):",
                r,
                "| trust:",
                f"{demo.get_source_reliability('demo_src'):.4f}",
            )
    if demo._opt:
        for _ in range(25):
            demo.think_step()
        sugs = demo.evaluate_self_optimization()
        print(demo._opt.format_report_ascii(sugs))
        if sugs:
            nb = demo.apply_backend_efficiency_suggestions(sugs)
            print("backend_efficiency_b after apply:", f"{nb:.4f}")
