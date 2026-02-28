"""species_engine — Day6 개체군 동역학 (N_s, growth − competition − predation)

dN_s/dt = r·N_s·gpp_scale
          − Σ_j C[s][j]·N_s·N_j          (Lotka-Volterra 경쟁, 행렬)
          − Σ_pred A[pred][s]·N_pred·N_s  (포식 손실)
          + Σ_prey A[s][prey]·N_s·N_prey  (포식 이득, 효율 η)

입력: 밴드별 자원(GPP, N_soil), 환경(T, CO₂), InteractionGraph.
출력: 밴드별 종 밀도 N_s, 성장률, 경쟁·포식 항.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .interaction_graph import InteractionGraph


@dataclass
class SpeciesState:
    """단일 밴드 또는 전 밴드의 종별 개체군 상태."""
    n_species: List[float]  # 종별 밀도 [개체/m²] or 바이오매스
    band_idx: Optional[int] = None  # None 이면 전 밴드 집계

    def total_density(self) -> float:
        return sum(self.n_species)


class SpeciesEngine:
    """개체군 동역학: growth − competition − predation.

    Day3 GPP·자원과 연동하여 성장, InteractionGraph 로부터
    경쟁 행렬 C[i][j] 와 포식 행렬 A[i][j] 를 받아 ODE 적분.

    Parameters
    ----------
    n_traits : int
        트레이트(종) 수.
    growth_rate : float
        기본 성장률 r [1/yr].
    competition_strength : float
        interaction_graph 없을 때 기본 경쟁 강도 (스칼라 폴백).
    predation_efficiency : float
        포식자가 피식자 생체량을 자신의 성장으로 전환하는 효율 η (0~1).
    """

    def __init__(
        self,
        n_traits: int = 4,
        growth_rate: float = 0.1,
        competition_strength: float = 0.01,
        predation_efficiency: float = 0.1,
    ) -> None:
        self.n_traits = n_traits
        self.growth_rate = growth_rate
        self.competition_strength = competition_strength
        self.predation_efficiency = predation_efficiency

    def step(
        self,
        state: SpeciesState,
        env: Dict[str, Any],
        dt_yr: float,
        graph: Optional["InteractionGraph"] = None,
    ) -> SpeciesState:
        """한 스텝 적분.

        dN_s/dt = r·N_s·gpp_scale
                  − Σ_j C[s][j]·N_s·N_j
                  − Σ_pred A[pred][s]·N_pred·N_s   (피식 손실)
                  + η·Σ_prey A[s][prey]·N_s·N_prey  (포식 이득)

        graph=None 이면 competition = competition_strength * N_s * total 폴백.
        """
        n = len(state.n_species)
        N = [max(0.0, x) for x in state.n_species]
        total = sum(N)
        gpp_scale = float(env.get("GPP_scale", 1.0))  # 0~1 자원 제한

        new_n: List[float] = []
        for s in range(n):
            Ns = N[s]

            # ── 성장 ─────────────────────────────────────────
            growth = self.growth_rate * gpp_scale * Ns

            # ── 경쟁 (Lotka-Volterra C[s][j] 행렬) ───────────
            if graph is not None:
                C_row = graph.competition[s]  # C[s][j], j=0..n-1
                competition = Ns * sum(C_row[j] * N[j] for j in range(min(n, graph.n_species)))
            else:
                competition = self.competition_strength * Ns * total

            # ── 포식 손실: Σ_pred A[pred][s] · N_pred · Ns ──
            predation_loss = 0.0
            if graph is not None:
                for pred in range(min(n, graph.n_species)):
                    predation_loss += graph.predation[pred][s] * N[pred] * Ns

            # ── 포식 이득: η · Σ_prey A[s][prey] · Ns · N_prey ─
            predation_gain = 0.0
            if graph is not None:
                for prey in range(min(n, graph.n_species)):
                    predation_gain += (
                        self.predation_efficiency
                        * graph.predation[s][prey]
                        * Ns
                        * N[prey]
                    )

            dN = (growth - competition - predation_loss + predation_gain) * dt_yr
            new_n.append(max(0.0, Ns + dN))

        return SpeciesState(
            n_species=new_n,
            band_idx=state.band_idx,
        )


def make_species_engine(
    n_traits: int = 4,
    growth_rate: float = 0.1,
    competition_strength: float = 0.01,
    predation_efficiency: float = 0.1,
) -> SpeciesEngine:
    return SpeciesEngine(
        n_traits=n_traits,
        growth_rate=growth_rate,
        competition_strength=competition_strength,
        predation_efficiency=predation_efficiency,
    )


__all__ = ["SpeciesEngine", "SpeciesState", "make_species_engine"]
