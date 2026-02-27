"""gravity_tides/tidal_mixing.py — 조석 혼합 모델 (넷째날 순환 3-A)

설계 철학:
    달-태양 조석력이 해양을 혼합하고, 깊은 영양염을 표층으로 올린다.
    표층 영양염↑ → 식물플랑크톤↑ → 탄소 격리↑ → CO₂↓ → T↓

수식 (DAY4_DESIGN.md):
    F_tidal(t) = F_moon(t) + F_sun(t)
    mixing_depth = K_mix × F_tidal       [m]
    nutrient_upwelling = K_up × mixing_depth × (C_deep - C_surface)

달 조석력 (단순화):
    F_moon(t) = F_moon_0 × (r_earth/r_moon(t))³
    r_moon(t) = a_moon × (1 - e_moon²) / (1 + e_moon×cos(anomaly))

태양 조석력:
    F_sun(t) = F_sun_0 × (AU/r_sun(t))³ (태양-지구 거리 보정)
    현재 비율: F_moon : F_sun ≈ 2.2 : 1

항상성:
    강한 조석 → 혼합↑ → CO₂ 흡수↑ → T↓ (음의 피드백)
    약한 조석 → 성층화 → 생산성↓ → CO₂↑ → T↑ (양의 피드백)

v1.0 (넷째날 순환 3-A):
    TidalField: 달+태양 조석력 계산
    OceanMixing: 혼합 깊이 + 영양염 upwelling
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# ── 물리 상수 ─────────────────────────────────────────────────────────────────

# 달 조석력 (현재 지구 기준)
F_MOON_REF      = 1.0       # 기준 달 조석력 [정규화, 현재=1.0]
A_MOON_M        = 3.844e8   # 달 반장축 [m]
E_MOON          = 0.0549    # 달 궤도 이심률
T_MOON_YR       = 27.32 / 365.25  # 달 공전 주기 [yr]

# 태양 조석력 (달 대비)
F_SUN_TO_MOON   = 0.46      # 태양 조석력 / 달 조석력 (현재)
T_YEAR          = 1.0       # 지구 공전 주기 [yr]
E_EARTH         = 0.0167    # 지구 이심률

# 혼합 깊이 변환 상수
K_MIX           = 200.0     # [m / (정규화 조석력)] 혼합 깊이 환산
# 현재 지구: 조석혼합층 ~50~200m
MIXING_DEPTH_MIN = 5.0      # [m] 최소 혼합 깊이 (성층화 극한)
MIXING_DEPTH_MAX = 500.0    # [m] 최대 혼합 깊이

# 영양염 upwelling
# 단위: K_UPWELLING_UM [μmol N/L/yr per meter mixing depth per μmol N/L gradient]
# 물리: Kz(확산계수) / MLD² ~ 수직 확산  →  K ≈ 1e-4 m²/s / (100m)² ≈ 1e-8 s⁻¹ ≈ 0.3 yr⁻¹/m
# 단순화: 1m 혼합 × 1 μmol/L 구배 → 0.01 μmol/L/yr 공급 (튜닝값)
K_UPWELLING_UM  = 0.01      # [μmol N/L/yr per m per μmol N/L]
C_DEEP_REF      = 30.0      # [μmol/L] 심층수 질산염 (현재 지구 심층 평균 ~30~40 μmol/L)
C_SURFACE_MIN   = 0.05      # [μmol/L] 표층 최솟값 (영양염 고갈 극한)

# 하위 호환: 구 버전 K_UPWELLING 이름 유지
K_UPWELLING = K_UPWELLING_UM

EPS = 1e-30


# ── 스냅샷 ────────────────────────────────────────────────────────────────────

@dataclass
class TidalState:
    """조석 상태 스냅샷.

    Attributes:
        time_yr:       현재 시간 [yr]
        F_moon:        달 조석력 [정규화, 현재=1.0]
        F_sun:         태양 조석력 [정규화]
        F_total:       총 조석력 [정규화]
        mixing_depth:  혼합 깊이 [m]
        upwelling_uM:  영양염 upwelling [μmol N/L/yr] (단위 정합됨)
        nutrient_flux: upwelling_uM alias (하위 호환)
        spring_neap:   사리(1.0)~조금(0.0) 위상 [0~1]
    """
    time_yr: float
    F_moon: float
    F_sun: float
    F_total: float
    mixing_depth: float
    upwelling_uM: float     # 단위 정합된 primary 필드
    spring_neap: float

    @property
    def nutrient_flux(self) -> float:
        """하위 호환 alias → upwelling_uM."""
        return self.upwelling_uM

    def summary(self) -> str:
        return (
            f"t={self.time_yr:.2f}yr | "
            f"F={self.F_total:.3f} (moon={self.F_moon:.3f}+sun={self.F_sun:.3f}) | "
            f"mix={self.mixing_depth:.1f}m | "
            f"upwelling={self.upwelling_uM:.4f} μmol/L/yr | "
            f"spring/neap={self.spring_neap:.2f}"
        )


# ── TidalField ────────────────────────────────────────────────────────────────

class TidalField:
    """달+태양 조석력 계산기.

    사용법::

        tf = TidalField()
        state = tf.compute(t_yr=0.5)    # 반년 시점

        print(state.F_total)    # 총 조석력 [정규화]
        print(state.mixing_depth)  # 혼합 깊이 [m]
    """

    def __init__(
        self,
        F_moon_ref: float = F_MOON_REF,
        F_sun_ratio: float = F_SUN_TO_MOON,
        K_mix: float = K_MIX,
        C_deep: float = C_DEEP_REF,
        C_surface_init: float = 5.0,
    ):
        self.F_moon_ref  = F_moon_ref
        self.F_sun_ratio = F_sun_ratio
        self.K_mix       = K_mix
        self.C_deep      = C_deep
        self.C_surface   = C_surface_init  # [μmol/L] 갱신되는 표층 영양염

    # ── 달 조석력 ─────────────────────────────────────────────────────────────

    def moon_tidal(self, t_yr: float) -> float:
        """달 조석력 [정규화].

        달 궤도 이심률로 인한 근지점/원지점 변동.
        F_moon ∝ (1/r_moon)³

        r_moon(t) = a × (1-e²) / (1 + e×cos(2πt/T_moon))
        → (a/r)³ = ((1 + e×cos(θ))/(1-e²))³
        """
        theta = 2.0 * math.pi * t_yr / T_MOON_YR
        one_minus_e2 = 1.0 - E_MOON * E_MOON
        r_factor = (1.0 + E_MOON * math.cos(theta)) / (one_minus_e2 + EPS)
        return self.F_moon_ref * (r_factor ** 3)

    def sun_tidal(self, t_yr: float, eccentricity: float = E_EARTH) -> float:
        """태양 조석력 [정규화].

        F_sun ∝ (1/r_sun)³  (지구 이심률 보정)
        """
        theta = 2.0 * math.pi * t_yr / T_YEAR
        one_minus_e2 = 1.0 - eccentricity * eccentricity
        r_factor = (1.0 + eccentricity * math.cos(theta)) / (one_minus_e2 + EPS)
        return self.F_moon_ref * self.F_sun_ratio * (r_factor ** 3)

    # ── 사리-조금 위상 ────────────────────────────────────────────────────────

    @staticmethod
    def spring_neap_phase(t_yr: float) -> float:
        """사리(봄조)-조금(소조) 위상 [0~1].

        달 시노딕 주기(29.53일) 기준.
        사리: 달-지구-태양 일직선 (삭/망) → F↑
        조금: 직각 → F↓

        Returns 0.0(조금) ~ 1.0(사리)
        """
        T_synodic = 29.53 / 365.25  # [yr]
        phase = (t_yr % T_synodic) / T_synodic
        # 월 2회 사리: 0/π에서 최대
        return 0.5 * (1.0 + math.cos(2.0 * 2.0 * math.pi * phase))

    # ── 혼합 깊이 ─────────────────────────────────────────────────────────────

    def mixing_depth_m(self, F_total: float) -> float:
        """혼합 깊이 [m].

        mixing_depth = K_mix × F_total × spring_neap_factor
        """
        depth = self.K_mix * F_total
        return max(MIXING_DEPTH_MIN, min(MIXING_DEPTH_MAX, depth))

    # ── 영양염 upwelling ──────────────────────────────────────────────────────

    def nutrient_upwelling_uM(self, mixing_depth: float) -> float:
        """영양염 upwelling 플럭스 [μmol N/L/yr].

        flux = K_UPWELLING_UM × mixing_depth [m] × (C_deep - C_surface) [μmol/L]

        단위:
            [μmol/L/yr per m per μmol/L] × [m] × [μmol/L] = [μmol/L/yr]

        Args:
            mixing_depth: 혼합 깊이 [m] (TidalField.mixing_depth_m() 출력)

        Returns:
            upwelling_uM [μmol N/L/yr]
        """
        gradient = max(0.0, self.C_deep - max(C_SURFACE_MIN, self.C_surface))
        flux = K_UPWELLING_UM * mixing_depth * gradient
        return max(0.0, flux)

    def nutrient_upwelling(self, mixing_depth: float) -> float:
        """하위 호환용 alias → nutrient_upwelling_uM()."""
        return self.nutrient_upwelling_uM(mixing_depth)

    # ── 통합 계산 ─────────────────────────────────────────────────────────────

    def compute(
        self,
        t_yr: float,
        eccentricity: float = E_EARTH,
    ) -> TidalState:
        """조석 상태 계산.

        Args:
            t_yr:          시간 [yr]
            eccentricity:  지구 이심률 (Milankovitch에서 주입 가능)

        Returns:
            TidalState
        """
        F_m  = self.moon_tidal(t_yr)
        F_s  = self.sun_tidal(t_yr, eccentricity)
        sn   = self.spring_neap_phase(t_yr)

        # 사리-조금 변조
        F_tot = (F_m + F_s) * (0.7 + 0.3 * sn)

        mix          = self.mixing_depth_m(F_tot)
        upwelling_uM = self.nutrient_upwelling_uM(mix)

        return TidalState(
            time_yr      = t_yr,
            F_moon       = F_m,
            F_sun        = F_s,
            F_total      = F_tot,
            mixing_depth = mix,
            upwelling_uM = upwelling_uM,
            spring_neap  = sn,
        )


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_tidal_field(
    F_moon_ref: float = F_MOON_REF,
    C_surface_init: float = 5.0,
) -> TidalField:
    """기본 현재 지구 조석 필드."""
    return TidalField(F_moon_ref=F_moon_ref, C_surface_init=C_surface_init)


__all__ = [
    "TidalField",
    "TidalState",
    "make_tidal_field",
    "F_MOON_REF",
    "K_MIX",
    "K_UPWELLING",
]
