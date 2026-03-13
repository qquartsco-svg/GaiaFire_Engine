"""mobility_engine — Day5 생물 이동 에이전트 (Bird/Fish)

이 모듈은 Day5 레이어의 "움직이는 생명체"를
아주 단순한 형태로 표현한다.

역할:
    - 위도 밴드별로 정의된 biosphere 상태(B_seed 등)에 대해
      이동률(migration rate)을 계산하는 helper.
    - 실제 mass transport는 seed_transport.SeedTransport 가 담당하고,
      여기서는 "어느 밴드가 어느 이웃으로 얼마나 자주 이동하려 하는가"
      를 rate [1/yr] 로 제공한다.

Loop 연결:
    Loop F: BirdAgent 씨드 분산 → pioneer 원거리 확산
    Loop G: 구아노 N → nitrogen.N_soil
    Loop H: FishAgent 포식 → phyto 감소 → CO₂ 호흡 변화

수식:
    rate_i = base_rate * max(0, 1 + o2_sensitivity * (O2_i - O2_ref))
    구아노 플럭스: r_guano * base_rate  [g N/m²/yr per band]
    씨드 플럭스:   r_seed * migration_rates[i]  [/yr]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import math

from ._constants import (
    R_SEED_DISPERSAL,
    R_GUANO_N,
    R_PREDATION,
    R_RESP_CO2,
)


# ── 유틸리티 ───────────────────────────────────────────────────────────────────

def _ring_neighbors(n_bands: int) -> List[List[int]]:
    """위도 밴드 이웃 목록 생성.

    물리적 위도 구조:
        밴드 0        = 남극 (−90°) → 오른쪽(1)만 이웃
        밴드 1~n-2   = 중위도      → 양쪽(i-1, i+1) 이웃
        밴드 n-1     = 북극 (+90°) → 왼쪽(n-2)만 이웃

    위도 경계에서 wrap-around 하지 않는다.
    """
    neighbors: List[List[int]] = []
    for i in range(n_bands):
        nb: List[int] = []
        if i > 0:
            nb.append(i - 1)        # 남쪽 이웃
        if i < n_bands - 1:
            nb.append(i + 1)        # 북쪽 이웃
        neighbors.append(nb)
    return neighbors


# ── BirdAgent ─────────────────────────────────────────────────────────────────

@dataclass
class BirdAgent:
    """새 무리(BirdAgent)의 이동 특성.

    Attributes
    ----------
    n_bands : int
        위도 밴드 수 (latitude_bands.BAND_COUNT 와 일치 권장).
    base_rate : float
        기본 이동률 [1/yr]. dt_yr * base_rate << 1 권장.
    o2_sensitivity : float
        대기 O2 에 따른 이동률 스케일링 계수.
        rate_i = base_rate * (1 + o2_sensitivity * (O2_i - O2_ref)).
    o2_ref : float
        기준 O2 몰분율 (예: 0.21).
    r_seed : float
        씨드 분산 계수 (Loop F).
    r_guano : float
        구아노 N 기여 계수 (Loop G).
    """

    n_bands: int
    base_rate: float = 0.05
    o2_sensitivity: float = 1.0
    o2_ref: float = 0.21
    r_seed: float = R_SEED_DISPERSAL
    r_guano: float = R_GUANO_N

    def __post_init__(self) -> None:
        self._neighbors = _ring_neighbors(self.n_bands)

    @property
    def neighbors(self) -> List[List[int]]:
        """위도 밴드 링 구조의 이웃 인덱스."""
        return self._neighbors

    def migration_rates(
        self,
        o2_by_band: Optional[List[float]] = None,
    ) -> List[float]:
        """각 밴드의 effective migration rate [1/yr] 를 반환.

        방정식:
            rate_i = base_rate * scale_i
            scale_i = max(0, 1 + s * (O2_i - O2_ref))  (옵션)
        """
        if o2_by_band is None:
            return [self.base_rate] * self.n_bands

        scaled: List[float] = []
        for o2 in o2_by_band:
            delta = o2 - self.o2_ref
            scale = max(0.0, 1.0 + self.o2_sensitivity * delta)
            scaled.append(self.base_rate * scale)
        return scaled

    def seed_flux(
        self,
        pioneer: List[float],
        o2_by_band: Optional[List[float]] = None,
    ) -> List[float]:
        """Loop F: 씨드 분산 플럭스 [/yr].

        flux[i→j] = r_seed * rate_i * pioneer[i]
        반환: 각 밴드로 유입되는 씨드 flux (이웃 합산)
        """
        rates = self.migration_rates(o2_by_band)
        flux_in = [0.0] * self.n_bands
        for i in range(self.n_bands):
            out = self.r_seed * rates[i] * pioneer[i]
            for j in self._neighbors[i]:
                flux_in[j] += out / len(self._neighbors[i])
        return flux_in

    def guano_flux(
        self,
        o2_by_band: Optional[List[float]] = None,
    ) -> List[float]:
        """Loop G: 구아노 N 기여 [g N/m²/yr].

        guano[i] = r_guano * rate_i
        """
        rates = self.migration_rates(o2_by_band)
        return [self.r_guano * r for r in rates]


# ── FishAgent ─────────────────────────────────────────────────────────────────

@dataclass
class FishAgent:
    """해양 어류/플랑크톤 무리의 단순 이동 특성.

    Loop H (먹이사슬):
        phyto[i] × B_fish → 포식 → CO₂ 호흡
    """

    n_bands: int
    base_rate: float = 0.02
    r_pred: float = R_PREDATION
    r_co2: float = R_RESP_CO2

    def __post_init__(self) -> None:
        self._neighbors = _ring_neighbors(self.n_bands)

    @property
    def neighbors(self) -> List[List[int]]:
        return self._neighbors

    def migration_rates(self) -> List[float]:
        """각 밴드의 effective migration rate [1/yr]."""
        return [self.base_rate] * self.n_bands

    def predation_flux(self, phyto: List[float]) -> List[float]:
        """Loop H: phyto 포식량 [/yr].

        pred[i] = r_pred * base_rate * phyto[i]
        """
        return [self.r_pred * self.base_rate * p for p in phyto]

    def co2_resp_flux(self, phyto: List[float]) -> List[float]:
        """Loop H: CO₂ 호흡 플럭스 [상대값/yr].

        co2[i] = r_co2 * predation[i]
        """
        pred = self.predation_flux(phyto)
        return [self.r_co2 * p for p in pred]


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_bird_agent(n_bands: int = 12) -> BirdAgent:
    """기본 BirdAgent 생성 helper."""
    return BirdAgent(n_bands=n_bands)


def make_fish_agent(n_bands: int = 12) -> FishAgent:
    """기본 FishAgent 생성 helper."""
    return FishAgent(n_bands=n_bands)


__all__ = [
    "BirdAgent",
    "FishAgent",
    "make_bird_agent",
    "make_fish_agent",
    "R_SEED_DISPERSAL",
    "R_GUANO_N",
    "R_PREDATION",
    "R_RESP_CO2",
]
