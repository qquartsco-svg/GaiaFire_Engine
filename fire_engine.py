"""fire_engine.py — 전지구 산불 발생 예측 엔진 (Phase 7f → v1.1)

설계 철학:
  "환경 설정만 하면 항상성에 의해 산불이 발생할 지점이 자연스럽게 예측된다"

입력 (환경 설정):
  - 전지구 대기 상태: O2_frac, CO2_ppm
  - 태양 조건: obliquity_deg, F0 (태양상수)
  - 생태계 상태: 위도별 BandEco (목본, 낙엽, 수분)

출력:
  - 위도별 fire_risk map [0~1]
  - 전지구 산불 예상 지점 (hot spots)
  - 항상성 복원력 지표 (어느 위도에서 O₂ 소비가 일어나야 균형인가)
  - 계절별 변화 데이터
  - 전지구 로컬 플럭스 집계 [kg O2/m²/yr, kg C/m²/yr]

v1.1 핵심 변경:
  1. 단위 분리: fire_risk.py는 로컬 플럭스만. 전지구 ΔO2_frac은 여기서 변환
  2. BandEco dataclass — float 키 dict → 안전한 int 인덱스 구조
  3. provider 주입 — temp/moisture/fuel을 외부에서 끼워넣기 가능
     (독립 실행: 기본 내장 함수 / CookiieBrain 연결: LatitudeBands provider)

인지 브리지:
  ForgetEngine(forget_engine.py) 과 동일한 ODE 구조로 설계됨.
  fire_risk(위도) ↔ forget_risk(뉴런 ID)
  fire_o2_sink   ↔ atp_drain
  전지구 GFI     ↔ 전뇌 인지 부하 지수
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Callable

try:
    from .fire_risk import (
        compute_fire_risk, FireRiskState,
        f_O2_fire, f_fuel, f_temperature, f_dryness, dry_season_modifier,
    )
except ImportError:
    from fire_risk import (
        compute_fire_risk, FireRiskState,
        f_O2_fire, f_fuel, f_temperature, f_dryness, dry_season_modifier,
    )

# ── 위도 밴드 ──────────────────────────────────────────────────────────────────
BAND_COUNT = 12
BAND_CENTERS_DEG = [
    -90.0 + (i + 0.5) * (180.0 / BAND_COUNT)
    for i in range(BAND_COUNT)
]
BAND_CENTERS_RAD = [d * math.pi / 180.0 for d in BAND_CENTERS_DEG]

EPS = 1e-30

_raw_weights = [max(0.0, math.cos(r)) for r in BAND_CENTERS_RAD]
_total = sum(_raw_weights) + EPS
BAND_WEIGHTS = [w / _total for w in _raw_weights]

# 태양 물리
SOLAR_CONST   = 1361.0
SIGMA         = 5.6704e-8
ALBEDO_BASE   = 0.30
GREENHOUSE_DT = 33.0
OBLIQUITY_DEG = 23.45

# 전지구 O₂ 저장고 변환 상수 (Gaia 모듈 연결 시 사용)
KG_O2_PER_FRAC = 1.2e18    # [kg] 전지구 O₂ 총량 (O2_frac=1.0 기준)
LAND_AREA_M2   = 1.48e14   # [m²] 전지구 육지 면적


# ── BandEco dataclass (v1.1) ──────────────────────────────────────────────────

@dataclass
class BandEco:
    """위도 밴드 생태계 상태 (타입 안전 입력).

    band_idx: 0~11 (남극→북극)
    phi_deg:  밴드 중심 위도 [-82.5 ~ +82.5]
    B_wood:   목본 바이오매스 [kg C/m²]
    organic:  낙엽/유기물층 [kg C/m²]
    W_override: 수분 직접 지정 (None이면 기본 프로파일 사용) [0~1]

    인지 대응:
      B_wood   ↔ synapse_strength  (연료 = 기억 밀도)
      organic  ↔ debris_load       (낙엽 = 미처리 자극/노이즈)
      W_override ↔ attention_level (수분 = 주의력 자원)
    """
    band_idx:   int
    phi_deg:    float
    B_wood:     float = 2.0
    organic:    float = 0.5
    W_override: Optional[float] = None


# ── 기본 내장 provider 함수 (독립 실행용) ─────────────────────────────────────

def _default_solar_flux(phi_rad: float, time_yr: float,
                        obliquity_rad: float, F0: float) -> float:
    total = 0.0
    n = 8
    for s in range(n):
        frac  = (s + 0.5) / n
        delta = obliquity_rad * math.sin(2.0 * math.pi * frac)
        cos_h0 = max(-1.0, min(1.0, -math.tan(phi_rad) * math.tan(delta)))
        h0     = math.acos(cos_h0)
        f_daily = (F0 / math.pi) * (
            math.sin(phi_rad) * math.sin(delta) * h0
            + math.cos(phi_rad) * math.cos(delta) * math.sin(h0)
        )
        total += max(0.0, f_daily)
    return total / n


def _default_surface_temp(F: float) -> float:
    T_eq = ((F * (1.0 - ALBEDO_BASE)) / (SIGMA + EPS)) ** 0.25
    return T_eq + GREENHOUSE_DT


def _default_soil_moisture(phi_deg: float) -> float:
    abs_phi = abs(phi_deg)
    if abs_phi <= 30.0:
        return 0.9 - 0.2 * (abs_phi / 30.0)
    elif abs_phi <= 60.0:
        return 0.7 - 0.3 * ((abs_phi - 30.0) / 30.0)
    else:
        return 0.4 - 0.3 * ((abs_phi - 60.0) / 30.0)


def _default_fuel_profile(phi_deg: float) -> Tuple[float, float]:
    """기본 위도별 목본/낙엽 프로파일."""
    abs_phi = abs(phi_deg)
    B_wood = 2.0 * math.exp(-((abs_phi - 45.0) / 25.0) ** 2)
    organic = 0.5 * B_wood
    return B_wood, organic


# ── FireEnvSnapshot (v1.1) ────────────────────────────────────────────────────

@dataclass
class FireEnvSnapshot:
    """전지구 환경 상태 스냅샷 — FireEngine 입력.

    band_ecosystems: List[BandEco] (길이 = BAND_COUNT) 또는 None(기본 프로파일)
      → v1.1 변경: float 키 dict → int 인덱스 BandEco 리스트
    """
    O2_frac:        float = 0.21
    CO2_ppm:        float = 400.0
    obliquity_deg:  float = OBLIQUITY_DEG
    F0:             float = SOLAR_CONST
    time_yr:        float = 0.0
    band_ecosystems: Optional[List[BandEco]] = None   # None → 기본 프로파일

    def get_band(self, band_idx: int) -> BandEco:
        if self.band_ecosystems and 0 <= band_idx < len(self.band_ecosystems):
            return self.band_ecosystems[band_idx]
        phi = BAND_CENTERS_DEG[band_idx]
        B_wood, organic = _default_fuel_profile(phi)
        return BandEco(band_idx=band_idx, phi_deg=phi,
                       B_wood=B_wood, organic=organic)


# ── FireBandResult ────────────────────────────────────────────────────────────

@dataclass
class FireBandResult:
    """위도 밴드 산불 예측 결과."""
    band_idx:     int
    phi_deg:      float
    time_yr:      float
    fire_risk:    float
    f_O2:         float
    f_fuel:       float
    f_temp:       float
    f_dry:        float
    T_K:          float
    W_eff:        float
    B_wood:       float
    F_solar:      float
    fire_intensity:       float   # [kg C/m²/yr]   로컬 탄소 플럭스
    fire_o2_sink_kgO2:    float   # [kg O2/m²/yr]  로컬 O₂ 플럭스
    fire_co2_source_kgC:  float   # [kg C/m²/yr]   로컬 CO₂ 플럭스
    is_hotspot:   bool


# ── FireEngine (v1.1) ─────────────────────────────────────────────────────────

class FireEngine:
    """전지구 산불 발생 예측 엔진.

    환경 설정(snapshot) → 위도별 fire_risk map → hot spot 예측
    항상성과의 연결: fire_risk 분포 = O₂ 항상성 복원력 공간 분포

    provider 주입 (v1.1):
      temp_provider(phi_deg, time_yr, env) -> T [K]
      moisture_provider(phi_deg, time_yr, env) -> W [0~1]
      fuel_provider(phi_deg, time_yr, env) -> (B_wood, organic) [kg C/m²]

    독립 실행: provider=None → 기본 내장 함수 사용
    CookiieBrain 연결: LatitudeBands 객체를 provider로 주입

    사용:
        engine = FireEngine()
        env = FireEnvSnapshot(O2_frac=0.21, time_yr=0.5)
        result = engine.predict(env)
        engine.print_map(result)
    """

    HOTSPOT_THRESHOLD = 0.005

    def __init__(
        self,
        temp_provider:     Optional[Callable] = None,
        moisture_provider: Optional[Callable] = None,
        fuel_provider:     Optional[Callable] = None,
    ):
        """
        provider 미지정 시 기본 내장 물리 함수 사용.
        외부 주입 시그니처:
          temp_provider(phi_deg, time_yr, env: FireEnvSnapshot) -> float [K]
          moisture_provider(phi_deg, time_yr, env) -> float [0~1]
          fuel_provider(phi_deg, time_yr, env) -> (B_wood, organic) [kg C/m²]
        """
        self._temp_provider     = temp_provider
        self._moisture_provider = moisture_provider
        self._fuel_provider     = fuel_provider

    def _get_temp(self, phi_deg: float, time_yr: float,
                  env: FireEnvSnapshot) -> float:
        if self._temp_provider:
            return self._temp_provider(phi_deg, time_yr, env)
        phi_rad = phi_deg * math.pi / 180.0
        obliquity_rad = env.obliquity_deg * math.pi / 180.0
        F = _default_solar_flux(phi_rad, time_yr, obliquity_rad, env.F0)
        return _default_surface_temp(F), F

    def _get_temp_and_flux(self, phi_deg: float, time_yr: float,
                           env: FireEnvSnapshot) -> Tuple[float, float]:
        """온도 + 태양 복사 동시 반환 (기본 provider 전용)."""
        if self._temp_provider:
            T = self._temp_provider(phi_deg, time_yr, env)
            phi_rad = phi_deg * math.pi / 180.0
            obliquity_rad = env.obliquity_deg * math.pi / 180.0
            F = _default_solar_flux(phi_rad, time_yr, obliquity_rad, env.F0)
            return T, F
        phi_rad = phi_deg * math.pi / 180.0
        obliquity_rad = env.obliquity_deg * math.pi / 180.0
        F = _default_solar_flux(phi_rad, time_yr, obliquity_rad, env.F0)
        T = _default_surface_temp(F)
        return T, F

    def _get_moisture(self, phi_deg: float, time_yr: float,
                      env: FireEnvSnapshot) -> float:
        if self._moisture_provider:
            return self._moisture_provider(phi_deg, time_yr, env)
        return _default_soil_moisture(phi_deg)

    def _get_fuel(self, band_idx: int, phi_deg: float,
                  time_yr: float, env: FireEnvSnapshot) -> Tuple[float, float]:
        if self._fuel_provider:
            return self._fuel_provider(phi_deg, time_yr, env)
        eco = env.get_band(band_idx)
        return eco.B_wood, eco.organic

    def predict(self, env: FireEnvSnapshot) -> List[FireBandResult]:
        """전지구 산불 위험도 예측."""
        results = []
        for band_idx, (phi_deg, phi_rad) in enumerate(
                zip(BAND_CENTERS_DEG, BAND_CENTERS_RAD)):

            T, F = self._get_temp_and_flux(phi_deg, env.time_yr, env)
            W    = self._get_moisture(phi_deg, env.time_yr, env)
            B_wood, organic = self._get_fuel(band_idx, phi_deg, env.time_yr, env)

            dry_mod = dry_season_modifier(phi_deg, env.time_yr)
            W_eff   = W * dry_mod

            rs = compute_fire_risk(
                O2=env.O2_frac, T=T, W=W,
                B_wood=B_wood, phi_deg=phi_deg, time_yr=env.time_yr,
                organic_litter=organic, solar_flux=F,
            )

            results.append(FireBandResult(
                band_idx            = band_idx,
                phi_deg             = phi_deg,
                time_yr             = env.time_yr,
                fire_risk           = rs.fire_risk,
                f_O2                = rs.f_O2,
                f_fuel              = rs.f_fuel,
                f_temp              = rs.f_temp,
                f_dry               = rs.f_dry,
                T_K                 = T,
                W_eff               = W_eff,
                B_wood              = B_wood,
                F_solar             = F,
                fire_intensity      = rs.fire_intensity,
                fire_o2_sink_kgO2   = rs.fire_o2_sink_kgO2,
                fire_co2_source_kgC = rs.fire_co2_source_kgC,
                is_hotspot          = rs.fire_risk > self.HOTSPOT_THRESHOLD,
            ))
        return results

    def predict_seasonal(
        self, env: FireEnvSnapshot, n_seasons: int = 8
    ) -> List[Tuple[float, List[FireBandResult]]]:
        seasons = []
        for i in range(n_seasons):
            t = env.time_yr + i / n_seasons
            env_t = FireEnvSnapshot(
                O2_frac=env.O2_frac, CO2_ppm=env.CO2_ppm,
                obliquity_deg=env.obliquity_deg, F0=env.F0,
                time_yr=t, band_ecosystems=env.band_ecosystems,
            )
            seasons.append((t, self.predict(env_t)))
        return seasons

    def global_fire_index(self, results: List[FireBandResult]) -> float:
        return sum(r.fire_risk * BAND_WEIGHTS[i]
                   for i, r in enumerate(results))

    def global_o2_flux(self, results: List[FireBandResult]) -> float:
        """전지구 면적 가중 O₂ 소비 플럭스 [kg O2/m²/yr].

        Gaia 모듈 연결 시:
          ΔO2_frac = -(global_o2_flux × dt × LAND_AREA_M2) / KG_O2_PER_FRAC
        """
        return sum(r.fire_o2_sink_kgO2 * BAND_WEIGHTS[i]
                   for i, r in enumerate(results))

    def delta_O2_frac(self, results: List[FireBandResult],
                      dt_yr: float = 1.0) -> float:
        """전지구 O₂ fraction 변화량 계산 (Gaia 대기 모듈 연결용).

        단위 변환 여기서만 수행:
          ΔO2_frac = -(Σ fire_o2_sink × area_weight × dt × LAND_AREA) / KG_O2_PER_FRAC
        """
        flux = self.global_o2_flux(results)
        return -(flux * dt_yr * LAND_AREA_M2) / KG_O2_PER_FRAC

    def homeostasis_pressure(self, results: List[FireBandResult],
                              O2_target: float = 0.21) -> Dict[str, Any]:
        """항상성 복원 압력 분석.

        반환:
          global_fire_index     [0~1]  : 전지구 산불 강도
          dominant_latitude     [°]    : 최고 위험 위도
          total_fire_co2_flux   [kg C/m²/yr]: 전지구 가중 CO₂ 방출
          global_o2_flux        [kg O2/m²/yr]: 전지구 가중 O₂ 소비
          delta_O2_frac_per_yr  [mol/mol/yr]: 대기 O₂ 감소율 (Gaia 연결용)
          homeostasis_pressure  [0~1]  : 복원 필요 강도
        """
        dominant_lat = max(results, key=lambda r: r.fire_risk).phi_deg
        total_co2 = sum(r.fire_co2_source_kgC * BAND_WEIGHTS[i]
                        for i, r in enumerate(results))
        gfi  = self.global_fire_index(results)
        gof  = self.global_o2_flux(results)
        do2  = self.delta_O2_frac(results, dt_yr=1.0)

        return {
            "global_fire_index":    gfi,
            "dominant_latitude":    dominant_lat,
            "total_fire_co2_flux":  total_co2,
            "global_o2_flux":       gof,
            "delta_O2_frac_per_yr": do2,
            "homeostasis_pressure": min(1.0, gfi * 2.0),
        }

    def print_map(self, results: List[FireBandResult],
                  title: str = "전지구 산불 위험도 MAP") -> None:
        print(f"\n  {title}")
        print(f"  {'위도':>7}  {'위험도':>7}  {'O₂':>5}  {'연료':>5}  "
              f"{'온도':>5}  {'건조':>5}  {'T(°C)':>7}  {'W':>5}  "
              f"{'강도(kgC)':>10}  {'O₂소비(kgO2)':>13}  시각화")
        print("  " + "-" * 110)
        for r in results:
            bar_len = int(r.fire_risk * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            spot = "🔥HOT" if r.is_hotspot else "   "
            print(
                f"  {r.phi_deg:>7.1f}°"
                f"  {r.fire_risk:>7.3f}"
                f"  {r.f_O2:>5.2f}"
                f"  {r.f_fuel:>5.2f}"
                f"  {r.f_temp:>5.2f}"
                f"  {r.f_dry:>5.2f}"
                f"  {r.T_K-273.15:>7.1f}"
                f"  {r.W_eff:>5.2f}"
                f"  {r.fire_intensity:>10.4f}"
                f"  {r.fire_o2_sink_kgO2:>13.4f}"
                f"  |{bar}| {spot}"
            )
