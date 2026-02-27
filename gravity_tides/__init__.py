"""gravity_tides/ — 중력-조석 주기 (넷째날 순환 3) — GaiaFire_Engine 독립 버전

달+태양 조석 → 해양 혼합 → 영양염 upwelling → 식물플랑크톤 → CO₂ 격리
"""

from .tidal_mixing import (
    TidalField,
    TidalState,
    make_tidal_field,
    F_MOON_REF,
    K_MIX,
    K_UPWELLING,
)

from .ocean_nutrients import (
    OceanNutrients,
    OceanState,
    make_ocean_nutrients,
    K_PHYTO_GROWTH,
    K_EXPORT,
    CO2_PPM_PER_GT_CO2,
)

__all__ = [
    "TidalField", "TidalState", "make_tidal_field",
    "F_MOON_REF", "K_MIX", "K_UPWELLING",
    "OceanNutrients", "OceanState", "make_ocean_nutrients",
    "K_PHYTO_GROWTH", "K_EXPORT", "CO2_PPM_PER_GT_CO2",
]

__version__ = "1.0.0"
