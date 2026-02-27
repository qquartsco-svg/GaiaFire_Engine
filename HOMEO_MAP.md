# Homeostasis Map — 미시(뉴런) ↔ 거시(행성) 변수 매핑

> "같은 수학, 다른 스케일" — 동일한 attractor 구조가 ms에서 yr까지 반복된다

---

## 1. 변수 매핑 테이블 (완전판)

| 레벨 | 뉴런/인지 변수 | 단위 | 행성/생태계 변수 | 단위 | 변환 함수 |
|------|--------------|------|----------------|------|---------|
| 상태 | membrane_E | mV | O₂_frac | mol/mol | normalize(E, -90, 0) |
| 상태 | ATP | [0~1] | Solar_flux | W/m² | ATP × F0 |
| 상태 | Ca²⁺ | μM | CO₂_ppm | ppm | Ca × 100 |
| 상태 | memory_load | [0~1] | O₂_excess | mol/mol | load × 0.14 + 0.21 |
| 입력 | co2_pulse | μmol/s | GPP | kg C/m²/yr | ×scale |
| 입력 | heat_pulse | mW | T_surface | K | T₀ + heat×0.01 |
| 피드백 | cortisol | [0~1] | CO₂_ppm_offset | ppm | cort × 200 |
| 피드백 | atp_drain | [0~1] | fire_o2_sink | kgO2/m²/yr | drain × K |
| 출력 | forget_rate | synapses/s | fire_intensity | kgC/m²/yr | ×scale |
| 출력 | pruning_area | region_id | fire_hotspot | phi_deg | band_map |
| 지수 | CBI | [0~1] | GFI | [0~1] | 직접 대응 |
| 압력 | homeostasis_pressure | [0~1] | homeostasis_pressure | [0~1] | 동일 함수 |

---

## 2. 시간 스케일 변환 (StressAccumulator 3단계)

```
뉴런 이벤트 (ms)
    ↓ EMA  τ=0.1s
세포 스트레스 (s)      ← CellStressState
    ↓ EMA  τ=3600s
기관 피로 (hr)         ← OrganFatigueState
    ↓ EMA  τ=3.15e7s
행성 스트레스 (yr)     ← PlanetStressIndex
    ↓ patch
FireEnvSnapshot.O2_frac += O2_stress_offset
```

시정수 의미:
- τ_cell = 0.1s → 뉴런 회복 시간 (100ms)
- τ_organ = 3600s → 코르티솔 반감기 (1hr)
- τ_planet = 3.15e7s → 생태계 회복 (1yr)

---

## 3. attractor 수식 동일성

모든 레벨에서 동일한 비선형 음의 피드백:

```
Level 1 (세포):
  excess_cell   = K_C × max(0, stress   - S_th_cell  )²

Level 2 (기관):
  excess_organ  = K_O × max(0, fatigue  - S_th_organ )²
  pruning_pressure = excess_organ   → ForgetEngine 입력

Level 3 (행성):
  excess_planet = K_P × max(0, planet  - S_th_planet)²
  fire_pressure = excess_planet     → FireEngine O2 보정

행성 직접:
  fire_sink     = K_F × max(0, O2     - O2_th      )²

뇌 직접:
  forget_sink   = K_G × max(0, Load   - Load_th    )²

────────────────────────────────────────────────────
모두: f(x) = K × max(0, x - x_th)²
      ∂(dx/dt)/∂x < 0  ← attractor 조건 (항상성)
```

---

## 4. 스트레스 → 산불 연결 경로

```
뉴런 발화 과다
    │ co2_pulse ↑, heat_pulse ↑
    ▼
StressAccumulator.push_neuron_event()
    │ EMA 적산
    ▼
CellStressState.stress_score ↑
    │ τ=0.1s 감쇠
    ▼
OrganFatigueState.cortisol_equiv ↑  →  ForgetEngine (망각↑)
                  .atp_depletion ↑
                  .pruning_pressure ↑
    │ τ=1hr 감쇠
    ▼
PlanetStressIndex.fire_pressure ↑
                  .O2_stress_offset ↑
    │
    ▼
FireEnvSnapshot.O2_frac += O2_stress_offset  →  FireEngine (산불↑)
                                                  LocalFireReset (B_wood↓)
    │
    ▼
산불 발생 → CO₂ 방출 → 행성 스트레스 부분 해소
            B_wood 국소 리셋 → 새 생장 공간
```

---

## 5. 망각 후 회복 메커니즘 (LocalFireReset)

```
산불(망각) 발생
    │ fire_risk > 0.1
    ▼
LocalFireReset.apply()
    │ B_wood  -= burned_wood    (기억 소거)
    │ organic -= burned_organic (잡음 제거)
    │ planet_ema  *= 0.7        (스트레스 해소 30%)
    │ co2_acc *= 0.85           (CO₂ 누적 해소)
    ▼
new_B_wood < 0.5 → recovery_mode = True
    │
    ▼
pioneer 종 정착 → B_wood 서서히 증가  (새 학습 시작)
```

---

## 6. 동기화 지수 (GaiaForgetBridge.sync_index)

```
sync_index = 1.0 - |GFI - CBI|

GFI (Global Fire Index)     = fire_engine.global_fire_index()
CBI (Cognitive Burden Index) = forget_engine.global_cbi()

sync_index > 0.8 → 행성-뇌 항상성 일치 (정상)
sync_index < 0.5 → 두 시스템 부하 불균형 (이상)

실용적 의미:
  sync 높음: 뇌가 스트레스 받는 만큼 지구도 산불 압력 받음 (균형)
  sync 낮음: 뇌만 과부하 or 지구만 과부하 (불균형 → 보정 필요)
```

---

## 7. 질소/영양 루프 (미구현 — 확장 예약)

현재 시스템: C, O₂ 루프만 구현
부족한 것: N (질소), P (인) 순환

향후 추가 방향:
```
N_soil [kg N/m²]  → 광합성 효율 보정
  dN/dt = N_input (빗물, 질소 고정) - N_uptake (식물 흡수) - N_loss (용탈)

뉴런 대응:
  glutamate, GABA (질소 함유 신경전달물질)
  → N_soil ↔ neurotransmitter_pool
```

구현 우선순위: C/O₂ 항상성 완전 검증 후 추가

---

## 8. 파일-모듈 구조 (v1.2)

```
GaiaFire_Engine/
  fire_risk.py          로컬 플럭스 ODE          [완성]
  fire_engine.py        전지구 예측 + provider   [완성]
  forget_engine.py      인지 망각 ODE            [완성]
  stress_accumulator.py 시간 스케일 번역기        [완성 v1.2]
    └ StressAccumulator  3단계 적산 파이프라인
    └ LocalFireReset     국소 산불/망각 리셋
  __init__.py           공개 API                 [완성]
  INTERFACE_CONTRACT.md 10줄 규약                [완성]
  HOMEO_MAP.md          이 파일 — 변수 매핑      [완성 v1.2]
  demo.py               산불 4시나리오
  forget_demo.py        망각 4시나리오
  stress_demo.py        적산기 4시나리오          [추가 예정]
```

---

*GaiaFire Engine v1.2 — CookiieBrain Phase 7f*
*"뉴런이 스트레스 받으면 지구 어딘가에 불이 난다" — 번역기 완성*
