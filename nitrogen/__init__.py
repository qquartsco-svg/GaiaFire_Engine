"""nitrogen/ — 질소 순환 (넷째날 순환 1) — GaiaFire_Engine 독립 버전

N₂ ↔ 고정질소(NH₃, NO₃) ↔ 단백질 ↔ 사체분해 ↔ N₂
"""

from .fixation import (
    NitrogenFixation,
    FixationResult,
    make_fixation_engine,
    K_FIX_MAX,
    O2_HALF_N2FIX,
    T_OPT_N2FIX,
)

from .cycle import (
    NitrogenCycle,
    NitrogenState,
    make_nitrogen_cycle,
    K_UPTAKE,
    K_DENITRIFY,
    K_DECOMP,
)

__all__ = [
    "NitrogenFixation", "FixationResult", "make_fixation_engine",
    "K_FIX_MAX", "O2_HALF_N2FIX", "T_OPT_N2FIX",
    "NitrogenCycle", "NitrogenState", "make_nitrogen_cycle",
    "K_UPTAKE", "K_DENITRIFY", "K_DECOMP",
]

__version__ = "1.0.0"
