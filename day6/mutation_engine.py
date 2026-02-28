"""mutation_engine — Day6 변이·종분화 생성기

dN_new/dt = μ * P_contact(A,B) * fitness_pressure(env)

μ_eff = base_mutation_rate * p_contact * fitness_pressure(env)
→ 확률 μ_eff * dt_yr 로 MutationEvent 생성 (stochastic).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import random


@dataclass
class MutationEvent:
    """단일 변이/종분화 이벤트."""
    parent_trait_idx: int
    new_trait_idx: int
    band_idx: int
    rate: float
    via_recombination: bool = False  # True면 이중 재조합 경로


class MutationEngine:
    """변이율 μ, fitness_pressure(env) 에 따른 신종 출현.
    stochastic branching process 스켈레톤.
    binary_convergence_pressure: 이진 재조합(남·녀) 프로토콜 수렴 압력.
    """
    def __init__(
        self,
        base_mutation_rate: float = 1e-4,
        stress_sensitivity: float = 0.5,
        binary_convergence_pressure: bool = False,
    ) -> None:
        self.base_mutation_rate = base_mutation_rate
        self.stress_sensitivity = stress_sensitivity
        self.binary_convergence_pressure = binary_convergence_pressure

    def fitness_pressure(self, env: Dict[str, Any]) -> float:
        """환경 스트레스 (T, CO₂, N 등). 극단적일수록 변이 폭발."""
        t = env.get("T_surface", 288.0)
        co2 = env.get("CO2_ppm", 400.0)
        t_stress = 1.0 + 0.1 * abs(t - 288.0) / 50.0
        co2_stress = 1.0 + 0.1 * abs(co2 - 400.0) / 200.0
        return min(3.0, 1.0 + self.stress_sensitivity * ((t_stress - 1.0) + (co2_stress - 1.0)))

    def step(
        self,
        p_contact: float,
        env: Dict[str, Any],
        dt_yr: float,
        band_idx: int = 0,
        n_traits: int = 4,
        rng: Optional[random.Random] = None,
    ) -> List[MutationEvent]:
        """조우 확률과 환경에 따른 변이 이벤트 목록.

        μ_eff = base_mutation_rate * p_contact * fitness_pressure(env)
        → 모든 (parent, new) 쌍에 대해 독립 베르누이 시행:
          P(event | pair) = min(1, μ_eff * dt_yr)
          최대 n_traits*(n_traits-1) 개 이벤트 동시 발생 가능.
          이것이 "난교 파티" — 다중 쌍 동시 교차의 수학적 표현.

        binary_convergence_pressure=True 이면:
          → via_recombination=True 플래그 → 이진 재조합 경로 우선
          → 환경 스트레스가 높을수록 binary OS로 수렴 압력 증가.
        """
        rng = rng or random.Random()
        if n_traits <= 0:
            return []
        fp = self.fitness_pressure(env)
        mu_eff = self.base_mutation_rate * max(0.0, p_contact) * fp
        prob_per_pair = min(1.0, mu_eff * dt_yr)

        events: List[MutationEvent] = []
        for parent in range(n_traits):
            for new in range(n_traits):
                if parent == new:
                    continue          # 자기 자신으로 변이 없음
                if rng.random() < prob_per_pair:
                    events.append(
                        MutationEvent(
                            parent_trait_idx=parent,
                            new_trait_idx=new,
                            band_idx=band_idx,
                            rate=mu_eff,
                            via_recombination=self.binary_convergence_pressure,
                        )
                    )
        return events


def make_mutation_engine(
    base_mutation_rate: float = 1e-4,
    stress_sensitivity: float = 0.5,
    binary_convergence_pressure: bool = False,
) -> MutationEngine:
    return MutationEngine(
        base_mutation_rate=base_mutation_rate,
        stress_sensitivity=stress_sensitivity,
        binary_convergence_pressure=binary_convergence_pressure,
    )


__all__ = ["MutationEngine", "MutationEvent", "make_mutation_engine"]
