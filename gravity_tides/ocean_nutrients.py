"""gravity_tides/ocean_nutrients.py — 해양 영양염 + 탄소 펌프 (넷째날 순환 3-B)

설계 철학:
    영양염 upwelling → 식물플랑크톤 성장 → 생물학적 탄소 펌프
    → 심층 탄소 격리 → 대기 CO₂↓ → T↓ (음의 피드백)

수식:
    dC_surface/dt = F_upwelling - K_uptake_N × phyto_growth / NUTRIENT_TO_C - K_mix_loss × C_surface
    dphyto/dt     = K_phyto × f(C_surface) × light × (1 - phyto/PHYTO_MAX) - (K_grazing + K_mortality) × phyto
    carbon_export = K_export × phyto
    CO2_sink_ppm  = carbon_export × C_TO_CO2 × OCEAN_AREA_M2 / GT_TO_G × CO2_PPM_PER_GT_CO2

단위 정합 (v1.1 수정):
    C_surface: [μmol N/L]
    F_upwelling: [μmol N/L/yr] — TidalField.nutrient_upwelling_uM() 출력
    phyto: [g C/m²]
    carbon_export: [g C/m²/yr]
    CO2_sink_ppm: [ppm/yr] (전지구 해양 면적 환산)

v1.1 (버그 수정):
    - C_surface ODE 추가 (step()에서 실제로 갱신됨)
    - nutrient → phyto 성장 연결: Michaelis-Menten f(C_surface) 추가
    - 단위 정합: upwelling flux를 [μmol/L/yr]로 통일
    - NUTRIENT_TO_C (레드필드) 사용하여 영양염 uptake 계산
    - TidalField.C_surface 공유: tf.C_surface = ocean.C_surface 패턴 (별도 함수 없음)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ── 상수 ──────────────────────────────────────────────────────────────────────

# 식물플랑크톤 [g C/m²]
K_PHYTO_GROWTH    = 2.0     # [yr⁻¹] 최대 성장속도 (영양염/빛 포화 시)
K_GRAZING         = 0.15    # [yr⁻¹] 동물플랑크톤 섭식률
K_MORTALITY       = 0.05    # [yr⁻¹] 자연 사멸률
PHYTO_MAX         = 50.0    # [g C/m²] 최대 식물플랑크톤 탄소량
PHYTO_MIN         = 0.01    # [g C/m²] 최솟값

# 영양염 [μmol N/L]
C_SURFACE_INIT    = 5.0     # [μmol/L] 초기 표층 영양염 (질산염)
C_SURFACE_MIN     = 0.05    # [μmol/L] 물리적 최솟값
C_SURFACE_MAX     = 50.0    # [μmol/L] 포화 상한
K_N_HALF          = 2.0     # [μmol/L] Michaelis-Menten 반포화 상수 (질산염)
K_MIX_LOSS        = 0.05    # [yr⁻¹] 표층 영양염 혼합 손실률 (심층으로 재순환)

# 빛 제한
LIGHT_FACTOR_REF  = 0.7     # [0~1] 현재 지구 평균

# 탄소 수출 (생물 펌프)
K_EXPORT          = 0.15    # [yr⁻¹] 탄소 침강 수출 효율
C_TO_CO2          = 3.67    # [g CO₂/g C] 분자량 비 (44/12)
OCEAN_AREA_M2     = 3.6e14  # [m²] 전지구 해양 면적

# 레드필드 비율: C:N = 106:16 = 6.625  →  1 gC 생산 = 1/6.625 × (14/12) g N 소비
# 단위 변환: g N/m² ↔ μmol N/L (혼합층 깊이 MLD 경유)
NUTRIENT_TO_C     = 6.625   # [g C / g N] 레드필드
MLD_REF_M         = 100.0   # [m] 혼합층 기준 깊이 (단위 변환 기준)
# 1 μmol N/L × MLD [m] × 1000 L/m³ × 14e-6 kg/μmol = g N/m²
# → g N/m² → g C/m² via NUTRIENT_TO_C
UMOL_N_TO_GN_PER_M2 = 14e-3 * MLD_REF_M  # [g N/m² per μmol N/L] MLD=100m 기준

# CO₂ 단위 변환
# 대기 CO₂ 1ppm = 2.13 GtC = 7.81 Gt CO₂
CO2_PPM_PER_GT_CO2 = 1.0 / 7.81   # [ppm/Gt CO₂]
GT_TO_G            = 1e15          # [g/Gt]

EPS = 1e-30


# ── 스냅샷 ────────────────────────────────────────────────────────────────────

@dataclass
class OceanState:
    """해양 생태계 상태 스냅샷.

    Attributes:
        time_yr:        시간 [yr]
        C_surface:      표층 영양염 [μmol N/L]
        phyto_biomass:  식물플랑크톤 탄소량 [g C/m²]
        phyto_growth:   성장률 [g C/m²/yr]
        carbon_export:  탄소 수출 [g C/m²/yr]
        CO2_sink_ppm:   CO₂ 격리량 [ppm/yr] (전지구 환산)
        upwelling_uM:   upwelling 영양염 [μmol N/L/yr]
        f_nutrient:     영양염 제한 팩터 [0~1]
    """
    time_yr: float
    C_surface: float
    phyto_biomass: float
    phyto_growth: float
    carbon_export: float
    CO2_sink_ppm: float
    upwelling_uM: float
    f_nutrient: float

    def summary(self) -> str:
        return (
            f"t={self.time_yr:.1f}yr | "
            f"C_surf={self.C_surface:.2f}μM | "
            f"phyto={self.phyto_biomass:.3f}gC/m² | "
            f"export={self.carbon_export:.4f}gC/m²/yr | "
            f"CO2_sink={self.CO2_sink_ppm:.6f}ppm/yr | "
            f"f_N={self.f_nutrient:.3f}"
        )


# ── OceanNutrients ────────────────────────────────────────────────────────────

class OceanNutrients:
    """해양 영양염 동역학 + 생물학적 탄소 펌프.

    상태 변수:
        C_surface [μmol N/L]  — 표층 영양염 (ODE로 갱신)
        phyto     [g C/m²]    — 식물플랑크톤 탄소량 (ODE로 갱신)

    TidalField와 연결::

        tf = make_tidal_field()
        ocean = make_ocean_nutrients()

        for yr in range(100):
            ts = tf.compute(t_yr=yr)
            # upwelling [μmol/L/yr] = nutrient_upwelling_uM(mixing_depth, C_surface)
            upwelling_uM = ts.mixing_depth * K_UPWELLING_UM * (C_deep - C_surface)
            os = ocean.step(dt=1.0, upwelling_uM=upwelling_uM)
            tf.C_surface = os.C_surface   # 표층 영양염 공유 (루프 연결)

    닫힌 루프:
        강한 조석 → 혼합↑ → C_surface↑ → phyto↑ → export↑ → CO₂↓
        CO₂↓ → 광합성↓(phyto가 영양염 소진) → C_surface↑(재공급 대기)
        → 다음 upwelling 사이클 (음의 피드백 진동)
    """

    def __init__(
        self,
        C_surface_init: float = C_SURFACE_INIT,
        phyto_init: float = 1.0,
        K_phyto: float = K_PHYTO_GROWTH,
        K_grazing: float = K_GRAZING,
        K_mortality: float = K_MORTALITY,
        K_export: float = K_EXPORT,
        K_mix_loss: float = K_MIX_LOSS,
    ):
        self.C_surface   = max(C_SURFACE_MIN, C_surface_init)
        self.phyto       = max(PHYTO_MIN, phyto_init)
        self.K_phyto     = K_phyto
        self.K_grazing   = K_grazing
        self.K_mortality = K_mortality
        self.K_export    = K_export
        self.K_mix_loss  = K_mix_loss
        self._time_yr    = 0.0

    # ── 영양염 제한 팩터 ──────────────────────────────────────────────────────

    def f_nutrient(self) -> float:
        """영양염 제한 팩터 — Michaelis-Menten [0~1].

        f_N = C_surface / (C_surface + K_N_half)
        영양염이 높을수록 성장 포화에 가까워짐.
        """
        return self.C_surface / (self.C_surface + K_N_HALF + EPS)

    # ── phyto 동역학 ──────────────────────────────────────────────────────────

    def _phyto_growth_rate(self, light: float) -> float:
        """식물플랑크톤 성장률 [g C/m²/yr].

        growth = K_phyto × f_N(C_surface) × light × (1 - phyto/PHYTO_MAX)
        """
        f_N = self.f_nutrient()
        carrying = max(0.0, 1.0 - self.phyto / PHYTO_MAX)
        return self.K_phyto * f_N * light * carrying * self.phyto

    def _phyto_loss_rate(self) -> float:
        """식물플랑크톤 손실률 [g C/m²/yr]."""
        return (self.K_grazing + self.K_mortality) * self.phyto

    # ── C_surface 동역학 ──────────────────────────────────────────────────────

    def _dC_surface_dt(self, upwelling_uM: float, phyto_growth: float) -> float:
        """표층 영양염 변화율 [μmol N/L/yr].

        dC/dt = upwelling                   [upwelling 공급]
              - phyto_growth / NUTRIENT_TO_C / UMOL_N_TO_GN_PER_M2  [phyto 흡수]
              - K_mix_loss × C_surface       [혼합 손실/재순환]

        단위 변환:
            phyto_growth [g C/m²/yr]
            → g N/m²/yr  (÷ NUTRIENT_TO_C)
            → μmol N/L/yr (÷ UMOL_N_TO_GN_PER_M2)
        """
        uptake_uM = (phyto_growth / NUTRIENT_TO_C) / (UMOL_N_TO_GN_PER_M2 + EPS)
        mix_loss  = self.K_mix_loss * self.C_surface
        return upwelling_uM - uptake_uM - mix_loss

    # ── 탄소 펌프 ─────────────────────────────────────────────────────────────

    def _carbon_export_rate(self) -> float:
        """탄소 침강 수출 [g C/m²/yr]."""
        return self.K_export * self.phyto

    def _co2_sink_ppm_per_yr(self, carbon_export: float) -> float:
        """탄소 수출 → 대기 CO₂ 감소 [ppm/yr].

        CO₂_sink [Gt CO₂/yr] = carbon_export [g C/m²/yr]
                              × C_TO_CO2 [g CO₂/g C]
                              × OCEAN_AREA_M2 [m²]
                              / GT_TO_G [g/Gt]
        CO₂_sink [ppm/yr] = CO₂_sink [Gt/yr] × CO2_PPM_PER_GT_CO2
        """
        co2_gt = carbon_export * C_TO_CO2 * OCEAN_AREA_M2 / GT_TO_G
        return co2_gt * CO2_PPM_PER_GT_CO2

    # ── step ──────────────────────────────────────────────────────────────────

    def step(
        self,
        dt: float,
        upwelling_uM: float,
        light_factor: float = LIGHT_FACTOR_REF,
    ) -> OceanState:
        """해양 생태계 1 타임스텝 — 오일러 적분.

        Args:
            dt:           타임스텝 [yr]
            upwelling_uM: 영양염 upwelling [μmol N/L/yr]
                          (TidalField.nutrient_upwelling_uM() 출력)
            light_factor: 빛 제한 팩터 [0~1]

        Returns:
            OceanState (C_surface 갱신 포함)
        """
        f_N    = self.f_nutrient()

        # 1. phyto 동역학
        growth = self._phyto_growth_rate(light_factor)
        loss   = self._phyto_loss_rate()
        dphyto = growth - loss

        # 2. C_surface ODE
        dC = self._dC_surface_dt(upwelling_uM, growth)

        # 3. 탄소 수출
        carbon_export = self._carbon_export_rate()
        co2_sink      = self._co2_sink_ppm_per_yr(carbon_export)

        # 4. 오일러 적분
        self.phyto     = max(PHYTO_MIN, min(PHYTO_MAX, self.phyto + dphyto * dt))
        self.C_surface = max(C_SURFACE_MIN, min(C_SURFACE_MAX, self.C_surface + dC * dt))
        self._time_yr += dt

        return OceanState(
            time_yr       = self._time_yr,
            C_surface     = self.C_surface,
            phyto_biomass = self.phyto,
            phyto_growth  = growth,
            carbon_export = carbon_export,
            CO2_sink_ppm  = co2_sink,
            upwelling_uM  = upwelling_uM,
            f_nutrient    = f_N,
        )


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_ocean_nutrients(
    C_surface_init: float = C_SURFACE_INIT,
    phyto_init: float = 1.0,
) -> OceanNutrients:
    """기본 지구 해양 생태계."""
    return OceanNutrients(C_surface_init=C_surface_init, phyto_init=phyto_init)


__all__ = [
    "OceanNutrients",
    "OceanState",
    "make_ocean_nutrients",
    "K_PHYTO_GROWTH",
    "K_EXPORT",
    "CO2_PPM_PER_GT_CO2",
    "K_N_HALF",
    "UMOL_N_TO_GN_PER_M2",
]
