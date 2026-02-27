"""cycles/insolation.py — 위도×시간 일사량 계산 + GaiaLoopConnector 연결 (넷째날 순환 2-B)

설계:
    MilankovitchCycle 출력 → 매 시뮬레이션 yr마다
      1) obliquity(t) → GaiaLoopConnector.make_fire_env() 주입
      2) insolation(t, φ) → FireEnvSnapshot.F0 보정
      3) is_glacial(t) → ice_albedo.py 트리거 (구현 예정)

핵심 함수:
    insolation_at(cycle, t_yr, phi_deg)    — 특정 위도 일사량
    make_fire_env_milank(connector, ...)   — Milankovitch 반영 FireEnvSnapshot
    MilankovitchDriver                     — 매 스텝 통합 드라이버

v1.0 (넷째날 순환 2-B)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from .milankovitch import MilankovitchCycle, MilankovitchState, make_earth_cycle

if TYPE_CHECKING:
    from ..gaia_loop_connector import GaiaLoopConnector
    from ..fire.fire_engine import FireEnvSnapshot

EPS = 1e-30

# 위도 기반 일사량 보정 — 지구 대기 투과율 근사
ATM_TRANSMITTANCE = 0.7   # 대기 투과율 (맑은 하늘 평균)


# ── 위도×시간 일사량 ─────────────────────────────────────────────────────────

def insolation_at(
    cycle: MilankovitchCycle,
    t_yr: float,
    phi_deg: float,
    include_atmosphere: bool = True,
) -> float:
    """특정 위도·시점의 일사량 [W/m²].

    Args:
        cycle: MilankovitchCycle 인스턴스
        t_yr: 시간 [yr] (0 = 현재)
        phi_deg: 위도 [deg]
        include_atmosphere: True = 대기 투과율 반영

    Returns:
        Q [W/m²]
    """
    e   = cycle.eccentricity(t_yr)
    eps = cycle.obliquity(t_yr)          # [deg]
    eps_rad = math.radians(eps)
    phi_rad = math.radians(phi_deg)
    psi = cycle.longitude_perihelion(t_yr)

    # 연평균 일사량 기반 (하지 보정 포함)
    # 연평균: Q̄(φ) = F₀/π × (1-e²)^(-1/2) × [sin φ sin δ_max + cos φ H_0 sin H_0]
    # 단순화: cos(φ - ε) 천정각 + (1-e²)^(-1/2) 보정
    delta_max = eps_rad                   # 하지 적위 ≈ 경사각
    cos_zenith_annual = math.cos(abs(phi_rad) - delta_max)
    cos_zenith_annual = max(0.0, min(1.0, cos_zenith_annual))

    # 이심률 보정
    e_factor = 1.0 / math.sqrt(max(1.0 - e * e, EPS))

    Q = cycle.F0 / 4.0 * e_factor * cos_zenith_annual * 4.0   # ×4 되돌림
    # (F0/4 는 전지구 평균, 위도별로는 F0 기반으로 계산)
    Q = max(0.0, Q)

    if include_atmosphere:
        Q *= ATM_TRANSMITTANCE

    return Q


def insolation_grid(
    cycle: MilankovitchCycle,
    t_yr: float,
    phi_bands: Optional[list] = None,
) -> dict:
    """12개 위도 밴드의 일사량 계산.

    Returns:
        dict: {phi_deg: Q_Wm2}
    """
    if phi_bands is None:
        phi_bands = [-82.5, -67.5, -52.5, -37.5, -22.5, -7.5,
                      7.5,  22.5,  37.5,  52.5,  67.5,  82.5]
    return {
        phi: insolation_at(cycle, t_yr, phi)
        for phi in phi_bands
    }


# ── MilankovitchDriver — 매 스텝 통합 드라이버 ───────────────────────────────

@dataclass
class DriverOutput:
    """MilankovitchDriver 매 스텝 출력."""
    t_yr: float
    milank_state: MilankovitchState
    obliquity_scale: float           # → GaiaLoopConnector.Loop C
    F0_corrected: float              # → FireEnvSnapshot.F0
    is_glacial: bool                 # → ice_albedo (미래 연결)
    insolation_by_band: dict         # {phi_deg: W/m²}

    def summary(self) -> str:
        glac = "빙하기" if self.is_glacial else "간빙기"
        return (
            f"t={self.t_yr/1000:.1f}kyr [{glac}] | "
            f"obliq={self.milank_state.obliquity_deg:.2f}° "
            f"(scale={self.obliquity_scale:.3f}) | "
            f"e={self.milank_state.eccentricity:.4f} | "
            f"F0={self.F0_corrected:.1f}W/m²"
        )


class MilankovitchDriver:
    """Milankovitch 주기를 GaiaLoopConnector에 매 스텝 주입하는 드라이버.

    사용법::

        cycle   = make_earth_cycle()
        driver  = MilankovitchDriver(cycle)
        connector = make_connector(...)

        for yr in range(200_000):
            output = driver.step(t_yr=float(yr - 100_000))

            # Loop C 갱신 (obliquity → 계절성 진폭)
            env = connector.make_fire_env(
                base_env,
                obliquity_deg=output.milank_state.obliquity_deg,
            )

            # F0 보정 (이심률 → 태양 복사 강도)
            env.F0 = output.F0_corrected

            # 빙하기 트리거 (미래: ice_albedo.py)
            if output.is_glacial:
                connector.apply_glacial_mode()

    설계 원칙:
        - MilankovitchCycle은 pure function (상태 없음)
        - Driver만 상태 보유 (현재 t_yr, 이전 상태 비교)
        - GaiaLoopConnector에 의존하지 않음 (output을 연결기가 사용)
    """

    def __init__(
        self,
        cycle: Optional[MilankovitchCycle] = None,
        glacial_threshold_Wm2: float = 450.0,
        glacial_phi_deg: float = 65.0,
    ):
        """
        Args:
            cycle: MilankovitchCycle. None → 지구 기본값
            glacial_threshold_Wm2: 빙하기 판단 임계 일사량 [W/m²]
            glacial_phi_deg: 빙하기 판단 기준 위도 [deg]
        """
        self.cycle  = cycle or make_earth_cycle()
        self._glac_th  = glacial_threshold_Wm2
        self._glac_phi = glacial_phi_deg
        self._last: Optional[DriverOutput] = None

    def step(self, t_yr: float) -> DriverOutput:
        """특정 시점의 드라이버 출력 계산.

        Args:
            t_yr: 현재 시뮬레이션 시간 [yr]

        Returns:
            DriverOutput
        """
        state      = self.cycle.state(t_yr)
        o_scale    = state.obliquity_scale
        is_glacial = self.cycle.is_glacial(t_yr, self._glac_th, self._glac_phi)

        # 이심률 보정 태양상수 (연평균 일사량 기준)
        # F0_eff = F0 × (1-e²)^(-1/2)  (타원 궤도 평균)
        e = state.eccentricity
        F0_corrected = self.cycle.F0 / math.sqrt(max(1.0 - e * e, EPS))

        insol_grid = insolation_grid(self.cycle, t_yr)

        output = DriverOutput(
            t_yr             = t_yr,
            milank_state     = state,
            obliquity_scale  = o_scale,
            F0_corrected     = F0_corrected,
            is_glacial       = is_glacial,
            insolation_by_band = insol_grid,
        )
        self._last = output
        return output

    def last(self) -> Optional[DriverOutput]:
        """마지막으로 계산된 출력 반환."""
        return self._last


# ── 간편 함수 ─────────────────────────────────────────────────────────────────

def make_earth_driver(
    glacial_threshold: float = 450.0,
    glacial_phi: float = 65.0,
) -> MilankovitchDriver:
    """지구 기본 Milankovitch 드라이버."""
    return MilankovitchDriver(
        cycle=make_earth_cycle(),
        glacial_threshold_Wm2=glacial_threshold,
        glacial_phi_deg=glacial_phi,
    )


__all__ = [
    "insolation_at",
    "insolation_grid",
    "MilankovitchDriver",
    "DriverOutput",
    "make_earth_driver",
]
