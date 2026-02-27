"""_constants.py — Day5 생물 이동 레이어 공유 상수

모든 리터럴 상수는 여기에 집중.
mobility_engine / food_web / seed_transport 에서 import해서 사용.

단위 표기:
    [1/yr]       = 연간 비율 (dimensionless per year)
    [g N/m²/yr]  = 단위 면적당 질소 플럭스
    [kgC/m²/yr]  = 단위 면적당 탄소 플럭스

단위 설계 원칙:
    - 이동률(migration_rates)은 항상 [1/yr].
    - 씨드 분산 계수(R_SEED_DISPERSAL)는 [−] (무차원) — 이동률에 곱해서 이동률 스케일 유지.
    - 구아노 계수(R_GUANO_N)는 [g N · yr/m²] — 이동률[1/yr]에 곱하면 플럭스[g N/m²/yr].
    - 포식률(R_PREDATION)은 [−] (무차원) — base_rate[1/yr]에 곱해 포식 비율.
"""

# ── mobility_engine 상수 ──────────────────────────────────────────────────────

# BirdAgent
R_SEED_DISPERSAL: float = 0.02
# [−] 씨드 분산 스케일 계수.
# seed_flux[i] = R_SEED_DISPERSAL * migration_rate_i * pioneer[i]  → 단위 = pioneer 단위/yr

R_GUANO_N: float = 0.1
# [g N·yr / m²] 구아노 N 계수.
# guano[i] = R_GUANO_N * migration_rate_i  [1/yr] → 결과 [g N/m²/yr]
# (base_rate=0.05 [1/yr] 기준 → guano ≈ 0.005 g N/m²/yr, 합리적 범위)

# FishAgent
R_PREDATION: float = 0.1
# [−] phyto 포식 스케일 계수 (무차원).
# predation[i] = R_PREDATION * base_rate[1/yr] * phyto[i]  → 결과 [phyto_unit/yr]

R_RESP_CO2: float = 0.3
# [−] FishAgent 경로 CO₂ 호흡 계수 (무차원).
# co2_resp[i] = R_RESP_CO2 * predation[i]  (FoodWeb 내부 rf 와 별도 경로; 이중 계산 주의)

# ── food_web 상수 ─────────────────────────────────────────────────────────────

ALPHA_CO2_ABS: float = 0.5
# [−] net_co2_flux() 흡수 계수.
# co2_abs = ALPHA_CO2_ABS * phyto * gpp  (gpp 있는 경우)
# 단위: phyto, gpp 가 모두 arbitrary units 이면 co2_abs 도 같은 스케일.
# → net_co2_flux 는 같은 arbitrary 스케일에서 (호흡 - 흡수) 를 반환.
# 대기 연동 시 단위 변환 계수(kgC/m²/yr per unit)를 외부에서 곱할 것.

DEFAULT_GROWTH_PHYTO: float = 1.0   # [1/yr] phyto 내재 성장률
DEFAULT_GRAZING_RATE: float = 0.5   # [1/yr·biomass⁻¹] 초식 포식률 (Lotka-Volterra 형)
DEFAULT_PREDATION:    float = 0.3   # [1/yr·biomass⁻¹] 상위 포식률
DEFAULT_RESP_FRAC:    float = 0.5   # [−] 포식→호흡 CO₂ 비율
M_CARNIVORE:          float = 0.1   # [1/yr] carnivore 선형 사망률 (장기 폭증 방지)
M_HERBIVORE:          float = 0.05  # [1/yr] herbivore 선형 사망률 (장기 폭증 방지)
# M_HERBIVORE < M_CARNIVORE: herbivore는 포식자보다 기저 사망률이 낮다 (생태학적 합리적 범위)

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
    "M_HERBIVORE",
]
