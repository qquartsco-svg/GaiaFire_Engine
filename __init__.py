"""GaiaFire Engine v1.1 — 전지구 산불 + 인지 망각 항상성 엔진

설계 철학:
  "환경 설정만 하면 항상성에 의해 산불/망각이 발생할 지점이 자연스럽게 창발된다"

구조:
  fire_risk.py    → 단일 위도×계절 산불 위험도 ODE (로컬 플럭스만)
  fire_engine.py  → 전지구 예측 엔진 (BandEco, provider 주입, ΔO2_frac 변환)
  forget_engine.py→ 인지 망각 ODE (산불과 동일 attractor 구조)
  demo.py         → 산불 4시나리오 데모
  forget_demo.py  → 망각 4시나리오 데모

v1.1 변경:
  - 단위 분리: fire_risk.py = 로컬 플럭스 [kgO2/m²/yr]
  - BandEco dataclass (float 키 → int 인덱스)
  - FireEngine provider 주입 (CookiieBrain LatitudeBands 연결용)
  - ForgetEngine: 산불 ODE → 인지 망각 ODE 브리지
  - GaiaForgetBridge: 행성-뇌 항상성 동기화 분석
  - INTERFACE_CONTRACT.md: 10줄 규약 문서
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

__version__ = "1.1.0"

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
    # 상수
    "BAND_COUNT", "BAND_CENTERS_DEG", "BAND_WEIGHTS",
    "KG_O2_PER_FRAC", "LAND_AREA_M2",
]
