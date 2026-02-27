"""gravity_tides/ocean_nutrients.py — 해양 영양염 + 탄소 펌프 (넷째날 순환 3-B)

설계 철학:
    영양염 upwelling → 식물플랑크톤 성장 → 생물학적 탄소 펌프
    → 심층 탄소 격리 → 대기 CO₂↓ → T↓ (음의 피드백)

수식:
    phyto_growth = K_phyto × nutrient_flux × light_factor
    carbon_export = K_export × phyto_biomass × sinking_rate
    CO2_sink = carbon_export × C_to_CO2_factor

    영양염 균형:
    dC_surface/dt = upwelling_flux - phyto_uptake - grazing - mixing_loss

v1.0 (넷째날 순환 3-B):
    OceanNutrients: 표층 영양염 + 식물플랑크톤 동역학
    CarbonPump: 생물학적 탄소 펌프 → CO₂ 격리
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ── 상수 ──────────────────────────────────────────────────────────────────────

# 식물플랑크톤
K_PHYTO_GROWTH    = 0.3     # [yr⁻¹ per (g nutrient m⁻² yr⁻¹)] 성장 속도
K_GRAZING         = 0.15    # [yr⁻¹] 동물플랑크톤 섭식률
K_MORTALITY       = 0.05    # [yr⁻¹] 자연 사멸률
PHYTO_MAX         = 50.0    # [g C m⁻²] 최대 식물플랑크톤 탄소량
PHYTO_MIN         = 0.01    # [g C m⁻²] 최솟값

# 빛 제한 (위도 평균)
LIGHT_FACTOR_REF  = 0.7     # 현재 지구 평균 (구름, 깊이 보정)

# 탄소 수출 (생물 펌프)
K_EXPORT          = 0.15    # [yr⁻¹] 탄소 침강 수출 효율
C_TO_CO2          = 3.67    # [g CO₂ / g C]  분자량 비 (44/12)
LAND_AREA_M2      = 3.6e14  # [m²] 전지구 해양 면적

# 영양염-식물플랑크톤 연결
NUTRIENT_TO_C     = 6.625   # 레드필드 비율 C:N = 106:16 ≈ 6.625

# CO₂ 단위 변환 (g CO₂ → ppm)
# 대기 CO₂ 1ppm = 2.13 GtC = 7.81 Gt CO₂
CO2_PPM_PER_GT_CO2 = 1.0 / 7.81   # [ppm / Gt CO₂]
GT_TO_G = 1e15                     # [g / Gt]

EPS = 1e-30


# ── 스냅샷 ────────────────────────────────────────────────────────────────────

@dataclass
class OceanState:
    """해양 생태계 상태 스냅샷.

    Attributes:
        time_yr:        시간 [yr]
        C_surface:      표층 영양염 [μmol/L]
        phyto_biomass:  식물플랑크톤 탄소량 [g C m⁻²]
        phyto_growth:   성장률 [g C m⁻² yr⁻¹]
        carbon_export:  탄소 수출 [g C m⁻² yr⁻¹]
        CO2_sink_ppm:   CO₂ 격리량 [ppm/yr] (전지구 환산)
        nutrient_flux:  upwelling 영양염 [g m⁻² yr⁻¹]
    """
    time_yr: float
    C_surface: float
    phyto_biomass: float
    phyto_growth: float
    carbon_export: float
    CO2_sink_ppm: float
    nutrient_flux: float

    def summary(self) -> str:
        return (
            f"t={self.time_yr:.1f}yr | "
            f"nutrient={self.nutrient_flux:.4f} | "
            f"phyto={self.phyto_biomass:.3f} gC/m² | "
            f"export={self.carbon_export:.4f} gC/m²/yr | "
            f"CO2_sink={self.CO2_sink_ppm:.6f} ppm/yr"
        )


# ── OceanNutrients ────────────────────────────────────────────────────────────

class OceanNutrients:
    """해양 영양염 동역학 + 생물학적 탄소 펌프.

    사용법::

        ocean = OceanNutrients()

        state = ocean.step(
            dt=1.0,
            nutrient_flux=0.5,    # TidalField에서 주입
            light_factor=0.7,
        )
        print(state.CO2_sink_ppm)   # → atmosphere.CO2 감소 연결
    """

    def __init__(
        self,
        C_surface_init: float = 5.0,    # [μmol/L]
        phyto_init: float = 1.0,        # [g C m⁻²]
        K_phyto: float = K_PHYTO_GROWTH,
        K_grazing: float = K_GRAZING,
        K_mortality: float = K_MORTALITY,
        K_export: float = K_EXPORT,
    ):
        self.C_surface    = max(0.0, C_surface_init)
        self.phyto        = max(PHYTO_MIN, phyto_init)
        self.K_phyto      = K_phyto
        self.K_grazing    = K_grazing
        self.K_mortality  = K_mortality
        self.K_export     = K_export
        self._time_yr     = 0.0

    # ── 내부 계산 ─────────────────────────────────────────────────────────────

    def _phyto_growth_rate(self, nutrient_flux: float, light: float) -> float:
        """식물플랑크톤 순 성장률 [g C m⁻² yr⁻¹].

        growth = K_phyto × nutrient_flux × light × (1 - phyto/PHYTO_MAX)
        """
        carrying_capacity = max(0.0, 1.0 - self.phyto / PHYTO_MAX)
        return self.K_phyto * max(0.0, nutrient_flux) * light * carrying_capacity

    def _phyto_loss_rate(self) -> float:
        """식물플랑크톤 손실률 [g C m⁻² yr⁻¹].

        손실 = 섭식 + 사멸
        """
        return (self.K_grazing + self.K_mortality) * self.phyto

    def _carbon_export_rate(self) -> float:
        """탄소 침강 수출 [g C m⁻² yr⁻¹].

        export = K_export × phyto_biomass
        """
        return self.K_export * self.phyto

    def _co2_sink_ppm_per_yr(self, carbon_export: float) -> float:
        """탄소 수출 → 대기 CO₂ 감소 [ppm/yr].

        CO₂_sink [Gt CO₂/yr] = carbon_export × C_TO_CO2 × LAND_AREA_M2 / GT_TO_G
        CO₂_sink [ppm/yr]    = CO₂_sink [Gt] × CO2_PPM_PER_GT_CO2
        """
        co2_gt = carbon_export * C_TO_CO2 * LAND_AREA_M2 / GT_TO_G
        return co2_gt * CO2_PPM_PER_GT_CO2

    # ── step ──────────────────────────────────────────────────────────────────

    def step(
        self,
        dt: float,
        nutrient_flux: float,
        light_factor: float = LIGHT_FACTOR_REF,
    ) -> OceanState:
        """해양 생태계 1 타임스텝 (오일러 적분).

        Args:
            dt:             타임스텝 [yr]
            nutrient_flux:  TidalField에서 주입한 영양염 [g m⁻² yr⁻¹]
            light_factor:   빛 제한 팩터 [0~1]

        Returns:
            OceanState
        """
        # 1. 식물플랑크톤 성장/손실
        growth = self._phyto_growth_rate(nutrient_flux, light_factor)
        loss   = self._phyto_loss_rate()
        dphyto = growth - loss

        # 2. 탄소 수출 (생물 펌프)
        carbon_export = self._carbon_export_rate()
        co2_sink      = self._co2_sink_ppm_per_yr(carbon_export)

        # 3. 오일러 적분
        self.phyto     = max(PHYTO_MIN, min(PHYTO_MAX, self.phyto + dphyto * dt))
        self._time_yr += dt

        return OceanState(
            time_yr        = self._time_yr,
            C_surface      = self.C_surface,
            phyto_biomass  = self.phyto,
            phyto_growth   = growth,
            carbon_export  = carbon_export,
            CO2_sink_ppm   = co2_sink,
            nutrient_flux  = nutrient_flux,
        )


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_ocean_nutrients(
    C_surface_init: float = 5.0,
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
]
