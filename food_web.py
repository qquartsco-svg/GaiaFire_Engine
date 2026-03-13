"""food_web — Day5 단순 먹이사슬 ODE 스켈레톤.

이 모듈은 Day5 확장을 위한 최소 Food Web 모델을 제공한다.
phyto → herbivore → carnivore 흐름과 CO₂ 호흡 포함.

Loop H 연결:
    FishAgent 포식 → phyto 감소
    phyto 감소 → CO₂ 흡수 감소 → 대기 CO₂ 증가

수식:
    dP/dt = GPP - grazing                      (phyto)
    dH/dt = grazing - pred                     (herbivore)
    dC/dt = pred - m_carn * C                  (carnivore, 사망률 포함)
    co2_resp_yr = rf * (grazing + pred) / dt   (이 스텝 연간 환산 플럭스)

FishAgent 연결 (Loop H):
    env["fish_predation"] = FishAgent.predation_flux()[band]
    → phyto 추가 감소항으로 주입
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from ._constants import (
    ALPHA_CO2_ABS,
    DEFAULT_GROWTH_PHYTO,
    DEFAULT_GRAZING_RATE,
    DEFAULT_PREDATION,
    DEFAULT_RESP_FRAC,
    M_CARNIVORE,
)


# ── 스냅샷 ────────────────────────────────────────────────────────────────────

@dataclass
class TrophicState:
    """단일 위도 밴드/셀에 대한 먹이사슬 상태."""

    phyto:        float   # 1차 생산자 (식물/플랑크톤) 바이오매스
    herbivore:    float   # 초식동물/소비자
    carnivore:    float   # 상위 포식자
    co2_resp_yr:  float   # (이 스텝에서의) 연간 환산 호흡 CO₂ 플럭스 [kgC/m²/yr]

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

        # 기본 step
        state = fw.step(state, env={"GPP": 0.5}, dt_yr=1.0)

        # FishAgent 포식량 주입 (Loop H)
        fish_pred = fish_agent.predation_flux(phyto_by_band)
        state = fw.step(state, env={"GPP": 0.5, "fish_predation": fish_pred[band]}, dt_yr=1.0)

        print(state.co2_resp_yr)   # → atmosphere CO₂ 가산 [kgC/m²/yr]
    """

    def __init__(
        self,
        growth_rate_phyto: float = DEFAULT_GROWTH_PHYTO,
        grazing_rate: float = DEFAULT_GRAZING_RATE,
        predation_rate: float = DEFAULT_PREDATION,
        respiration_fraction: float = DEFAULT_RESP_FRAC,
        mortality_carnivore: float = M_CARNIVORE,
    ) -> None:
        self.gp = growth_rate_phyto
        self.gr = grazing_rate
        self.pr = predation_rate
        self.rf = respiration_fraction
        self.mc = mortality_carnivore

    def step(
        self,
        state: TrophicState,
        env: Dict[str, Any],
        dt_yr: float,
    ) -> TrophicState:
        """간단한 Euler step.

        Args:
            state:  현재 트로픽 상태
            env:    환경 딕셔너리.
                    "GPP"             : float  — 1차 생산력 [상대값]
                    "fish_predation"  : float  — FishAgent 포식량 [/yr] (Loop H)
            dt_yr:  타임스텝 [yr]
        """
        phyto = state.phyto
        herb  = state.herbivore
        carn  = state.carnivore

        # 1차 생산: 환경 입력(GPP 근사)
        gpp = float(env.get("GPP", self.gp * phyto))

        # FishAgent 포식 (Loop H) — 외부에서 주입, 없으면 0
        fish_pred = float(env.get("fish_predation", 0.0))

        # grazing / predation
        grazing  = self.gr * herb * phyto * dt_yr
        pred     = self.pr * carn * herb  * dt_yr

        # carnivore 사망률 (장기 폭증 방지)
        carn_death = self.mc * carn * dt_yr

        # phyto: GPP 성장 - grazing - FishAgent 포식
        phyto_new = max(0.0, phyto + (gpp * dt_yr) - grazing - fish_pred * dt_yr)
        herb_new  = max(0.0, herb  + grazing - pred)
        carn_new  = max(0.0, carn  + pred - carn_death)

        # 호흡 CO₂ — 이 스텝 방출량을 연간 플럭스로 환산
        if dt_yr <= 0.0:
            co2_rate = 0.0
        else:
            # fish_pred도 호흡 기여 (포식 → 호흡)
            delta_co2 = self.rf * (grazing + pred + fish_pred * dt_yr)
            co2_rate  = delta_co2 / dt_yr   # [kgC/m²/yr]

        return TrophicState(
            phyto       = phyto_new,
            herbivore   = herb_new,
            carnivore   = carn_new,
            co2_resp_yr = co2_rate,
        )

    def net_co2_flux(self, state: TrophicState, gpp: float | None = None) -> float:
        """Loop H: net CO₂ 플럭스 [상대값].

        음수 = 흡수, 양수 = 방출.

        Args
        ----
        state: TrophicState
            현재 먹이망 상태.
        gpp: Optional[float]
            1차 생산(GPP) [상대값]. 주어지면 CO₂ 흡수 항을
            GPP와 phyto 둘 다에 비례하도록 스케일링한다.
        """
        if gpp is None:
            co2_abs = ALPHA_CO2_ABS * state.phyto
        else:
            co2_abs = ALPHA_CO2_ABS * state.phyto * gpp
        return state.co2_resp_yr - co2_abs


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_food_web(
    growth_rate_phyto: float = DEFAULT_GROWTH_PHYTO,
    grazing_rate: float = DEFAULT_GRAZING_RATE,
    predation_rate: float = DEFAULT_PREDATION,
    respiration_fraction: float = DEFAULT_RESP_FRAC,
    mortality_carnivore: float = M_CARNIVORE,
) -> FoodWeb:
    """기본 FoodWeb 인스턴스 생성 helper."""
    return FoodWeb(
        growth_rate_phyto=growth_rate_phyto,
        grazing_rate=grazing_rate,
        predation_rate=predation_rate,
        respiration_fraction=respiration_fraction,
        mortality_carnivore=mortality_carnivore,
    )


__all__ = [
    "FoodWeb",
    "TrophicState",
    "make_food_web",
]
