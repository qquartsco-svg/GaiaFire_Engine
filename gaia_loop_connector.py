"""gaia_loop_connector.py — 3개 열린 루프를 닫는 항상성 연결기 (Phase 8.5)

목적:
    "초기 조건만 주면 스스로 순환하는" 환경 구현을 위해
    개별적으로 존재했던 모듈들을 닫힌 피드백 루프로 연결한다.

닫히는 루프 3개:
─────────────────────────────────────────────────────────────────────
[Loop A] 산불 CO₂ → 대기 CO₂ (fire_engine → atmosphere)
    fire_co2_source_kgC [kg C/m²/yr]
    → ΔCO₂ [mol/mol/yr]
    → atmosphere.composition.CO₂ 갱신
    → 다음 스텝 온실효과 강화 → T↑ → 건조↑ → 산불 ↑ (양의 피드백)
    → GPP 증가 → O₂ 방출 → CO₂ 흡수 (음의 피드백, attractor)

[Loop B] 식생 알베도 → 온도 (biosphere → atmosphere)
    delta_albedo_land (biosphere.column 출력)
    → atmosphere.albedo 갱신
    → 다음 스텝 T 변화 → GPP 변화 → 식생 변화 (음의 피드백 attractor)

[Loop C] 세차 obliquity → 계절성 (core → fire_risk)
    obliquity_deg(t) (evolution_engine 또는 FireEnvSnapshot)
    → dry_season_amplitude 동적 조정
    → fire_risk.dry_season_modifier 의 진폭 변경
    → 건기 강도 변화 → fire_risk 변화
─────────────────────────────────────────────────────────────────────

사용법:
    connector = GaiaLoopConnector(atmosphere, land_fraction=0.29)

    # 매 yr 스텝마다:
    # 1) biosphere.step() 결과 → Loop B 적용
    connector.apply_albedo_loop(bio_result)

    # 2) fire_engine.predict() 결과 → Loop A 적용
    connector.apply_fire_co2_loop(fire_results, dt_yr=1.0)

    # 3) FireEnvSnapshot 생성 시 → Loop C 반영
    env = connector.make_fire_env(base_env, obliquity_deg, time_yr)

수학:
    Loop A: ΔCO₂ = fire_co2_total_kgC × (12/44) / (M_ATM_CO2_REF)
              = fire_co2_kgC [kg/m²/yr] × LAND_AREA_M2 / (M_ATM_kg_CO2)
              더 단순하게: Δ(CO2_mol_frac) = fire_co2_kgC × K_C_TO_PPM × 1e-6

    Loop B: albedo_eff = albedo_base × (1 - land_frac)
                       + (albedo_base + delta_albedo_land) × land_frac
            → albedo_eff를 atmosphere.albedo에 반영

    Loop C: amplitude(φ) = amplitude_base(φ) × obliquity_scale(obliquity_deg)
            obliquity_scale = 1.0 + K_OBLIQ × (obliquity_deg - OBLIQUITY_REF) / OBLIQUITY_REF

v1.0 (Phase 8.5):
    GaiaLoopConnector — 3루프 연결기
    LoopState — 매 스텝 루프 상태 스냅샷
    make_fire_env_with_obliquity — Loop C 반영 FireEnvSnapshot 생성
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, TYPE_CHECKING

# 독립 레포 — 동일 폴더에서 직접 import
try:
    from .atmosphere import AtmosphereColumn
    from .fire import FireEnvSnapshot, FireEngine
    from .fire.fire_engine import FireBandResult, BAND_WEIGHTS
except ImportError:
    # 독립 실행용 fallback (atmosphere 없는 경우 더미 사용)
    try:
        from fire_engine import FireEnvSnapshot, FireEngine, FireBandResult, BAND_WEIGHTS
    except ImportError:
        raise ImportError("fire_engine.py가 필요합니다.")

    # AtmosphereColumn 더미 (독립 레포에서 atmosphere 미설치 시)
    try:
        from atmosphere.column import AtmosphereColumn
    except ImportError:
        class _AtmComposition:
            def __init__(self): self.CO2 = 400e-6; self.O2 = 0.21; self.H2O = 0.01; self.CH4 = 1.8e-6
        class AtmosphereColumn:
            """독립 실행용 경량 대기 더미."""
            def __init__(self, T_surface_init=288.0, albedo=0.306, composition=None, **kw):
                self.T_surface = T_surface_init or 288.0
                self.albedo    = albedo
                self.composition = composition or _AtmComposition()
                self.time_yr   = 0.0
            def step(self, F_solar_si, dt_yr, **kw):
                self.time_yr += dt_yr

# ── 물리 상수 ─────────────────────────────────────────────────────────────────

# [Loop A] 산불 CO₂ → 대기 CO₂
# 지구 대기 총 탄소량: CO₂ 400ppm × 대기 질량 5.15e18 kg / (44 g/mol) × 12 g/mol
ATMO_MASS_KG       = 5.15e18     # [kg] 지구 대기 총 질량
CO2_MOL_MASS       = 0.044       # [kg/mol] CO₂ 분자량
C_MOL_MASS         = 0.012       # [kg/mol] 탄소 분자량
AIR_MOL_MASS       = 0.029       # [kg/mol] 공기 평균 분자량
LAND_AREA_M2       = 1.48e14     # [m²] 지구 육지 면적

# 탄소 1 kg → 대기 CO₂ mol/mol 변화량
# ΔCO₂ [mol/mol] = ΔC [kg] × (1/C_MOL_MASS) / (ATMO_MASS_KG / AIR_MOL_MASS)
# = ΔC [kg] × AIR_MOL_MASS / (C_MOL_MASS × ATMO_MASS_KG)
K_KGC_TO_CO2_FRAC  = AIR_MOL_MASS / (C_MOL_MASS * ATMO_MASS_KG)
# ≈ 0.029 / (0.012 × 5.15e18) ≈ 4.7e-22 [mol/mol per kg C]
# 실제로 전지구 CO₂ 1ppm = 2.13 GtC = 2.13e12 kg C
# → K = 1e-6 / 2.13e12 = 4.7e-19 [mol/mol / kg C]  ← 이 값 사용
K_KGC_TO_CO2_FRAC  = 1e-6 / 2.13e12  # [mol/mol per kg C]

# CO₂ 클램프 [mol/mol]
CO2_MIN = 150e-6     # 150 ppm (생존 하한)
CO2_MAX = 50_000e-6  # 50000 ppm (극한 상한)

# [Loop B] 식생 알베도
# land_fraction: 육지가 전체에서 차지하는 비율 (지구 ≈ 0.29)
# albedo_ocean: 바다 알베도 (지구 ≈ 0.06, 거의 안 변함)
ALBEDO_OCEAN_DEFAULT = 0.06

# [Loop C] 세차 obliquity → 계절성
OBLIQUITY_REF   = 23.5   # [deg] 현재 지구 황도경사
K_OBLIQ_SCALE   = 0.8    # obliquity 변화 → 계절성 진폭 감도
                          # 0.0 = 연결 없음, 1.0 = 1:1 선형
# obliquity 범위 (지구 Milankovitch: 22.1° ~ 24.5°, 4만년 주기)
OBLIQUITY_MIN   = 0.0    # 수학적 최솟값 (0° = 계절 없음)
OBLIQUITY_MAX   = 90.0   # 수학적 최댓값 (90° = 극한 계절)

EPS = 1e-30


# ── 루프 상태 스냅샷 ──────────────────────────────────────────────────────────

@dataclass
class LoopState:
    """매 스텝 3개 루프 연결 상태 스냅샷.

    Attributes:
        time_yr: 현재 시뮬레이션 시간 [yr]
        # Loop A
        fire_co2_total_kgC: 전지구 산불 CO₂ 방출 [kg C/yr]
        delta_CO2_frac: 대기 CO₂ 변화량 [mol/mol]
        CO2_new: 갱신 후 CO₂ [mol/mol]
        # Loop B
        delta_albedo_land: 식생 알베도 변화 [dimensionless]
        albedo_new: 갱신 후 전지구 유효 알베도
        # Loop C
        obliquity_deg: 현재 황도경사 [deg]
        obliquity_scale: 계절성 진폭 배율
    """
    time_yr: float
    # Loop A
    fire_co2_total_kgC: float = 0.0
    delta_CO2_frac: float = 0.0
    CO2_new: float = 400e-6
    # Loop B
    delta_albedo_land: float = 0.0
    albedo_new: float = 0.306
    # Loop C
    obliquity_deg: float = 23.5
    obliquity_scale: float = 1.0

    def summary(self) -> str:
        return (
            f"t={self.time_yr:.2f}yr | "
            f"ΔCO₂={self.delta_CO2_frac*1e6:+.3f}ppm "
            f"CO₂={self.CO2_new*1e6:.1f}ppm | "
            f"Δalbedo={self.delta_albedo_land:+.4f} "
            f"albedo={self.albedo_new:.4f} | "
            f"obliq={self.obliquity_deg:.1f}° "
            f"dry_scale={self.obliquity_scale:.3f}"
        )


# ── GaiaLoopConnector ────────────────────────────────────────────────────────

class GaiaLoopConnector:
    """3개 열린 피드백 루프를 닫아 항상성 순환을 완성하는 연결기.

    Loop A: 산불 CO₂ → 대기 CO₂ → 온실 효과 → 온도 → 건조 → 산불
    Loop B: 식생 알베도 → 대기 온도 → GPP → 식생 → 알베도
    Loop C: 세차 obliquity → 건기 진폭 → 산불 위험도 → 탄소 플럭스
    """

    def __init__(
        self,
        atmosphere: AtmosphereColumn,
        land_fraction: float = 0.29,
        albedo_ocean: float = ALBEDO_OCEAN_DEFAULT,
        loop_a_enabled: bool = True,
        loop_b_enabled: bool = True,
        loop_c_enabled: bool = True,
    ):
        """
        Args:
            atmosphere: AtmosphereColumn 인스턴스 (직접 수정)
            land_fraction: 육지 비율 [0,1] (지구 ≈ 0.29)
            albedo_ocean: 바다 알베도 (거의 안 변함, ≈ 0.06)
            loop_a/b/c_enabled: 개별 루프 활성화 여부
        """
        self.atm = atmosphere
        self.land_frac = land_fraction
        self.albedo_ocean = albedo_ocean
        self.loop_a = loop_a_enabled
        self.loop_b = loop_b_enabled
        self.loop_c = loop_c_enabled

        # 기준 알베도 기억 (Loop B: 육지 알베도 변화만 적용)
        self._albedo_land_base = (
            atmosphere.albedo - albedo_ocean * (1.0 - land_fraction)
        ) / max(land_fraction, EPS)
        self._albedo_land_current = self._albedo_land_base

        # Loop C 현재 obliquity scale
        self._obliquity_scale: float = 1.0

        # 히스토리
        self._loop_history: List[LoopState] = []

    # ── Loop A: 산불 CO₂ → 대기 CO₂ ─────────────────────────────────────────

    def apply_fire_co2_loop(
        self,
        fire_results: List[FireBandResult],
        dt_yr: float = 1.0,
        fire_engine: Optional[FireEngine] = None,
    ) -> float:
        """산불 CO₂ 방출을 대기 CO₂ 농도에 반영한다.

        Args:
            fire_results: FireEngine.predict() 반환값
            dt_yr: 시간 스텝 [yr]
            fire_engine: 있으면 global_o2_flux도 계산 (선택)

        Returns:
            delta_CO2_frac: 이번 스텝 CO₂ 변화량 [mol/mol]
        """
        if not self.loop_a:
            return 0.0

        # 전지구 가중 CO₂ 방출 [kg C/m²/yr]
        co2_flux_kgC_m2_yr = sum(
            r.fire_co2_source_kgC * BAND_WEIGHTS[i]
            for i, r in enumerate(fire_results)
        )

        # 전지구 총량 [kg C/yr]
        co2_total_kgC_yr = co2_flux_kgC_m2_yr * LAND_AREA_M2

        # 대기 CO₂ 분율 변화량 [mol/mol]
        delta_CO2 = co2_total_kgC_yr * dt_yr * K_KGC_TO_CO2_FRAC

        # 대기 CO₂ 갱신
        old_CO2 = self.atm.composition.CO2
        new_CO2 = max(CO2_MIN, min(CO2_MAX, old_CO2 + delta_CO2))
        self.atm.composition.CO2 = new_CO2

        return delta_CO2

    # ── Loop B: 식생 알베도 → 대기 온도 ─────────────────────────────────────

    def apply_albedo_loop(
        self,
        bio_result: Dict[str, Any],
        smooth_factor: float = 0.1,
    ) -> float:
        """biosphere.step() 결과의 delta_albedo_land를 대기 알베도에 반영한다.

        EMA(지수이동평균)으로 부드럽게 반영 — 급격한 점프 방지.

        Args:
            bio_result: BiosphereColumn.step() 반환 dict
            smooth_factor: EMA 가중치 [0,1]. 작을수록 느린 응답.

        Returns:
            albedo_new: 갱신 후 전지구 유효 알베도
        """
        if not self.loop_b:
            return self.atm.albedo

        delta_alb = bio_result.get("delta_albedo_land", 0.0)

        # 육지 알베도 EMA 갱신
        land_alb_target = self._albedo_land_base + delta_alb
        self._albedo_land_current = (
            (1.0 - smooth_factor) * self._albedo_land_current
            + smooth_factor * land_alb_target
        )

        # 전지구 유효 알베도 = 육지 × 육지비율 + 바다 × 바다비율
        albedo_eff = (
            self._albedo_land_current * self.land_frac
            + self.albedo_ocean * (1.0 - self.land_frac)
        )
        # 클램프
        albedo_eff = max(0.01, min(0.99, albedo_eff))
        self.atm.albedo = albedo_eff

        return albedo_eff

    # ── Loop C: 세차 obliquity → 계절성 진폭 ────────────────────────────────

    def obliquity_scale(self, obliquity_deg: float) -> float:
        """세차 obliquity → 계절성 진폭 배율 계산.

        Args:
            obliquity_deg: 현재 황도경사각 [deg]

        Returns:
            scale: 건기 진폭 배율 [0.5, 2.0] 클램프
        """
        if not self.loop_c:
            return 1.0

        ratio = (obliquity_deg - OBLIQUITY_REF) / max(OBLIQUITY_REF, EPS)
        scale = 1.0 + K_OBLIQ_SCALE * ratio
        self._obliquity_scale = max(0.5, min(2.0, scale))
        return self._obliquity_scale

    def make_fire_env(
        self,
        base_env: FireEnvSnapshot,
        obliquity_deg: float,
        veg_feedback: bool = True,
    ) -> FireEnvSnapshot:
        """Loop C를 반영한 FireEnvSnapshot 생성.

        Loop C: obliquity → 계절성 진폭 배율이 fire_risk 계산에 적용될 수 있도록
        FireEnvSnapshot에 obliquity_deg를 갱신한다.
        (fire_risk.py의 dry_season_modifier는 obliquity를 직접 받지 않으므로,
        외부 wrapper인 obliquity_dry_modifier()를 통해 스케일을 조정한다.)

        Args:
            base_env: 기본 FireEnvSnapshot
            obliquity_deg: 현재 황도경사각 [deg]
            veg_feedback: True면 Loop B의 알베도 변화도 반영

        Returns:
            obliquity가 갱신된 FireEnvSnapshot
        """
        scale = self.obliquity_scale(obliquity_deg)

        return FireEnvSnapshot(
            O2_frac       = base_env.O2_frac,
            CO2_ppm       = self.atm.composition.CO2 * 1e6,  # Loop A 반영
            obliquity_deg = obliquity_deg,
            F0            = base_env.F0,
            time_yr       = base_env.time_yr,
            band_ecosystems = base_env.band_ecosystems,
        )

    # ── 통합 스텝 ─────────────────────────────────────────────────────────────

    def step(
        self,
        fire_results: List[FireBandResult],
        bio_result: Dict[str, Any],
        obliquity_deg: float,
        dt_yr: float = 1.0,
        time_yr: float = 0.0,
        fire_engine: Optional[FireEngine] = None,
    ) -> LoopState:
        """3개 루프를 한 번에 적용하는 통합 스텝.

        Args:
            fire_results: FireEngine.predict() 결과
            bio_result: BiosphereColumn.step() 결과 dict
            obliquity_deg: 현재 황도경사 [deg]
            dt_yr: 스텝 크기 [yr]
            time_yr: 현재 시뮬레이션 시간 [yr]
            fire_engine: Loop A에서 선택적으로 사용

        Returns:
            LoopState: 이번 스텝 루프 상태 스냅샷
        """
        # Loop A
        dCO2 = self.apply_fire_co2_loop(fire_results, dt_yr, fire_engine)

        # Loop B
        alb_new = self.apply_albedo_loop(bio_result)

        # Loop C
        scale = self.obliquity_scale(obliquity_deg)

        state = LoopState(
            time_yr             = time_yr,
            fire_co2_total_kgC  = sum(
                r.fire_co2_source_kgC * BAND_WEIGHTS[i]
                for i, r in enumerate(fire_results)
            ) * LAND_AREA_M2,
            delta_CO2_frac      = dCO2,
            CO2_new             = self.atm.composition.CO2,
            delta_albedo_land   = bio_result.get("delta_albedo_land", 0.0),
            albedo_new          = alb_new,
            obliquity_deg       = obliquity_deg,
            obliquity_scale     = scale,
        )
        self._loop_history.append(state)
        return state

    # ── 계절성 진폭 오버라이드 도우미 ────────────────────────────────────────

    def obliquity_dry_modifier(
        self,
        phi_deg: float,
        time_yr: float,
        base_amplitude: float,
    ) -> float:
        """Loop C 반영: 세차 obliquity 스케일이 적용된 건기 계절성 수분 계수.

        fire_risk.py의 dry_season_modifier()를 대체하거나 보완하여
        obliquity에 따라 진폭이 달라지는 계절성을 구현.

        Args:
            phi_deg: 위도 [deg]
            time_yr: 현재 시간 [yr] (0~1 = 1년 주기)
            base_amplitude: 기본 건기 진폭 (위도별 고정값)

        Returns:
            W_modifier [0,1]: 낮을수록 건조 (= fire_risk 올라감)
        """
        amplitude = base_amplitude * self._obliquity_scale

        if phi_deg >= 0:
            phase = 0.25   # 북반구: 여름(t=0.5) 건기
        else:
            phase = 0.75   # 남반구: 반대

        dry_factor = amplitude * math.sin(2.0 * math.pi * (time_yr - phase))
        return max(0.0, min(1.0, 1.0 - dry_factor))

    # ── 상태 조회 ─────────────────────────────────────────────────────────────

    def history(self) -> List[LoopState]:
        return list(self._loop_history)

    def summary(self) -> Dict[str, Any]:
        """현재 대기 + 루프 상태 요약."""
        return {
            "CO2_ppm":          self.atm.composition.CO2 * 1e6,
            "O2_frac":          self.atm.composition.O2,
            "albedo":           self.atm.albedo,
            "T_surface_K":      self.atm.T_surface,
            "obliquity_scale":  self._obliquity_scale,
            "albedo_land":      self._albedo_land_current,
            "loop_a":           self.loop_a,
            "loop_b":           self.loop_b,
            "loop_c":           self.loop_c,
        }


# ── 간편 팩토리 ──────────────────────────────────────────────────────────────

def make_connector(
    T_init: float = 288.0,
    CO2_ppm: float = 400.0,
    O2_frac: float = 0.21,
    albedo: float = 0.306,
    land_fraction: float = 0.29,
    use_water_cycle: bool = True,
) -> tuple:
    """AtmosphereColumn + GaiaLoopConnector 기본 세트 생성.

    Returns:
        (atmosphere, connector) tuple
    """
    # AtmosphereComposition import (독립/패키지 양방향 지원)
    try:
        from .atmosphere import AtmosphereComposition
    except ImportError:
        try:
            from atmosphere.column import AtmosphereComposition
        except ImportError:
            AtmosphereComposition = None

    if AtmosphereComposition is not None:
        comp = AtmosphereComposition(O2=O2_frac, CO2=CO2_ppm * 1e-6)
    else:
        comp = None   # 더미 AtmosphereColumn이 내부 생성

    atm = AtmosphereColumn(
        T_surface_init=T_init,
        albedo=albedo,
        composition=comp,
        use_water_cycle=use_water_cycle,
    )
    connector = GaiaLoopConnector(
        atmosphere=atm,
        land_fraction=land_fraction,
    )
    return atm, connector


__all__ = [
    "GaiaLoopConnector",
    "GaiaLoopConnectorConfig",
    "LoopState",
    "make_connector",
]
