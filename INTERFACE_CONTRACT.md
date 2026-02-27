# GaiaFire Engine — 인터페이스 규약 (v1.1)

> Gaia(대기) 모듈이 GaiaFire Engine을 받아들이기 위한 최소 규약.
> 10줄 규약 — 이것만 지키면 어떤 외부 모듈에도 플러그인처럼 붙는다.

---

## 규약 1: fire_risk.py 는 로컬 플럭스만 반환한다

```
입력: O2[mol/mol], T[K], W[0~1], B_wood[kgC/m²], phi_deg[°], time_yr[yr]
출력: FireRiskState
  .fire_risk           [0~1]          산불 발생 확률
  .fire_intensity      [kgC/m²/yr]    탄소 소비 (로컬)
  .fire_o2_sink_kgO2   [kgO2/m²/yr]  O₂ 소비  (로컬) ← v1.1 핵심
  .fire_co2_source_kgC [kgC/m²/yr]   CO₂ 방출 (로컬)
```

**금지**: fire_risk.py 안에서 전지구 상수(KG_O2_PER_FRAC, LAND_AREA) 사용 금지.

---

## 규약 2: 전지구 O₂ fraction 변환은 Gaia 모듈이 수행한다

```python
# Gaia(대기) 모듈 또는 fire_engine.py 에서만:
ΔO2_frac = -(Σ fire_o2_sink_kgO2 × area_weight × dt) / KG_O2_PER_FRAC
# KG_O2_PER_FRAC = 1.2e18 [kg]  (전지구 O₂ 총량)
# 또는 fire_engine.delta_O2_frac(results, dt_yr) 호출
```

---

## 규약 3: BandEco 인터페이스 (밴드 입력)

```python
BandEco(
  band_idx:   int,           # 0~11 (남극→북극, float 키 사용 금지)
  phi_deg:    float,         # 밴드 중심 위도
  B_wood:     float,         # [kgC/m²] 목본
  organic:    float,         # [kgC/m²] 낙엽
  W_override: float | None,  # [0~1] 수분 직접 지정 (None=기본 프로파일)
)
```

---

## 규약 4: FireEngine provider 주입 시그니처

```python
# CookiieBrain/LatitudeBands 연결 시 이 시그니처로 주입:
temp_provider     (phi_deg, time_yr, env: FireEnvSnapshot) -> float  [K]
moisture_provider (phi_deg, time_yr, env: FireEnvSnapshot) -> float  [0~1]
fuel_provider     (phi_deg, time_yr, env: FireEnvSnapshot) -> (B_wood, organic)

# 사용 예:
engine = FireEngine(
    temp_provider     = lambda phi, t, env: my_latbands.get_T(phi),
    moisture_provider = lambda phi, t, env: my_latbands.get_W(phi),
    fuel_provider     = lambda phi, t, env: my_latbands.get_fuel(phi),
)
```

---

## 규약 5: ForgetEngine ↔ FireEngine 인터페이스 (인지-Gaia 브리지)

```
FireEngine  변수          ForgetEngine 변수          단위 대응
───────────────────────────────────────────────────────────────
O2_frac                ↔  memory_load_global         [0~1]
CO2_ppm (온실)          ↔  cortisol_global            [0~1]
F0 (태양상수)            ↔  atp_global                 [0~1]
time_yr (계절)           ↔  time_hr (일주기)            [yr → hr]
fire_risk              ↔  forget_risk                 [0~1]
fire_o2_sink_kgO2      ↔  atp_drain                  [플럭스]
global_fire_index()    ↔  global_cbi()               [0~1 지수]
```

동기화 분석:
```python
bridge = GaiaForgetBridge()
result = bridge.compare(fire_gfi, forget_cbi)
# result["sync_index"] → 1.0 = 행성-뇌 항상성 일치
```

---

## 규약 6: attractor 조건 (수식 불변)

모든 항상성 피드백은 이 조건을 만족해야 한다:

```
∂(d상태/dt)/∂상태 < 0   ← 음의 피드백 attractor

산불:  fire_sink   ∝ max(0, O2   - O2_th  )²  → O₂ 과잉 시 소비
망각:  forget_sink ∝ max(0, Load - Load_th )²  → 부하 과잉 시 소거
뉴런:  E_recovery  = g·(ATP-E) - γ·(E-E0)     → 에너지 이탈 시 복원
```

---

## 규약 7: 확장 시 밴드 수 변경

```python
# fire_engine.py 상단:
BAND_COUNT = 12   # → 36으로 변경 시 BandEco 리스트만 교체
# BAND_CENTERS_DEG 자동 재계산됨 (하드코딩 없음)
```

---

## 규약 8: 단위 요약표

| 변수 | 단위 | 출처 |
|------|------|------|
| fire_risk | [0~1] | 무차원 확률장 |
| fire_intensity | kgC/m²/yr | 로컬 탄소 플럭스 |
| fire_o2_sink_kgO2 | kgO2/m²/yr | 로컬 O₂ 플럭스 |
| fire_co2_source_kgC | kgC/m²/yr | 로컬 CO₂ 플럭스 |
| delta_O2_frac | mol/mol/yr | Gaia 모듈 변환 후 |
| global_fire_index | [0~1] | 면적 가중 평균 |
| forget_risk | [0~1] | 무차원 pruning 확률 |
| atp_drain | ATP/neuron/s | 로컬 에너지 플럭스 |

---

## 규약 9: 철학 — "no magic number 원칙"

```
fire_risk.py 안의 모든 상수 → 물리 관측값 기반 + 주석 필수
forget_engine.py 안의 모든 상수 → 신경과학 관측값 기반 + 주석 필수
예외: EPS = 1e-30 (수치 안정성 전용)
```

---

## 규약 10: 독립 실행 보장

```bash
# 이 두 명령이 항상 통과해야 한다 (외부 패키지 없이):
python demo.py          # GaiaFire 4시나리오 ALL PASS
python forget_demo.py   # ForgetEngine 4시나리오 ALL PASS
```

외부 의존성: **Python >= 3.8 표준 라이브러리만** (math, dataclasses, typing)

---

*GaiaFire Engine v1.1 — CookiieBrain Phase 7f*
*설계: 세차운동·토양·생태계·산불·망각 = 동일한 attractor 구조*
