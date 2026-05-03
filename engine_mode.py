"""
Engine Mode (Idea 5 — Mode Labeling) — egységes módcímkézés az AIE-ben.

Cél: a paraméter-átállításokat (forbidden_weight, negation_threshold, stb.)
egyetlen, explicit, jól nevezett "mode" entitás mögé rendezni, hogy az F/G/H
modulok és az Idea 4 (oszcilláció) közös API-t kapjanak.

Ez **címkézés és csomagolás**, NEM új mechanika. A meglévő hipnagóg state
machine és discovery flagek változatlanok; az `EngineMode` egy default
relaxation-csomagot ad, amelyet a kernel akkor használ, ha a hipnagóg
state machine NINCS aktív (AWAKE / inicializálatlan).

Új viselkedés a CONSOLIDATING módnál: `accept_new_edges=False` — a kernel
elutasítja az új él hozzáadását, csak a meglévő él-erősségek (decay-mode-ban)
maradnak aktívak. Ez a "replay/pruning fázis" csíraszerű implementációja
a Modul H-hoz.

Falsifiable hipotézis NINCS — design-cleanup. Az F/G/H/Idea4 építkezés
felett ad közös API-t.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict


class EngineMode(Enum):
    """Az AIE négy diszkrét üzemmódja.

    A nevek **címkék**, nem új mechanizmus. A biológiai megfelelők
    (beta/alpha/theta/delta) csak metafora — a paraméter-csomagok mögött
    a meglévő szimbolikus engine-mechanika dolgozik.
    """

    FOCUSED = "focused"            # szigorú forbidden, alacsony surprise-érzékenység
    EXPLORATORY = "exploratory"    # lazább forbidden, közepes amplitúdó
    HYPNAGOGIC = "hypnagogic"      # erős lazítás, far-domain bias (Modul A)
    CONSOLIDATING = "consolidating"  # replay-mode, új él felvétel kikapcsolva (Modul H csíra)


@dataclass(frozen=True)
class ModeProfile:
    """Egy mód relaxation-csomagja.

    Mezők kompatibilisek a `get_current_relaxation()` dict-tel, plusz egy
    extra `accept_new_edges` flag a CONSOLIDATING számára.
    """

    forbidden_weight: float        # 1.0 = szigorú; <1.0 = valószínűségi
    negation_threshold: float      # 1.0 = szigorú
    far_domain_pref: float         # 0.0 = nincs preferencia; <=1.0 erős
    verify_chain_depth: int        # legalább 1
    accept_new_edges: bool = True  # CONSOLIDATING-ban False

    def to_relaxation_dict(self) -> Dict[str, float]:
        """A meglévő `current_relaxation` dict-formátumba konvertál
        (backward-kompatibilis a kernel-ben már használt kulcsokkal)."""
        return {
            "forbidden_weight": float(self.forbidden_weight),
            "negation_threshold": float(self.negation_threshold),
            "far_domain_pref": float(self.far_domain_pref),
            "verify_chain_depth": int(self.verify_chain_depth),
        }


# Alapértelmezett mód-profilok. Felülírhatók engine-példányban
# (engine._mode_profiles[mode] = ModeProfile(...)) az adatvezérelt
# kísérletezéshez (Idea 4 oszcillációs profilok ide csatlakoznak).
DEFAULT_PROFILES: Dict[EngineMode, ModeProfile] = {
    EngineMode.FOCUSED: ModeProfile(
        forbidden_weight=1.0,
        negation_threshold=1.0,
        far_domain_pref=0.0,
        verify_chain_depth=1,
        accept_new_edges=True,
    ),
    EngineMode.EXPLORATORY: ModeProfile(
        forbidden_weight=0.7,
        negation_threshold=0.8,
        far_domain_pref=0.3,
        verify_chain_depth=2,
        accept_new_edges=True,
    ),
    EngineMode.HYPNAGOGIC: ModeProfile(
        # Konzisztens a HypnagogicPolicy *_deep alapértékekkel,
        # de **csak akkor használt**, ha a state machine NEM aktív
        # (state machine prioritást élvez visszafelé kompatibilitásból).
        forbidden_weight=0.3,
        negation_threshold=0.5,
        far_domain_pref=0.6,
        verify_chain_depth=3,
        accept_new_edges=True,
    ),
    EngineMode.CONSOLIDATING: ModeProfile(
        # Szigorú "no new" mód: a meglévő gráf rendeződik (decay/pruning),
        # de új élt nem fogadunk be. Ez a Modul H replay-fázis csírája.
        forbidden_weight=1.0,
        negation_threshold=1.0,
        far_domain_pref=0.0,
        verify_chain_depth=1,
        accept_new_edges=False,
    ),
}


def default_profile(mode: EngineMode) -> ModeProfile:
    """Egy adott mód alap-profiljának kérdezése (immutable copy)."""
    return replace(DEFAULT_PROFILES[mode])


def all_modes() -> list[EngineMode]:
    """Stabil sorrendben a négy mód."""
    return [
        EngineMode.FOCUSED,
        EngineMode.EXPLORATORY,
        EngineMode.HYPNAGOGIC,
        EngineMode.CONSOLIDATING,
    ]
