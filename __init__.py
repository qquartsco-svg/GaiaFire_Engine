"""GaiaFire_Engine — 전지구 산불 발생 예측 엔진

설계 철학:
  "환경 설정(O2, T, W, 위도, 계절)만 하면
   항상성에 의해 산불이 발생할 지점이 자연스럽게 창발된다"

구조:
  fire_risk.py   → 단일 위도×계절 산불 위험도 ODE (물리 층)
  fire_engine.py → 전지구 예측 엔진 (12밴드 × 계절 × 항상성 해석)
  demo.py        → 4시나리오 데모 실행

독립 모듈:
  외부 의존성 없음 (Python 표준 라이브러리만 사용)
  환경 snapshot(O2, T, W, B_wood)만 받아서 동작

발전 방향:
  - 실제 위성 관측 (MODIS 산불 탐지)과 비교 검증
  - 기후 모델 출력 연결 (CMIP6 등)
  - CookiieBrain 뉴런 항상성 → Gaia 항상성 → 산불 경보 통합
"""

from .fire_risk import (
    compute_fire_risk,
    FireRiskState,
    f_O2_fire,
    f_fuel,
    f_temperature,
    f_dryness,
    dry_season_modifier,
    O2_IGNITION_MIN,
    O2_IGNITION_HIGH,
    K_FIRE_INTENSITY,
)
from .fire_engine import (
    FireEngine,
    FireEnvSnapshot,
    FireBandResult,
    BAND_CENTERS_DEG,
    BAND_WEIGHTS,
)

__version__ = "1.0.0"

__all__ = [
    "compute_fire_risk", "FireRiskState",
    "f_O2_fire", "f_fuel", "f_temperature", "f_dryness", "dry_season_modifier",
    "O2_IGNITION_MIN", "O2_IGNITION_HIGH", "K_FIRE_INTENSITY",
    "FireEngine", "FireEnvSnapshot", "FireBandResult",
    "BAND_CENTERS_DEG", "BAND_WEIGHTS",
]
