"""fire_engine.py — 전지구 산불 발생 예측 엔진 (Phase 7f)

설계 철학:
  "환경 설정만 하면 항상성에 의해 산불이 발생할 지점이 자연스럽게 예측된다"

입력 (환경 설정):
  - 전지구 대기 상태: O2_frac, CO2_ppm
  - 태양 조건: obliquity_deg, F0 (태양상수)
  - 생태계 상태: 위도별 B_wood, organic_layer, soil_moisture

출력:
  - 위도별 fire_risk map [0~1]
  - 전지구 산불 예상 지점 (hot spots)
  - 항상성 복원력 지표 (어느 위도에서 O₂ 소비가 일어나야 균형인가)
  - 계절별 변화 애니메이션 데이터

독립 모듈 원칙:
  - solar/biosphere/에 의존하지 않음
  - 환경 snapshot만 받아서 동작
  - LatitudeBands와 연결하거나, 독립 실행 모두 가능

발전 방향 (향후):
  - 실제 위성 관측 데이터 (MODIS 산불 탐지) 와 비교
  - 기후 모델 출력과 연결
  - 뉴런 항상성과 연결: 신경계 "경보" 시스템 아날로그
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

try:
    # 패키지로 import될 때 (solar.fire)
    from .fire_risk import (
        compute_fire_risk, FireRiskState,
        f_O2_fire, f_fuel, f_temperature, f_dryness, dry_season_modifier,
    )
except ImportError:
    # 독립 실행 (GaiaFire_Engine/)
    from fire_risk import (
        compute_fire_risk, FireRiskState,
        f_O2_fire, f_fuel, f_temperature, f_dryness, dry_season_modifier,
    )

# ── 위도 밴드 (latitude_bands.py와 동일 — 독립 정의) ──────────────────────────
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

# 태양 물리 (독립 상수)
SOLAR_CONST   = 1361.0
SIGMA         = 5.6704e-8
ALBEDO_BASE   = 0.30
GREENHOUSE_DT = 33.0
OBLIQUITY_DEG = 23.45


# ── 기본 위도별 환경 프로파일 ──────────────────────────────────────────────────

def _solar_flux(phi_rad: float, time_yr: float,
                obliquity_rad: float, F0: float = SOLAR_CONST) -> float:
    """위도×계절 연평균 복사 조도 (latitude_bands.py와 동일 구현)."""
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


def _surface_temp(F: float) -> float:
    T_eq = ((F * (1.0 - ALBEDO_BASE)) / (SIGMA + EPS)) ** 0.25
    return T_eq + GREENHOUSE_DT


def _soil_moisture_base(phi_deg: float) -> float:
    """위도별 연평균 기본 토양 수분 [0~1]."""
    abs_phi = abs(phi_deg)
    if abs_phi <= 30.0:
        return 0.9 - 0.2 * (abs_phi / 30.0)
    elif abs_phi <= 60.0:
        return 0.7 - 0.3 * ((abs_phi - 30.0) / 30.0)
    else:
        return 0.4 - 0.3 * ((abs_phi - 60.0) / 30.0)


# ── FireEnvSnapshot ────────────────────────────────────────────────────────────

@dataclass
class FireEnvSnapshot:
    """전지구 환경 상태 스냅샷 — FireEngine 입력."""
    O2_frac:      float = 0.21          # 전지구 대기 O₂
    CO2_ppm:      float = 400.0         # 전지구 대기 CO₂
    obliquity_deg: float = OBLIQUITY_DEG
    F0:           float = SOLAR_CONST
    time_yr:      float = 0.0

    # 위도별 생태계 상태 (없으면 기본값 사용)
    # dict: {phi_deg: {"B_wood": float, "organic": float, "W_override": float}}
    band_ecosystem: Dict[float, Dict[str, float]] = field(default_factory=dict)

    def get_band(self, phi_deg: float) -> Dict[str, float]:
        """위도 밴드 생태계 상태 반환 (없으면 기본 프로파일)."""
        if phi_deg in self.band_ecosystem:
            return self.band_ecosystem[phi_deg]
        # 기본: 성숙 온대 생태계 스케일
        abs_phi = abs(phi_deg)
        # 목본: 중위도 최대, 극지·열대 감소 (연속 함수)
        B_wood_base = 2.0 * math.exp(-((abs_phi - 45.0) / 25.0) ** 2)
        # 낙엽: B_wood 비례
        organic_base = 0.5 * B_wood_base
        return {
            "B_wood":  B_wood_base,
            "organic": organic_base,
        }


# ── FireBandResult ────────────────────────────────────────────────────────────

@dataclass
class FireBandResult:
    """위도 밴드 산불 예측 결과."""
    phi_deg:      float
    time_yr:      float
    fire_risk:    float    # [0~1] 종합 위험도
    f_O2:         float
    f_fuel:       float
    f_temp:       float
    f_dry:        float
    T_K:          float    # 지표 온도 [K]
    W_eff:        float    # 유효 수분 (건기 보정 후)
    B_wood:       float
    F_solar:      float    # 태양 복사 [W/m²]
    fire_intensity: float  # [kg C/m²/yr]
    is_hotspot:   bool     # fire_risk > threshold


# ── FireEngine ────────────────────────────────────────────────────────────────

class FireEngine:
    """전지구 산불 발생 예측 엔진.

    환경 설정(snapshot) → 위도별 fire_risk map → hot spot 예측
    항상성과의 연결: fire_risk 분포 = O₂ 항상성 복원력 공간 분포

    사용:
        env = FireEnvSnapshot(O2_frac=0.21, time_yr=0.5)  # 여름
        engine = FireEngine()
        result = engine.predict(env)
        engine.print_map(result)
    """

    HOTSPOT_THRESHOLD = 0.005  # fire_risk > 0.005 → hot spot
                               # O₂=21% 성숙 생태계 최대값 ≈ 0.012 기준으로 설정

    def predict(self, env: FireEnvSnapshot) -> List[FireBandResult]:
        """전지구 산불 위험도 예측.

        12개 위도 밴드 × 환경 조건 → FireBandResult 리스트
        """
        obliquity_rad = env.obliquity_deg * math.pi / 180.0
        results = []

        for phi_deg, phi_rad in zip(BAND_CENTERS_DEG, BAND_CENTERS_RAD):
            # 물리 환경
            F     = _solar_flux(phi_rad, env.time_yr, obliquity_rad, env.F0)
            T     = _surface_temp(F)
            W_base = _soil_moisture_base(phi_deg)

            # 생태계 상태
            eco   = env.get_band(phi_deg)
            B_wood   = eco.get("B_wood",  0.0)
            organic  = eco.get("organic", 0.0)
            W_override = eco.get("W_override", None)
            W = W_override if W_override is not None else W_base

            # 건기 보정 수분
            dry_mod = dry_season_modifier(phi_deg, env.time_yr)
            W_eff   = W * dry_mod

            # 산불 위험도 계산
            rs = compute_fire_risk(
                O2            = env.O2_frac,
                T             = T,
                W             = W,
                B_wood        = B_wood,
                phi_deg       = phi_deg,
                time_yr       = env.time_yr,
                organic_litter= organic,
                solar_flux    = F,
            )

            results.append(FireBandResult(
                phi_deg      = phi_deg,
                time_yr      = env.time_yr,
                fire_risk    = rs.fire_risk,
                f_O2         = rs.f_O2,
                f_fuel       = rs.f_fuel,
                f_temp       = rs.f_temp,
                f_dry        = rs.f_dry,
                T_K          = T,
                W_eff        = W_eff,
                B_wood       = B_wood,
                F_solar      = F,
                fire_intensity = rs.fire_intensity,
                is_hotspot   = rs.fire_risk > self.HOTSPOT_THRESHOLD,
            ))

        return results

    def predict_seasonal(
        self, env: FireEnvSnapshot, n_seasons: int = 8
    ) -> List[Tuple[float, List[FireBandResult]]]:
        """연간 계절별 예측 (n_seasons 등간격).

        반환: [(time_yr, [FireBandResult, ...]), ...]
        """
        seasons = []
        for i in range(n_seasons):
            t = env.time_yr + i / n_seasons
            env_t = FireEnvSnapshot(
                O2_frac       = env.O2_frac,
                CO2_ppm       = env.CO2_ppm,
                obliquity_deg = env.obliquity_deg,
                F0            = env.F0,
                time_yr       = t,
                band_ecosystem= env.band_ecosystem,
            )
            seasons.append((t, self.predict(env_t)))
        return seasons

    def global_fire_index(self, results: List[FireBandResult]) -> float:
        """전지구 면적 가중 산불 위험 지수 [0~1].

        높을수록 O₂ 항상성 복원 압력이 큰 상태.
        """
        total = sum(r.fire_risk * BAND_WEIGHTS[i]
                    for i, r in enumerate(results))
        return total

    def homeostasis_pressure(self, results: List[FireBandResult],
                              O2_target: float = 0.21) -> Dict[str, float]:
        """항상성 복원 압력 분석.

        현재 O₂와 목표 O₂의 차이를 산불 분포로 해석:
          O₂ > O2_target → fire_risk 높은 위도에서 소비 필요
          O₂ < O2_target → 산불 없어야 (광합성 키워야)

        반환:
          pressure: 전지구 항상성 복원 압력 [0~1]
          dominant_lat: 가장 많이 소비해야 할 위도
          total_fire_co2: 전지구 예상 산불 CO₂ 방출 [kg C/m²/yr, 면적 가중]
        """
        dominant_lat = max(results, key=lambda r: r.fire_risk).phi_deg
        total_fire_co2 = sum(
            r.fire_intensity * BAND_WEIGHTS[i]
            for i, r in enumerate(results)
        )
        gfi = self.global_fire_index(results)

        return {
            "global_fire_index":   gfi,
            "dominant_latitude":   dominant_lat,
            "total_fire_co2_flux": total_fire_co2,
            "homeostasis_pressure": min(1.0, gfi * 2.0),
        }

    def print_map(self, results: List[FireBandResult],
                  title: str = "전지구 산불 위험도 MAP") -> None:
        """위도별 산불 위험도 시각화 출력."""
        print(f"\n  {title}")
        print(f"  {'위도':>7}  {'위험도':>7}  {'O₂':>5}  {'연료':>5}  "
              f"{'온도':>5}  {'건조':>5}  {'T(°C)':>7}  {'W':>5}  "
              f"{'강도(kgC)':>10}  시각화")
        print("  " + "-" * 90)
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
                f"  |{bar}| {spot}"
            )
