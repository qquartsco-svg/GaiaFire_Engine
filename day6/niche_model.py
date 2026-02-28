"""niche_model — Day6 서식지 분할·자원 경쟁

밴드별 land_fraction, 자원(GPP, N_soil)에 따른 니치 분할.
자원 한계(resource_capacity) 내에서 종별 점유(occupancy) 갱신.

업데이트 규칙:
  raw_growth_i = occupancy_i * r_i * gpp_scale
  demand_i     = raw_growth_i * dt_yr
  total_demand = Σ_i demand_i

  capacity = resource_capacity * land_fraction  (유효 용량)

  if total_demand <= capacity:
      new_occupancy_i = occupancy_i + demand_i   (자원 충분 → 무제한 성장)
  else:
      # 자원 비례 배분 (proportional rationing)
      new_occupancy_i = capacity * demand_i / total_demand
      if demand_i = 0 → new_occupancy_i = 0

추가: 자원 초과 시 land_fraction 으로 클램핑 (육지/해양 물리적 한계).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class NicheState:
    """밴드별 니치 점유 상태."""
    band_idx: int
    land_fraction: float          # 육지 비율 [0,1]
    resource_capacity: float      # GPP or N 등 자원 용량 [무차원 또는 g/m²]
    occupancy: List[float]        # 종별 점유량 [개체/m² 또는 바이오매스]


class NicheModel:
    """서식지(밴드)별 자원 용량과 종 간 경쟁에 의한 점유.

    land_fraction_by_band 에 따라 육지에서만 활동하는 Day6 크롤러와 연동.

    Parameters
    ----------
    n_bands : int
        위도 밴드 수 (기본 12).
    n_species : int
        종 수 (기본 4).
    growth_rate : float
        종별 공통 성장률 r [1/yr].
    """

    def __init__(
        self,
        n_bands: int = 12,
        n_species: int = 4,
        growth_rate: float = 0.1,
    ) -> None:
        self.n_bands = n_bands
        self.n_species = n_species
        self.growth_rate = growth_rate

    def _step_band(
        self,
        state: NicheState,
        env: Dict[str, Any],
        dt_yr: float,
    ) -> NicheState:
        """단일 밴드 점유 갱신.

        자원 비례 배분:
          demand_i  = occupancy_i * r * gpp_scale * dt_yr
          capacity  = resource_capacity * land_fraction
          if Σ demand <= capacity: 자유 성장
          else: proportional rationing → new_occ_i = capacity * (demand_i / Σ demand)
        """
        gpp_scale = float(env.get("GPP_scale", 1.0))
        capacity = state.resource_capacity * max(0.0, state.land_fraction)

        demands: List[float] = []
        for occ in state.occupancy:
            raw = max(0.0, occ) * self.growth_rate * gpp_scale * dt_yr
            demands.append(raw)

        total_demand = sum(demands)
        current_total = sum(max(0.0, o) for o in state.occupancy)

        new_occ: List[float] = []
        n_occ = len(state.occupancy)

        if capacity <= 0.0:
            # 자원 없음 (육지 없는 셀 등) → 전 종 점유 0
            new_occ = [0.0] * n_occ
        elif total_demand <= 0.0:
            # 수요 없음 (점유 0) → 현상 유지
            new_occ = [max(0.0, o) for o in state.occupancy]
        elif current_total + total_demand <= capacity:
            # 자원 충분 → 자유 성장 (capacity 상한 클램핑)
            new_occ = [
                min(capacity, max(0.0, state.occupancy[i]) + demands[i])
                for i in range(n_occ)
            ]
        else:
            # 자원 부족 → 비례 배분 (proportional rationing)
            # new_occ_i = capacity * (occ_i + demand_i) / (Σ occ_j + Σ demand_j)
            total_raw = current_total + total_demand  # 항상 > 0 (total_demand > 0 보장)
            new_occ = [
                capacity * (max(0.0, state.occupancy[i]) + demands[i]) / total_raw
                for i in range(n_occ)
            ]

        return NicheState(
            band_idx=state.band_idx,
            land_fraction=state.land_fraction,
            resource_capacity=state.resource_capacity,
            occupancy=new_occ,
        )

    def step(
        self,
        state: List[NicheState],
        env_by_band: List[Dict[str, Any]],
        dt_yr: float,
    ) -> List[NicheState]:
        """전 밴드 한 스텝: 자원 한계 내에서 점유 갱신."""
        result: List[NicheState] = []
        for i, s in enumerate(state):
            env = env_by_band[i] if i < len(env_by_band) else {}
            result.append(self._step_band(s, env, dt_yr))
        return result


def make_niche_model(
    n_bands: int = 12,
    n_species: int = 4,
    growth_rate: float = 0.1,
) -> NicheModel:
    return NicheModel(n_bands=n_bands, n_species=n_species, growth_rate=growth_rate)


__all__ = ["NicheModel", "NicheState", "make_niche_model"]
