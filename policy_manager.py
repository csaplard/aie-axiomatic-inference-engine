"""
YAML-alapú policy betöltése és hot-reload (mtime), opcionális CPU-cél alapú sleep.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

try:
    import psutil  # type: ignore

    _HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore
    _HAS_PSUTIL = False


@dataclass
class QStabilityPolicy:
    window_size: int = 20
    q_threshold_base: float = 0.77


@dataclass
class SparsityPolicy:
    nnz_ratio_threshold: float = 0.12
    suggest_sparse_backend: bool = True


@dataclass
class BackendEfficiencyPolicy:
    b_boost_on_stable_q: float = 0.02
    b_max_limit: float = 1.0


@dataclass
class SchedulingPolicy:
    sleep_s_base: float = 0.01
    adaptive_sleep_enabled: bool = True
    cpu_target_percent: float = 15.0


@dataclass
class OptimizationPolicy:
    q_stability: QStabilityPolicy
    sparsity: SparsityPolicy
    backend_efficiency: BackendEfficiencyPolicy
    scheduling: SchedulingPolicy


@dataclass
class DiscoveryPolicy:
    """Felfedező / daemon: tiltások lazítása, napló, végtelen think_loop opció."""

    enabled: bool = False
    daemon_mode: bool = False
    ignore_forbidden_edges: bool = False
    # Ha True: logical_negation_pairs nem blokkol él felvételt (kísérleti, lazított immun)
    ignore_negation_contradictions: bool = False
    log_path: str = "discovery_log.txt"
    log_q_threshold: float = 0.77
    log_cross_domain_only: bool = True
    seed_hamilton_ring: bool = True
    telemetry_enabled: bool = False
    telemetry_every_n_steps: int = 100
    telemetry_log_path: str = "telemetry.log"
    # 0 = korlátlan; pl. 86400 = 24 óra, után a think_loop leáll
    max_runtime_seconds: float = 0.0
    # Fázis 5: per-él trust fájl (policy könyvtárához relatív, ha nem abszolút)
    trust_store_path: str = "hypotheses/edge_trust.json"
    # q_eff = q * (1 + weight * trust); trust in [-1,1], weight ~0.1–0.2
    discovery_trust_weight: float = 0.15
    # Ha trust <= ez, discovery sor nem kerül naplózásra
    discovery_skip_log_trust_below: float = -0.6
    # Reprodukálhatóság: ha nem None, az engine numpy/random RNG-t ezzel seedeli.
    random_seed: Optional[int] = None


def _default_optimization_policy() -> OptimizationPolicy:
    return OptimizationPolicy(
        q_stability=QStabilityPolicy(),
        sparsity=SparsityPolicy(),
        backend_efficiency=BackendEfficiencyPolicy(),
        scheduling=SchedulingPolicy(),
    )


def _default_discovery_policy() -> DiscoveryPolicy:
    return DiscoveryPolicy()


def _parse_discovery_policy(raw: Dict[str, Any]) -> DiscoveryPolicy:
    if not raw:
        return _default_discovery_policy()
    daemon_mode = bool(raw.get("daemon_mode", False))
    if "seed_hamilton_ring" in raw:
        seed_hamilton = bool(raw.get("seed_hamilton_ring"))
    else:
        seed_hamilton = not daemon_mode
    return DiscoveryPolicy(
        enabled=bool(raw.get("enabled", False)),
        daemon_mode=daemon_mode,
        ignore_forbidden_edges=bool(raw.get("ignore_forbidden_edges", False)),
        ignore_negation_contradictions=bool(
            raw.get("ignore_negation_contradictions", False)
        ),
        log_path=str(raw.get("log_path", "discovery_log.txt")),
        log_q_threshold=float(raw.get("log_q_threshold", 0.77)),
        log_cross_domain_only=bool(raw.get("log_cross_domain_only", True)),
        seed_hamilton_ring=seed_hamilton,
        telemetry_enabled=bool(raw.get("telemetry_enabled", False)),
        telemetry_every_n_steps=int(raw.get("telemetry_every_n_steps", 100)),
        telemetry_log_path=str(raw.get("telemetry_log_path", "telemetry.log")),
        max_runtime_seconds=float(raw.get("max_runtime_seconds", 0)),
        trust_store_path=str(
            raw.get("trust_store_path", "hypotheses/edge_trust.json")
        ),
        discovery_trust_weight=float(raw.get("discovery_trust_weight", 0.15)),
        discovery_skip_log_trust_below=float(
            raw.get("discovery_skip_log_trust_below", -0.6)
        ),
        random_seed=(
            int(raw["random_seed"])
            if raw.get("random_seed") is not None
            else None
        ),
    )


def _parse_optimization_policy(raw: Dict[str, Any]) -> OptimizationPolicy:
    qs = raw.get("q_stability") or {}
    sp = raw.get("sparsity") or {}
    be = raw.get("backend_efficiency") or {}
    sc = raw.get("scheduling") or {}
    return OptimizationPolicy(
        q_stability=QStabilityPolicy(
            window_size=int(qs.get("window_size", 20)),
            q_threshold_base=float(qs.get("q_threshold_base", 0.77)),
        ),
        sparsity=SparsityPolicy(
            nnz_ratio_threshold=float(sp.get("nnz_ratio_threshold", 0.12)),
            suggest_sparse_backend=bool(sp.get("suggest_sparse_backend", True)),
        ),
        backend_efficiency=BackendEfficiencyPolicy(
            b_boost_on_stable_q=float(be.get("b_boost_on_stable_q", 0.02)),
            b_max_limit=float(be.get("b_max_limit", 1.0)),
        ),
        scheduling=SchedulingPolicy(
            sleep_s_base=float(sc.get("sleep_s_base", 0.01)),
            adaptive_sleep_enabled=bool(sc.get("adaptive_sleep_enabled", True)),
            cpu_target_percent=float(sc.get("cpu_target_percent", 15.0)),
        ),
    )


class PolicyManager:
    """
    YAML betöltése, mtime-alapú újratöltés, CPU minta (psutil, ha elérhető).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._mtime: float = 0.0
        self._optimization: OptimizationPolicy = _default_optimization_policy()
        self._discovery: DiscoveryPolicy = _default_discovery_policy()
        self._cpu_smoothed: Optional[float] = None

    @property
    def optimization_policy(self) -> OptimizationPolicy:
        with self._lock:
            return self._optimization

    def _op(self) -> OptimizationPolicy:
        with self._lock:
            return self._optimization

    def load(self) -> None:
        """Kényszerített betöltés fájlból (ha nem létezik, alapértelmezés)."""
        with self._lock:
            if not self.path.is_file():
                self._optimization = _default_optimization_policy()
                self._discovery = _default_discovery_policy()
                self._mtime = 0.0
                return
            with self.path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            op = data.get("optimization_policy") or {}
            self._optimization = _parse_optimization_policy(op)
            disc = data.get("discovery") or {}
            self._discovery = _parse_discovery_policy(disc)
            self._mtime = self.path.stat().st_mtime

    def check_and_reload(self) -> bool:
        """Ha a fájl módosult, újratöltés. Vissza: történt-e reload."""
        with self._lock:
            if not self.path.is_file():
                return False
            try:
                mtime = self.path.stat().st_mtime
            except OSError:
                return False
            if mtime == self._mtime:
                return False
        self.load()
        return True

    # --- Gyors elérési utak az engine / advisor számára ---

    @property
    def q_threshold_base(self) -> float:
        return self._op().q_stability.q_threshold_base

    @property
    def window_size(self) -> int:
        return self._op().q_stability.window_size

    @property
    def nnz_ratio_threshold(self) -> float:
        return self._op().sparsity.nnz_ratio_threshold

    @property
    def suggest_sparse_backend(self) -> bool:
        return self._op().sparsity.suggest_sparse_backend

    @property
    def b_boost_on_stable_q(self) -> float:
        return self._op().backend_efficiency.b_boost_on_stable_q

    @property
    def b_max_limit(self) -> float:
        return self._op().backend_efficiency.b_max_limit

    @property
    def sleep_s_base(self) -> float:
        return self._op().scheduling.sleep_s_base

    @property
    def adaptive_sleep_enabled(self) -> bool:
        return self._op().scheduling.adaptive_sleep_enabled

    @property
    def cpu_target_percent(self) -> float:
        return self._op().scheduling.cpu_target_percent

    def discovery_policy(self) -> DiscoveryPolicy:
        with self._lock:
            return self._discovery

    @property
    def discovery_enabled(self) -> bool:
        return self.discovery_policy().enabled

    @property
    def discovery_daemon_mode(self) -> bool:
        return self.discovery_policy().daemon_mode

    @property
    def ignore_forbidden_edges(self) -> bool:
        return self.discovery_policy().ignore_forbidden_edges

    @property
    def ignore_negation_contradictions(self) -> bool:
        return self.discovery_policy().ignore_negation_contradictions

    @property
    def discovery_log_path(self) -> str:
        return self.discovery_policy().log_path

    @property
    def discovery_log_q_threshold(self) -> float:
        return self.discovery_policy().log_q_threshold

    @property
    def discovery_log_cross_domain_only(self) -> bool:
        return self.discovery_policy().log_cross_domain_only

    @property
    def seed_hamilton_ring(self) -> bool:
        return self.discovery_policy().seed_hamilton_ring

    @property
    def telemetry_enabled(self) -> bool:
        return self.discovery_policy().telemetry_enabled

    @property
    def telemetry_every_n_steps(self) -> int:
        return self.discovery_policy().telemetry_every_n_steps

    @property
    def telemetry_log_path(self) -> str:
        return self.discovery_policy().telemetry_log_path

    @property
    def daemon_max_runtime_seconds(self) -> float:
        return float(self.discovery_policy().max_runtime_seconds)

    @property
    def random_seed(self) -> Optional[int]:
        return self.discovery_policy().random_seed

    def sample_cpu_percent(self) -> Optional[float]:
        """Folyamat CPU% (nem blokkoló, ha psutil elérhető)."""
        if not _HAS_PSUTIL:
            return None
        try:
            p = psutil.Process()
            cpu = p.cpu_percent(interval=None)
            if self._cpu_smoothed is None:
                self._cpu_smoothed = cpu
            else:
                self._cpu_smoothed = 0.3 * cpu + 0.7 * self._cpu_smoothed
            return float(self._cpu_smoothed)
        except Exception:
            return None

    def effective_sleep_s(self, sleep_s_current: float) -> float:
        """
        Adaptív alvás: alacsony cpu_target (~15%) → kímélés; magas cél (pl. 80%) →
        CPU felhúzása (sleep csökkentése), túlmelegedésnél némileg növelés.
        """
        base = sleep_s_current
        if not self.adaptive_sleep_enabled:
            return base
        cpu = self.sample_cpu_percent()
        if cpu is None:
            return base
        target = self.cpu_target_percent
        # Magas kihasználtsági cél: felfedező / daemon mód
        if target >= 35.0:
            if cpu < target * 0.88:
                return max(base * 0.65, 0.000005)
            if cpu > min(target * 1.12, 98.0):
                return min(base * 1.25, 0.05)
            return base
        if cpu > target * 1.4:
            return min(base * 1.35, 0.25)
        if cpu > target * 1.1:
            return min(base * 1.15, 0.15)
        if cpu < target * 0.5 and base > 0.0002:
            return max(base * 0.85, 0.0001)
        return base
