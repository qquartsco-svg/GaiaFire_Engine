"""GaiaFire Engine v1.2 — 전지구 산불 + 인지 망각 + 시간 스케일 번역기

설계 철학:
  "환경 설정만 하면 항상성에 의해 산불/망각이 발생할 지점이 자연스럽게 창발된다"

구조:
  fire_risk.py         → 단일 위도×계절 산불 위험도 ODE (로컬 플럭스만)
  fire_engine.py       → 전지구 예측 엔진 (BandEco, provider 주입, ΔO2_frac 변환)
  forget_engine.py     → 인지 망각 ODE (산불과 동일 attractor 구조)
  stress_accumulator.py→ 뉴런(ms)→기관(hr)→행성(yr) 3단계 번역기 + LocalFireReset
  demo.py              → 산불 4시나리오 데모
  forget_demo.py       → 망각 4시나리오 데모
  stress_demo.py       → 적산기 4시나리오 데모

v1.2 변경:
  - StressAccumulator: 뉴런 이벤트 → 행성 스트레스 3단계 적산 파이프라인
  - LocalFireReset: 산불 발생 시 B_wood 국소 소각 + 스트레스 해소
  - HOMEO_MAP.md: 미시(뉴런)-거시(행성) 완전 변수 매핑 테이블
"""

try:
    from .fire_risk import (
        compute_fire_risk, FireRiskState,
        f_O2_fire, f_fuel, f_temperature, f_dryness, dry_season_modifier,
        O2_IGNITION_MIN, O2_IGNITION_HIGH, K_FIRE_INTENSITY,
    )
    from .fire_engine import (
        FireEngine, FireEnvSnapshot, FireBandResult, BandEco,
        BAND_COUNT, BAND_CENTERS_DEG, BAND_WEIGHTS,
        KG_O2_PER_FRAC, LAND_AREA_M2,
    )
    from .forget_engine import (
        ForgetEngine, CognitiveBrainSnapshot, ForgetRiskState,
        GaiaForgetBridge, compute_forget_risk,
        f_load, f_debris, f_stress, f_fatigue, circadian_modifier,
    )
    from .stress_accumulator import (
        StressAccumulator, LocalFireReset, NeuronEvent,
        CellStressState, OrganFatigueState, PlanetStressIndex,
    )
except ImportError:
    from fire_risk import (
        compute_fire_risk, FireRiskState,
        f_O2_fire, f_fuel, f_temperature, f_dryness, dry_season_modifier,
        O2_IGNITION_MIN, O2_IGNITION_HIGH, K_FIRE_INTENSITY,
    )
    from fire_engine import (
        FireEngine, FireEnvSnapshot, FireBandResult, BandEco,
        BAND_COUNT, BAND_CENTERS_DEG, BAND_WEIGHTS,
        KG_O2_PER_FRAC, LAND_AREA_M2,
    )
    from forget_engine import (
        ForgetEngine, CognitiveBrainSnapshot, ForgetRiskState,
        GaiaForgetBridge, compute_forget_risk,
        f_load, f_debris, f_stress, f_fatigue, circadian_modifier,
    )
    from stress_accumulator import (
        StressAccumulator, LocalFireReset, NeuronEvent,
        CellStressState, OrganFatigueState, PlanetStressIndex,
    )

__version__ = "1.2.0"

__all__ = [
    # 산불
    "FireEngine", "FireEnvSnapshot", "FireBandResult", "BandEco",
    "FireRiskState", "compute_fire_risk",
    "f_O2_fire", "f_fuel", "f_temperature", "f_dryness", "dry_season_modifier",
    "O2_IGNITION_MIN", "O2_IGNITION_HIGH", "K_FIRE_INTENSITY",
    # 망각
    "ForgetEngine", "CognitiveBrainSnapshot", "ForgetRiskState",
    "GaiaForgetBridge", "compute_forget_risk",
    "f_load", "f_debris", "f_stress", "f_fatigue", "circadian_modifier",
    # 적산기
    "StressAccumulator", "LocalFireReset", "NeuronEvent",
    "CellStressState", "OrganFatigueState", "PlanetStressIndex",
    # 상수
    "BAND_COUNT", "BAND_CENTERS_DEG", "BAND_WEIGHTS",
    "KG_O2_PER_FRAC", "LAND_AREA_M2",
]
