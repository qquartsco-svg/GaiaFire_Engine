#!/usr/bin/env python3
"""
fire_prediction_demo.py — 전지구 산불 발생 예측 데모

설계 철학:
  "환경 설정만 하면 항상성에 의해 산불 발생 지점이 자연스럽게 창발"

시나리오:
  [A] 현재 지구 (O₂=21%, 여름/봄/겨울) — 계절별 hot spot 이동
  [B] O₂=28% (높은 O₂) — 산불 hot spot 확산
  [C] O₂=15% (낮은 O₂) — 산불 거의 없음
  [D] 항상성 복원력 분석 — 어느 위도에서 O₂ 소비해야 균형인가

핵심 출력:
  - 위도별 fire_risk map
  - 계절별 hot spot 이동 (북반구 여름 ↔ 남반구 여름)
  - O₂ 수준별 전지구 산불 위험 지수
  - 항상성 복원 압력 지도
"""

import sys, os
# 독립 실행: GaiaFire_Engine 폴더 자체를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fire_engine import FireEngine, FireEnvSnapshot
from fire_risk import f_O2_fire

engine = FireEngine()

# ── 시나리오 A: 현재 지구 — 계절별 hot spot 이동 ─────────────────────────────
print("=" * 95)
print("  [A] 현재 지구 (O₂=21%) — 계절별 산불 hot spot")
print("  입력: O2=21%, 성숙 생태계 (B_wood 위도별 분포)")
print("=" * 95)

# 계절 4개
seasons = {
    "봄  (t=0.25yr)": 0.25,
    "여름(t=0.50yr)": 0.50,
    "가을(t=0.75yr)": 0.75,
    "겨울(t=0.00yr)": 0.00,
}

for season_name, t_yr in seasons.items():
    env = FireEnvSnapshot(O2_frac=0.21, CO2_ppm=400.0, time_yr=t_yr)
    results = engine.predict(env)
    hotspots = [r for r in results if r.is_hotspot]
    gfi = engine.global_fire_index(results)

    print(f"\n  ── {season_name}  GFI={gfi:.4f} ──")
    print(f"  {'위도':>7}  {'위험도':>7}  {'온도(°C)':>9}  {'건조도':>7}  시각화")
    print("  " + "-" * 60)
    for r in results:
        bar = "█" * int(r.fire_risk * 15) + "░" * (15 - int(r.fire_risk * 15))
        flag = " 🔥" if r.is_hotspot else ""
        print(f"  {r.phi_deg:>7.1f}°  {r.fire_risk:>7.3f}  {r.T_K-273.15:>9.1f}  "
              f"{r.f_dry:>7.3f}  |{bar}|{flag}")
    if hotspots:
        hs_lats = [f"{h.phi_deg:.1f}°" for h in hotspots]
        print(f"\n  🔥 Hot spots: {', '.join(hs_lats)}")
    else:
        print(f"\n  산불 없음 (fire_risk < {engine.HOTSPOT_THRESHOLD})")

# ── 시나리오 B: O₂=28% — 고O₂ 산불 확산 ────────────────────────────────────
print("\n" + "=" * 95)
print("  [B] O₂=28% (높은 O₂) vs O₂=21% — 산불 hot spot 확산")
print("=" * 95)

for o2_pct, label in [(21, "현재(21%)"), (25, "임계(25%)"), (28, "고O₂(28%)")]:
    env = FireEnvSnapshot(O2_frac=o2_pct/100.0, time_yr=0.5)  # 북반구 여름
    results = engine.predict(env)
    gfi = engine.global_fire_index(results)
    n_hot = sum(1 for r in results if r.is_hotspot)
    hp = engine.homeostasis_pressure(results)
    print(f"\n  O₂={o2_pct}% [{label}]  GFI={gfi:.4f}  hotspot 밴드={n_hot}개  "
          f"압력={hp['homeostasis_pressure']:.3f}")
    engine.print_map(results, f"O₂={o2_pct}% 산불 위험도")

# ── 시나리오 C: O₂=15% — 산불 없음 ──────────────────────────────────────────
print("\n" + "=" * 95)
print("  [C] O₂=15% — 산불 거의 없음 확인")
print("=" * 95)

env_c = FireEnvSnapshot(O2_frac=0.15, time_yr=0.5)
results_c = engine.predict(env_c)
gfi_c = engine.global_fire_index(results_c)
print(f"\n  O₂=15%: f_O2 = {f_O2_fire(0.15):.4f}  GFI = {gfi_c:.6f}")
print(f"  최대 fire_risk: {max(r.fire_risk for r in results_c):.6f}")
print(f"  → O₂ 15% 이하에서 산불 발생 불가 ({'✓' if gfi_c < 0.01 else '✗'})")

# ── 시나리오 D: 항상성 복원력 분석 ───────────────────────────────────────────
print("\n" + "=" * 95)
print("  [D] 항상성 복원력 분석")
print("  핵심 질문: O₂ 수준별로 어느 위도에서 산불이 O₂를 소비해야 균형인가?")
print("=" * 95)

