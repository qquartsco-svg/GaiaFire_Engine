"""_constants.py — Day5 생물 이동 레이어 공유 상수

모든 리터럴 상수는 여기에 집중.
mobility_engine / food_web / seed_transport 에서 import해서 사용.

단위 표기:
    [1/yr]       = 연간 비율
    [g N/m²/yr]  = 단위 면적당 질소 플럭스
    [kgC/m²/yr]  = 단위 면적당 탄소 플럭스
"""

# ── mobility_engine 상수 ──────────────────────────────────────────────────────

# BirdAgent
R_SEED_DISPERSAL: float = 0.02    # [1/yr] 씨드 분산률
R_GUANO_N:        float = 0.005   # [g N/m²/yr] 구아노 N 기여 (per base_rate unit)

# FishAgent
R_PREDATION:  float = 0.1    # [1/yr] phyto 포식률
R_RESP_CO2:   float = 0.3    # [kgC/m²/yr] CO₂ 호흡 계수 (per predation unit)

# ── food_web 상수 ─────────────────────────────────────────────────────────────

ALPHA_CO2_ABS:        float = 0.5   # CO₂ 흡수 계수 (phyto 기준)
DEFAULT_GROWTH_PHYTO: float = 1.0   # [1/yr] phyto 내재 성장률
DEFAULT_GRAZING_RATE: float = 0.5   # [1/yr] 초식 포식률
DEFAULT_PREDATION:    float = 0.3   # [1/yr] 상위 포식률
DEFAULT_RESP_FRAC:    float = 0.5   # [-] 호흡 CO₂ 비율
M_CARNIVORE:          float = 0.1   # [1/yr] carnivore 사망률 (장기 폭증 방지)

__all__ = [
    # mobility
    "R_SEED_DISPERSAL",
    "R_GUANO_N",
    "R_PREDATION",
    "R_RESP_CO2",
    # food_web
    "ALPHA_CO2_ABS",
    "DEFAULT_GROWTH_PHYTO",
    "DEFAULT_GRAZING_RATE",
    "DEFAULT_PREDATION",
    "DEFAULT_RESP_FRAC",
    "M_CARNIVORE",
]
