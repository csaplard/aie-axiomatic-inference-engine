"""
Hipnagóg üzemmód állapotgép (pure state machine).

A modul csak állapotot követ és lazítási paraméter-szótárat számol; az engine
heurisztikus viselkedését NEM módosítja közvetlenül. Az integráció (think_step
oldali fogyasztás) később, külön komponensben történik.

Fázisok:
    AWAKE     — nem aktív, alap (strict) paraméterek érvényesek
    ENTRY     — belépés DEEP-be: lineáris interpoláció strict → deep
                ``entry_steps`` lépés alatt
    DEEP      — teljes lazítás, a policyban definiált deep paraméter-értékek
    EXIT      — kilépés DEEP-ből: lineáris interpoláció deep → strict
                ``exit_steps`` lépés alatt
    COOLDOWN  — kvázi-AWAKE (strict paraméterek), de új ENTRY-t blokkol amíg
                ``cooldown_steps`` el nem telik

A `tick(fisher_trigger=True)` DEEP fázisban azonnali EXIT-et vált ki
("kavics-csobbanás" detekció); más fázisokban a flag figyelmen kívül marad.
Az állapotgép determinisztikus: ugyanaz a policy + tick szekvencia ugyanazt
az állapotsorozatot eredményezi.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Union

from policy_manager import HypnagogicPolicy


class HypnagogicPhase(str, Enum):
    AWAKE = "awake"        # not in hypnagogic mode at all
    ENTRY = "entry"        # ramping into deep
    DEEP = "deep"          # full relaxation
    EXIT = "exit"          # ramping back to awake
    COOLDOWN = "cooldown"  # AWAKE-equivalent, blocks re-entry until expired


# Strict (waking) reference values — in AWAKE/COOLDOWN these are returned.
_STRICT_FORBIDDEN_WEIGHT: float = 1.0
_STRICT_NEGATION_THRESHOLD: float = 1.0
_STRICT_FAR_DOMAIN_PREF: float = 0.0
_STRICT_VERIFY_CHAIN_DEPTH: int = 1


def _lerp(a: float, b: float, t: float) -> float:
    """Lineáris interpoláció a-tól b-ig, t in [0,1] (clamp-elve)."""
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return a + (b - a) * t


class HypnagogicStateMachine:
    """Tiszta állapotgép a hipnagóg üzemmódhoz.

    Csak a fázist + belső számlálót tartja nyilván, és a `current_relaxation`
    metódussal előállítja a fázis-érzékeny lazítási paraméter-szótárat.
    """

    def __init__(self, policy: HypnagogicPolicy) -> None:
        self._policy: HypnagogicPolicy = policy
        self._phase: HypnagogicPhase = HypnagogicPhase.AWAKE
        self._counter: int = 0

    # ---- Public state inspection --------------------------------------

    def current_phase(self) -> HypnagogicPhase:
        return self._phase

    # ---- Transitions --------------------------------------------------

    def start_entry(self) -> bool:
        """Belépés-kísérlet ENTRY fázisba.

        Csak AWAKE fázisból engedélyezett (COOLDOWN blokkol). Visszatérés:
        True ha a váltás megtörtént, False egyébként.
        """
        if self._phase is not HypnagogicPhase.AWAKE:
            return False
        self._phase = HypnagogicPhase.ENTRY
        self._counter = 0
        return True

    def tick(self, fisher_trigger: bool = False) -> HypnagogicPhase:
        """Egy think_step-nyi időléptetés. Visszaadja az új (vagy változatlan)
        fázist.

        Logika:
          - AWAKE     : no-op
          - ENTRY     : counter++; ha counter >= entry_steps → DEEP
          - DEEP      : ha fisher_trigger → EXIT (azonnal); egyébként counter++;
                        ha counter >= deep_steps → EXIT
          - EXIT      : counter++; ha counter >= exit_steps → COOLDOWN
          - COOLDOWN  : counter++; ha counter >= cooldown_steps → AWAKE
        """
        phase = self._phase
        if phase is HypnagogicPhase.AWAKE:
            return phase

        if phase is HypnagogicPhase.ENTRY:
            self._counter += 1
            if self._counter >= self._policy.entry_steps:
                self._phase = HypnagogicPhase.DEEP
                self._counter = 0
            return self._phase

        if phase is HypnagogicPhase.DEEP:
            if fisher_trigger:
                self._phase = HypnagogicPhase.EXIT
                self._counter = 0
                return self._phase
            self._counter += 1
            if self._counter >= self._policy.deep_steps:
                self._phase = HypnagogicPhase.EXIT
                self._counter = 0
            return self._phase

        if phase is HypnagogicPhase.EXIT:
            self._counter += 1
            if self._counter >= self._policy.exit_steps:
                self._phase = HypnagogicPhase.COOLDOWN
                self._counter = 0
            return self._phase

        if phase is HypnagogicPhase.COOLDOWN:
            self._counter += 1
            if self._counter >= self._policy.cooldown_steps:
                self._phase = HypnagogicPhase.AWAKE
                self._counter = 0
            return self._phase

        return self._phase  # pragma: no cover

    def reset(self) -> None:
        """Visszaállítás AWAKE állapotba, számlálók törlése."""
        self._phase = HypnagogicPhase.AWAKE
        self._counter = 0

    # ---- Relaxation parameters ---------------------------------------

    def current_relaxation(self) -> Dict[str, Union[float, int]]:
        """Aktuális lazítási paraméterek a fázis és belső számláló alapján.

        Kulcsok:
          - forbidden_weight    (float in [0,1])
          - negation_threshold  (float in [0,1])
          - far_domain_pref     (float in [0,1])
          - verify_chain_depth  (int)
        """
        phase = self._phase
        p = self._policy

        if phase is HypnagogicPhase.AWAKE or phase is HypnagogicPhase.COOLDOWN:
            return {
                "forbidden_weight": _STRICT_FORBIDDEN_WEIGHT,
                "negation_threshold": _STRICT_NEGATION_THRESHOLD,
                "far_domain_pref": _STRICT_FAR_DOMAIN_PREF,
                "verify_chain_depth": _STRICT_VERIFY_CHAIN_DEPTH,
            }

        if phase is HypnagogicPhase.DEEP:
            return {
                "forbidden_weight": float(p.forbidden_weight_deep),
                "negation_threshold": float(p.negation_threshold_deep),
                "far_domain_pref": float(p.far_domain_pref_deep),
                "verify_chain_depth": int(p.verify_chain_depth_deep),
            }

        if phase is HypnagogicPhase.ENTRY:
            # t in (0, 1]: 0 a fázis kezdetén, 1 a DEEP elérésekor
            denom = max(1, p.entry_steps)
            t = self._counter / denom
            return {
                "forbidden_weight": _lerp(
                    p.forbidden_weight_entry_start,
                    p.forbidden_weight_deep,
                    t,
                ),
                "negation_threshold": _lerp(
                    _STRICT_NEGATION_THRESHOLD, p.negation_threshold_deep, t
                ),
                "far_domain_pref": _lerp(
                    _STRICT_FAR_DOMAIN_PREF, p.far_domain_pref_deep, t
                ),
                "verify_chain_depth": int(round(_lerp(
                    float(_STRICT_VERIFY_CHAIN_DEPTH),
                    float(p.verify_chain_depth_deep),
                    t,
                ))),
            }

        # EXIT
        denom = max(1, p.exit_steps)
        t = self._counter / denom
        return {
            "forbidden_weight": _lerp(
                p.forbidden_weight_deep,
                _STRICT_FORBIDDEN_WEIGHT,
                t,
            ),
            "negation_threshold": _lerp(
                p.negation_threshold_deep, _STRICT_NEGATION_THRESHOLD, t
            ),
            "far_domain_pref": _lerp(
                p.far_domain_pref_deep, _STRICT_FAR_DOMAIN_PREF, t
            ),
            "verify_chain_depth": int(round(_lerp(
                float(p.verify_chain_depth_deep),
                float(_STRICT_VERIFY_CHAIN_DEPTH),
                t,
            ))),
        }
