"""
Modul B (narrow scope) — epizodikus memória: engine-állapot persistence + reload.

Az engine képes elmenteni a teljes belső állapotát (knowledge_matrix, source_trust,
RRR-számlálók, opcionálisan az RNG-állapotot, és a hipnagóg state machine
fázisát) egy mappa alá, és ugyanonnan visszatölteni azt egy másik (vagy ugyanaz
a) engine-instance-ba. Ez a Modul C/D infrastruktúrája.

Tárolási formátum egy memória-mappa alatt:
  - state.json: non-array mezők (trust, counters, hypnagogic phase, RNG-state opt.)
  - knowledge_matrix.npy: a fő gráf-állapot
  - schema_version: explicit, későbbi migrációkhoz

API:
  EpisodicMemory(root: Path)
  .save_engine_state(engine, label: str, save_rng: bool = True) -> Path
  .load_engine_state(engine, label: str) -> bool
  .has_state(label: str) -> bool
  .list_labels() -> List[str]

A modul **nem érti** az engine belső reprezentációját, csak duck-typing alapon
fér hozzá az attribútumokhoz. Ez tesztelhetőséget és Modul C-D-be szétbontást
támogat.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

SCHEMA_VERSION = 1


class EpisodicMemory:
    """Engine-állapot persistence + reload, label-alapú namespace."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------- private

    def _label_dir(self, label: str) -> Path:
        # Egyszerű szanitárás: csak alfanumerikus + '_' + '-'
        safe = "".join(c if (c.isalnum() or c in "_-.") else "_" for c in label)
        if not safe:
            safe = "default"
        return self.root / f"memory_{safe}"

    @staticmethod
    def _serialize_rng_state(state: tuple) -> Dict[str, Any]:
        """np.random.get_state() tuple → JSON-serializable dict."""
        # Tuple shape: (str, ndarray, int, int, float)
        kind, keys, pos, has_gauss, cached_gauss = state
        return {
            "kind": str(kind),
            "keys": keys.tolist(),
            "pos": int(pos),
            "has_gauss": int(has_gauss),
            "cached_gauss": float(cached_gauss),
        }

    @staticmethod
    def _deserialize_rng_state(d: Dict[str, Any]) -> tuple:
        return (
            str(d["kind"]),
            np.array(d["keys"], dtype=np.uint32),
            int(d["pos"]),
            int(d["has_gauss"]),
            float(d["cached_gauss"]),
        )

    # -------------------------------------------------------------- public

    def has_state(self, label: str) -> bool:
        d = self._label_dir(label)
        return (d / "state.json").is_file() and (d / "knowledge_matrix.npy").is_file()

    def list_labels(self) -> List[str]:
        out = []
        if not self.root.is_dir():
            return out
        for sub in self.root.iterdir():
            if not sub.is_dir():
                continue
            name = sub.name
            if name.startswith("memory_"):
                out.append(name[len("memory_"):])
        return sorted(out)

    def save_engine_state(
        self, engine: Any, label: str, save_rng: bool = True
    ) -> Path:
        """Az engine teljes belső állapotát menti.

        engine: AxiomaticInferenceEngine (duck-typed; az alábbi attribútumok
                hozzáférhetők kellenek lennie).
        label: a mentés címkéje (a mappa neve memory_<label>).
        save_rng: ha True, a numpy RNG-állapotot is menti (perfekt determinism
                  load után). Ha False, csak a strukturális állapotot.

        Visszaadja: a memória-mappa Path-ja.
        """
        d = self._label_dir(label)
        d.mkdir(parents=True, exist_ok=True)

        # Knowledge matrix
        np.save(d / "knowledge_matrix.npy", engine.knowledge_matrix)

        # Strukturális állapot
        state: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "label": label,
            "n_nodes": int(engine.n_nodes),
            "think_step_counter": int(getattr(engine, "_think_step_counter", 0)),
            "reverse_attempt_count": int(getattr(engine, "_reverse_attempt_count", 0)),
            "reverse_reject_contradiction_count": int(
                getattr(engine, "_reverse_reject_contradiction_count", 0)
            ),
            "source_trust": dict(getattr(engine, "_source_trust", {}) or {}),
            "save_rng": bool(save_rng),
        }

        # RNG state (opcionális)
        if save_rng:
            try:
                rng_state = np.random.get_state()
                state["rng_state"] = self._serialize_rng_state(rng_state)
            except Exception:
                state["rng_state"] = None

        # Hipnagóg állapot (opcionális, csak ha a state machine létezik)
        hyp_state = getattr(engine, "_hypnagogic_state", None)
        if hyp_state is not None:
            try:
                state["hypnagogic"] = {
                    "phase": hyp_state.current_phase().value,
                    "counter": int(getattr(hyp_state, "_counter", 0)),
                }
            except Exception:
                state["hypnagogic"] = None

        with (d / "state.json").open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return d

    def load_engine_state(self, engine: Any, label: str) -> bool:
        """Visszatölti az engine-be a label-hez tartozó mentett állapotot.

        engine: AxiomaticInferenceEngine (mutált).
        label: a mentés címkéje.

        Visszaadja: True ha sikerült, False ha nincs ilyen mentés.
        """
        d = self._label_dir(label)
        sj = d / "state.json"
        km = d / "knowledge_matrix.npy"
        if not sj.is_file() or not km.is_file():
            return False

        with sj.open(encoding="utf-8") as f:
            state = json.load(f)
        if int(state.get("schema_version", -1)) != SCHEMA_VERSION:
            return False

        # Knowledge matrix
        loaded_matrix = np.load(km)
        if loaded_matrix.shape != engine.knowledge_matrix.shape:
            return False
        engine.knowledge_matrix = loaded_matrix.copy()

        # Strukturális állapot
        engine._think_step_counter = int(state.get("think_step_counter", 0))
        engine._reverse_attempt_count = int(state.get("reverse_attempt_count", 0))
        engine._reverse_reject_contradiction_count = int(
            state.get("reverse_reject_contradiction_count", 0)
        )
        engine._source_trust = dict(state.get("source_trust", {}) or {})

        # RNG state (ha mentve volt és kérik)
        if state.get("save_rng") and state.get("rng_state"):
            try:
                np.random.set_state(self._deserialize_rng_state(state["rng_state"]))
            except Exception:
                # Ha nem sikerül, csendesen folytatjuk — a B-Continuity teszt
                # éppen az RNG nélküli load-ot teszteli.
                pass

        # Hipnagóg állapot
        hyp_data = state.get("hypnagogic")
        hyp_state = getattr(engine, "_hypnagogic_state", None)
        if hyp_data is not None and hyp_state is not None:
            try:
                from hypnagogic_state import HypnagogicPhase
                phase_val = hyp_data.get("phase", "awake")
                hyp_state._phase = HypnagogicPhase(phase_val)
                hyp_state._counter = int(hyp_data.get("counter", 0))
            except Exception:
                pass

        return True