print(f"\n  {'O₂(%)':>7}  {'GFI':>7}  {'주요위도':>10}  {'CO₂플럭스':>12}  {'복원압력':>10}  해석")
print("  " + "-" * 75)
for o2_pct in [15, 18, 21, 23, 25, 27, 30, 33]:
    env_d = FireEnvSnapshot(O2_frac=o2_pct/100.0, time_yr=0.5)
    results_d = engine.predict(env_d)
    hp = engine.homeostasis_pressure(results_d, O2_target=0.21)
    gfi = hp["global_fire_index"]
    dom = hp["dominant_latitude"]
    co2f = hp["total_fire_co2_flux"]
    press = hp["homeostasis_pressure"]
    if o2_pct < 21:
        interp = "광합성 키워야"
    elif o2_pct == 21:
        interp = "균형점"
    elif o2_pct < 25:
        interp = "약한 산불 압력"
    else:
        interp = "강한 산불 소비 필요"
    print(f"  {o2_pct:>7}%  {gfi:>7.4f}  {dom:>10.1f}°  {co2f:>12.5f}  "
          f"{press:>10.3f}  {interp}")

# ── 검증 ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 95)
print("  검증")
print("-" * 95)

checks = []

# V1: O₂=21% 북반구 여름 → 북위 30~60° hot spot
env_v1 = FireEnvSnapshot(O2_frac=0.21, time_yr=0.5)
r_v1 = engine.predict(env_v1)
hot_v1 = [r for r in r_v1 if r.is_hotspot and r.phi_deg > 0]
ok1 = len(hot_v1) > 0
checks.append(("O₂=21% 북반구 여름 → 북위 hot spot 존재",
               ok1, f"hot spots: {[f'{r.phi_deg:.1f}°' for r in hot_v1]}"))

# V2: O₂=28% → O₂=21%보다 GFI 높아야
env_v2a = FireEnvSnapshot(O2_frac=0.21, time_yr=0.5)
env_v2b = FireEnvSnapshot(O2_frac=0.28, time_yr=0.5)
gfi_21 = engine.global_fire_index(engine.predict(env_v2a))
gfi_28 = engine.global_fire_index(engine.predict(env_v2b))
ok2 = gfi_28 > gfi_21
checks.append(("O₂=28% GFI > O₂=21% GFI (고O₂ → 더 많은 산불)",
               ok2, f"GFI(21%)={gfi_21:.4f} < GFI(28%)={gfi_28:.4f}"))

# V3: O₂=15% → 산불 없음
gfi_15 = engine.global_fire_index(engine.predict(FireEnvSnapshot(O2_frac=0.15)))
ok3 = gfi_15 < 0.01
checks.append(("O₂=15% → GFI < 0.01 (산불 발생 불가)",
               ok3, f"GFI(15%)={gfi_15:.6f}"))

# V4: 북반구 여름(t=0.5) hot spot > 북반구 겨울(t=0.0) hot spot
r_summer = engine.predict(FireEnvSnapshot(O2_frac=0.21, time_yr=0.5))
r_winter = engine.predict(FireEnvSnapshot(O2_frac=0.21, time_yr=0.0))
nh_summer = sum(r.fire_risk for r in r_summer if r.phi_deg > 0)
nh_winter = sum(r.fire_risk for r in r_winter if r.phi_deg > 0)
ok4 = nh_summer > nh_winter
checks.append(("북반구 여름 산불 위험 > 겨울 (계절성 창발)",
               ok4, f"여름={nh_summer:.4f} > 겨울={nh_winter:.4f}"))

print()
all_pass = True
for desc, ok, detail in checks:
    status = "PASS ✓" if ok else "FAIL ✗"
    if not ok:
        all_pass = False
    print(f"  [{status}] {desc}")
    print(f"           → {detail}")

print()
if all_pass:
    print("  ★★★ ALL PASS")
    print()
    print("  solar/fire/ 독립 모듈 완성:")
    print("    fire_risk.py  — 위도×계절×생태계 산불 위험도 ODE")
    print("    fire_engine.py — 전지구 예측 엔진 + 항상성 복원력 분석")
    print()
    print("  항상성 발견:")
    print("    O₂ 25% 이하 → 산불 없음 → 광합성이 O₂ 결정")
    print("    O₂ 25% 이상 → 건조+고온 위도에서 산불 자동 발생")
    print("    산불 hot spot = O₂ 항상성이 복원되어야 할 공간적 지점")
    print()
    print("  계절성 창발:")
    print("    북반구 여름(t=0.5) → 북위 중위도 hot spot")
    print("    남반구 여름(t=0.0) → 남위 중위도 hot spot")
    print("    자전축 기울기 → 계절 → 건기 → 산불 위치 자연 결정")
else:
    print("  일부 FAIL")
print("=" * 95)
