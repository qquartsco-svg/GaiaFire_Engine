"""day5_coupling — Day5 → Day6 연결 (transport biomass → contact rate)

핵심 수식:
    k_encounter(band) = k_base + k_transport * Σ_j |flux_ij|

Day5 BirdAgent.seed_flux() / FishAgent.predation_flux() 가 생성한
밴드 간 바이오매스 이동량이 클수록 같은 밴드 내 개체 조우 확률 증가.
→ contact_engine.ContactEngine 의 k_encounter 를 밴드별 동적으로 설정.

연결 다이어그램:
    Day5 mobility_engine
        BirdAgent.seed_flux()      → flux_in[band]
        FishAgent.predation_flux() → flux_in[band]
                ↓
    Day5Coupler.compute_k_encounter(flux_by_band)
                ↓   k_encounter[band]
    Day6 ContactEngine.compute(rho, k_override=k_encounter[band])
                ↓   p_contact_scalar
    Day6 MutationEngine.step(p_contact=...)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CouplingResult:
    """밴드별 조우율 스케일 결과."""
    k_encounter_by_band: List[float]  # [bands] 동적 k_encounter
    flux_magnitude_by_band: List[float]  # 디버깅용 플럭스 크기


class Day5Coupler:
    """Day5 transport flux → Day6 contact rate 변환기.

    contact_rate ∝ transported_biomass_gradient
    k_encounter(band) = k_base + k_transport * flux_magnitude(band)

    Parameters
    ----------
    k_base : float
        플럭스 없을 때 기본 조우율 (배경 이동·확산).
    k_transport : float
        플럭스 단위당 조우율 증가 계수 [k_encounter / flux_unit].
    flux_scale : float
        Day5 flux 값 정규화 스케일 (단위 맞춤).
    """

    def __init__(
        self,
        k_base: float = 0.1,
        k_transport: float = 1.0,
        flux_scale: float = 1.0,
    ) -> None:
        self.k_base = max(0.0, k_base)
        self.k_transport = max(0.0, k_transport)
        self.flux_scale = max(1e-12, flux_scale)

    def compute_k_encounter(
        self,
        bird_flux_by_band: Optional[List[float]] = None,
        fish_flux_by_band: Optional[List[float]] = None,
        n_bands: int = 12,
    ) -> CouplingResult:
        """Day5 플럭스 → 밴드별 k_encounter 계산.

        flux_magnitude(band) = |bird_flux(band)| + |fish_flux(band)|
        k_encounter(band)    = k_base + k_transport * flux_magnitude / flux_scale

        Parameters
        ----------
        bird_flux_by_band : List[float], optional
            BirdAgent.seed_flux() 또는 guano_flux() 반환값.
        fish_flux_by_band : List[float], optional
            FishAgent.predation_flux() 반환값.
        n_bands : int
            밴드 수 (flux가 None일 때 기본값).
        """
        nb = n_bands
        if bird_flux_by_band is not None:
            nb = len(bird_flux_by_band)
        elif fish_flux_by_band is not None:
            nb = len(fish_flux_by_band)

        bird = bird_flux_by_band or [0.0] * nb
        fish = fish_flux_by_band or [0.0] * nb

        # 길이 맞춤
        bird = list(bird) + [0.0] * max(0, nb - len(bird))
        fish = list(fish) + [0.0] * max(0, nb - len(fish))

        flux_mag: List[float] = []
        k_enc: List[float] = []
        for i in range(nb):
            mag = abs(bird[i]) + abs(fish[i])
            flux_mag.append(mag)
            k_enc.append(self.k_base + self.k_transport * mag / self.flux_scale)

        return CouplingResult(
            k_encounter_by_band=k_enc,
            flux_magnitude_by_band=flux_mag,
        )

    def p_contact_for_band(
        self,
        band_idx: int,
        rho: List[float],
        k_encounter: float,
        V_cell: float = 1.0,
    ) -> float:
        """밴드 하나의 평균 p_contact 스칼라 (ContactEngine 없이 빠른 계산).

        P_avg = (Σ_i ρ_i)² * k_encounter / (n² * V_cell)
        """
        n = len(rho)
        if n == 0:
            return 0.0
        rho_sum = sum(max(0.0, r) for r in rho)
        return rho_sum * rho_sum * k_encounter / (max(1, n * n) * max(1e-12, V_cell))


def make_day5_coupler(
    k_base: float = 0.1,
    k_transport: float = 1.0,
    flux_scale: float = 1.0,
) -> Day5Coupler:
    return Day5Coupler(k_base=k_base, k_transport=k_transport, flux_scale=flux_scale)


__all__ = ["Day5Coupler", "CouplingResult", "make_day5_coupler"]
