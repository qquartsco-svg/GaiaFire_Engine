# GaiaFire Engine
**전지구 산불 발생 예측 시스템 — 항상성 기반 자연 창발 엔진**

> "환경 설정만 하면, 항상성에 의해 산불이 발생할 지점이 자연스럽게 결정된다"

---

## 개념

지구 대기의 O₂ 농도가 일정 수준을 넘으면, 특정 위도·계절에서 산불이 자동으로 발생하여 O₂를 소비한다.
이 엔진은 그 **"어느 지점에서 산불이 발생해야 항상성이 유지되는가"** 를 물리 법칙으로 계산한다.

```
입력: O₂ 농도, 태양 위치(계절), 위도별 생태계 상태
출력: 전지구 산불 위험도 맵 + hot spot 위치 + 항상성 복원력 지수
```

산불은 3요소의 곱으로 결정된다:
```
fire_risk = f_O2 × f_fuel × f_temp × f_dry

f_O2(O2)     : O₂ > 15% 점화 가능, > 25% 기하급수 증가
f_fuel(B_wood): 목본+낙엽 연료량 (Michaelis-Menten)
f_temp(T)    : 온도 삼각형 게이트 (10~60°C 최적)
f_dry(W,φ,t) : 위도별 건기 계절성 → 북반구 여름, 남반구 겨울 건기
```

---

## 파일 구조

```
GaiaFire_Engine/
  fire_risk.py    — 단일 위도×계절 산불 위험도 ODE (물리 핵심)
  fire_engine.py  — 전지구 예측 엔진 (12밴드 × 계절 × 항상성 해석)
  __init__.py     — 공개 API
  demo.py         — 4시나리오 데모 실행
  README.md       — 이 파일
```

---

## 빠른 시작

```python
from fire_engine import FireEngine, FireEnvSnapshot

engine = FireEngine()

# 환경 설정: O₂=25%, 북반구 여름
env = FireEnvSnapshot(O2_frac=0.25, time_yr=0.5)

# 전지구 산불 위험도 예측
results = engine.predict(env)
engine.print_map(results)

# 항상성 복원력 분석
hp = engine.homeostasis_pressure(results)
print(f"주요 hot spot 위도: {hp['dominant_latitude']}°")
print(f"항상성 복원 압력: {hp['homeostasis_pressure']:.3f}")
```

데모 실행:
```bash
python demo.py
```

---

## 핵심 물리

| 파라미터 | 값 | 근거 |
|---|---|---|
| `O2_IGNITION_MIN` | 15% | O₂<15% 점화 불가 (Lenton & Watson 2000) |
| `O2_IGNITION_HIGH` | 25% | O₂>25% 산불 발생률 2배 이상 (Berner 2006) |
| `K_FIRE_INTENSITY` | 2.0 kg C/m²/yr | 보레알 산불 관측 0.5~3 kg C/m²/yr |
| `DRY_AMPLITUDE_TROPICAL` | 0.6 | 열대 건기 진폭 |
| `DRY_AMPLITUDE_TEMPERATE` | 0.4 | 온대 건기 진폭 |

---

## 검증 결과 (ALL PASS)

```
V1: O₂=21% 북반구 여름 → 북위 7.5°, 22.5° hot spot 자동 창발 ✓
V2: O₂=28% GFI > O₂=21% GFI (고O₂ → 더 많은 산불) ✓
V3: O₂=15% → GFI=0 (산불 발생 불가) ✓
V4: 북반구 여름 산불 > 겨울 (계절성 창발) ✓
```

계절별 hot spot 이동:
```
북반구 여름 (t=0.5yr): 북위 7.5°, 22.5° → 아열대 건기 산불
북반구 겨울 (t=0.0yr): 남위 7.5°, 22.5° → 남반구 여름 건기 산불
```

---

## 항상성 해석

```
O₂ < 25% → 산불 없음 → 광합성/호흡이 O₂ 결정
O₂ > 25% → 건조+고온 위도에서 산불 자동 발생 → O₂ 소비
산불 hot spot = "O₂ 항상성이 복원되어야 할 공간적 지점"

뉴런 ATP 항상성과 동일한 구조:
  세포:  ATP 이탈 → recover_k↑ → 복원 (음의 피드백)
  행성:  O₂ > 25% → fire_risk↑ → O₂↓ (음의 피드백)
  수학:  ∂(d상태/dt)/∂상태 < 0  (attractor 조건)
```

---

## 발전 방향

- **위성 데이터 연결**: MODIS 산불 탐지 데이터와 비교 검증
- **기후 모델 연결**: CMIP6 출력 → 환경 설정 자동 주입
- **CookiieBrain 통합**: 뉴런 항상성 → Gaia 항상성 → 산불 경보 시스템
- **실시간 예측**: 현재 O₂ 측정값 + 계절 → 산불 위험 지도 생성

---

## 의존성

```
Python >= 3.8
표준 라이브러리만 사용 (math, dataclasses, typing)
외부 패키지 없음
```

---

*GaiaFire Engine — CookiieBrain Phase 7f*
*설계: 세차운동·토양·생태계 항상성과 동일한 물리 철학*
