"""food_web — Day5 단순 먹이사슬 ODE 스켈레톤.

이 모듈은 Day5 확장을 위한 최소 Food Web 모델을 제공한다.
phyto → herbivore → carnivore 흐름과 CO₂ 호흡 포함.

Loop H 연결:
    FishAgent 포식 → phyto 감소
    phyto 감소 → CO₂ 흡수 감소 → 대기 CO₂ 증가

수식:
    dP/dt = GPP - grazing  (phyto)
    dH/dt = grazing - pred  (herbivore)
    dC/dt = pred  (carnivore)
    co2_resp += rf * (grazing + pred)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional


# ── 속도 상수 ──────────────────────────────────────────────────────────────────

ALPHA_CO2_ABS        = 0.5   # CO₂ 흡수 계수 (phyto 기준)
DEFAULT_GROWTH_PHYTO = 1.0   # [1/yr] phyto 내재 성장률
DEFAULT_GRAZING_RATE = 0.5   # [1/yr] 초식 포식률
DEFAULT_PREDATION    = 0.3   # [1/yr] 상위 포식률
DEFAULT_RESP_FRAC    = 0.5   # 호흡 CO₂ 비율


# ── 스냅샷 ────────────────────────────────────────────────────────────────────

@dataclass
class TrophicState:
    """단일 위도 밴드/셀에 대한 먹이사슬 상태."""

    phyto:        float   # 1차 생산자 (식물/플랑크톤) 바이오매스
    herbivore:    float   # 초식동물/소비자
    carnivore:    float   # 상위 포식자
    co2_resp_yr:  float   # 연간 호흡으로 방출된 CO₂ 양 [kgC/m²/yr]

    def summary(self) -> str:
        return (
            f"P={self.phyto:.3f} H={self.herbivore:.3f} "
            f"C={self.carnivore:.3f} CO₂_resp={self.co2_resp_yr:.4f}"
        )


# ── FoodWeb ───────────────────────────────────────────────────────────────────

class FoodWeb:
    """아주 단순한 로컬 food web 모델.

    사용법::

        fw = make_food_web()
        state = TrophicState(phyto=0.5, herbivore=0.2, carnivore=0.1, co2_resp_yr=0.0)
        state = fw.step(state, env={"GPP": 0.5}, dt_yr=1.0)
        print(state.co2_resp_yr)   # → atmosphere CO₂ 가산
    """

    def __init__(
        self,
        growth_rate_phyto: float = DEFAULT_GROWTH_PHYTO,
        grazing_rate: float = DEFAULT_GRAZING_RATE,
        predation_rate: float = DEFAULT_PREDATION,
        respiration_fraction: float = DEFAULT_RESP_FRAC,
    ) -> None:
        self.gp = growth_rate_phyto
        self.gr = grazing_rate
        self.pr = predation_rate
        self.rf = respiration_fraction

    def step(
        self,
        state: TrophicState,
        env: Dict[str, Any],
        dt_yr: float,
    ) -> TrophicState:
        """간단한 Euler step.

        Args:
            state:  현재 트로픽 상태
            env:    환경 딕셔너리 (GPP, nutrient_flux 등)
            dt_yr:  타임스텝 [yr]
        """
        phyto = state.phyto
        herb  = state.herbivore
        carn  = state.carnivore

        # 1차 생산: 환경 입력(GPP 근사)
        gpp = float(env.get("GPP", self.gp * phyto))

        # grazing / predation
        grazing = self.gr * herb * phyto * dt_yr
        pred    = self.pr * carn * herb  * dt_yr

        # 업데이트
        phyto_new = max(0.0, phyto + (gpp * dt_yr) - grazing)
        herb_new  = max(0.0, herb  + grazing - pred)
        carn_new  = max(0.0, carn  + pred)

        # 호흡 CO₂ (단순 비율)
        delta_co2 = self.rf * (grazing + pred)
        co2_new   = state.co2_resp_yr + delta_co2

        return TrophicState(
            phyto       = phyto_new,
            herbivore   = herb_new,
            carnivore   = carn_new,
            co2_resp_yr = co2_new,
        )

    def net_co2_flux(self, state: TrophicState, gpp: float) -> float:
        """Loop H: net CO₂ 플럭스 [상대값].

        음수 = 흡수, 양수 = 방출
        co2_abs = ALPHA_CO2_ABS * phyto
        """
        co2_abs = ALPHA_CO2_ABS * state.phyto
        return state.co2_resp_yr - co2_abs


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_food_web(
    growth_rate_phyto: float = DEFAULT_GROWTH_PHYTO,
    grazing_rate: float = DEFAULT_GRAZING_RATE,
    predation_rate: float = DEFAULT_PREDATION,
    respiration_fraction: float = DEFAULT_RESP_FRAC,
) -> FoodWeb:
    """기본 FoodWeb 인스턴스 생성 helper."""
    return FoodWeb(
        growth_rate_phyto=growth_rate_phyto,
        grazing_rate=grazing_rate,
        predation_rate=predation_rate,
        respiration_fraction=respiration_fraction,
    )


__all__ = [
    "FoodWeb",
    "TrophicState",
    "make_food_web",
    "ALPHA_CO2_ABS",
    "DEFAULT_GROWTH_PHYTO",
    "DEFAULT_GRAZING_RATE",
    "DEFAULT_PREDATION",
    "DEFAULT_RESP_FRAC",
]
