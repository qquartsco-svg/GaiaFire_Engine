"""forget_demo.py — ForgetEngine 4시나리오 검증 데모

산불 ↔ 망각 수식 동일성 + 행성-뇌 항상성 브리지 검증

V1: 정상 부하(0.5) → forget_risk 낮음 (pruning 없음)
V2: 과부하(0.8) + 스트레스 → forget_risk 높음, hot spot 창발
V3: 수면 중(새벽 3시) → 각성보다 pruning↑ (수면 청소)
V4: GaiaForgetBridge — O2_frac=0.28(과잉) → 행성-뇌 동기화 확인
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

try:
    from forget_engine import (
        ForgetEngine, CognitiveBrainSnapshot, GaiaForgetBridge,
    )
    from fire_engine import FireEngine, FireEnvSnapshot
except ImportError as e:
    print(f"Import 오류: {e}")
    sys.exit(1)

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def check(condition, label):
    status = PASS if condition else FAIL
    print(f"    {status}  {label}")
    return condition


def run_forget_demo():
    print("=" * 65)
    print("  ForgetEngine — 인지 망각 항상성 검증 데모")
    print("  산불 ODE ↔ 망각 ODE 수식 동일성 확인")
    print("=" * 65)

    engine = ForgetEngine()
    all_pass = True

    # ──────────────────────────────────────────────────────────────
    print("\n  [V1] 정상 부하 → pruning 없음")
    brain_normal = CognitiveBrainSnapshot(
        memory_load_global=0.4,   # 부하 낮음 (임계 0.3 근처)
        cortisol_global=0.2,      # 스트레스 낮음
        atp_global=0.9,           # ATP 충분
        time_hr=14.0,             # 오후 2시 (각성)
    )
    r_normal = engine.predict(brain_normal)
    cbi_normal = engine.global_cbi(r_normal)
    hotspots_normal = [r for r in r_normal if r.forget_risk > engine.HOTSPOT_THRESHOLD]

    print(f"    부하={brain_normal.memory_load_global}, "
          f"코르티솔={brain_normal.cortisol_global}, ATP={brain_normal.atp_global}")
    print(f"    전뇌 CBI={cbi_normal:.4f}, hot spot 수={len(hotspots_normal)}")
    ok1 = check(cbi_normal < 0.05, "정상 부하 → CBI < 0.05")
    ok2 = check(len(hotspots_normal) == 0, "hot spot 없음")
    all_pass = all_pass and ok1 and ok2

    # ──────────────────────────────────────────────────────────────
    print("\n  [V2] 과부하 + 스트레스 → pruning hot spot 창발")
    brain_stress = CognitiveBrainSnapshot(
        memory_load_global=0.85,  # 과부하 (임계 0.7 초과)
        cortisol_global=0.6,      # 중간-높은 스트레스
        atp_global=0.4,           # ATP 고갈
        time_hr=22.0,             # 저녁 10시 (수면 직전)
    )
    r_stress = engine.predict(brain_stress)
    cbi_stress = engine.global_cbi(r_stress)
    hotspots_stress = [r for r in r_stress if r.forget_risk > engine.HOTSPOT_THRESHOLD]
    hp_stress = engine.homeostasis_pressure(r_stress)

    print(f"    부하={brain_stress.memory_load_global}, "
          f"코르티솔={brain_stress.cortisol_global}, ATP={brain_stress.atp_global}")
    print(f"    전뇌 CBI={cbi_stress:.4f}, hot spot 수={len(hotspots_stress)}")
    print(f"    주요 pruning 영역: {hp_stress['dominant_region']}")

    ok3 = check(cbi_stress > cbi_normal, f"과부하 CBI({cbi_stress:.4f}) > 정상 CBI({cbi_normal:.4f})")
    ok4 = check(len(hotspots_stress) > 0, "pruning hot spot 창발")
    all_pass = all_pass and ok3 and ok4
    engine.print_map(r_stress, "과부하 + 스트레스 상태")

    # ──────────────────────────────────────────────────────────────
    print("\n  [V3] 수면(새벽 3시) vs 각성(오후 2시) 계절성")
    brain_base = CognitiveBrainSnapshot(
        memory_load_global=0.65,
        cortisol_global=0.4,
        atp_global=0.6,
        time_hr=14.0,   # 각성
    )
    brain_sleep = CognitiveBrainSnapshot(
        memory_load_global=0.65,
        cortisol_global=0.4,
        atp_global=0.6,
        time_hr=3.0,    # 수면 (새벽 3시 = pruning 최대)
    )
    r_awake = engine.predict(brain_base)
    r_sleep  = engine.predict(brain_sleep)
    cbi_awake = engine.global_cbi(r_awake)
    cbi_sleep = engine.global_cbi(r_sleep)

    print(f"    각성(14시) CBI={cbi_awake:.4f}")
    print(f"    수면(03시) CBI={cbi_sleep:.4f}")
    ok5 = check(cbi_sleep > cbi_awake,
                f"수면 CBI({cbi_sleep:.4f}) > 각성 CBI({cbi_awake:.4f})  ← 수면 청소 창발")
    all_pass = all_pass and ok5

    # ──────────────────────────────────────────────────────────────
    print("\n  [V4] GaiaForgetBridge — 행성 O₂ 과잉 → 뇌 부하 매핑 + 동기화")
    bridge = GaiaForgetBridge()

    # 행성: O₂=28% 과잉
    fire_engine = FireEngine()
    env_high = FireEnvSnapshot(O2_frac=0.28, time_yr=0.5)
    fire_results = fire_engine.predict(env_high)
    gfi = fire_engine.global_fire_index(fire_results)

    # 행성 상태 → 뇌 상태 매핑
    brain_mapped = bridge.planet_to_brain(
        O2_frac=0.28, CO2_ppm=500.0, time_yr=0.5
    )
    forget_results = engine.predict(brain_mapped)
    cbi = engine.global_cbi(forget_results)

    sync = bridge.compare(gfi, cbi)

    print(f"    행성 O₂=28%, GFI={gfi:.4f}")
    print(f"    매핑된 뇌 부하={brain_mapped.memory_load_global:.2f}, "
          f"코르티솔={brain_mapped.cortisol_global:.2f}")
    print(f"    뇌 CBI={cbi:.4f}")
    print(f"    동기화 지수={sync['sync_index']:.3f}  ({sync['interpretation']})")

    ok6 = check(gfi > 0, f"O₂=28% → 산불 GFI={gfi:.4f} > 0")
    ok7 = check(brain_mapped.memory_load_global > 0.5,
                f"O₂=28% → 인지 부하={brain_mapped.memory_load_global:.2f} > 0.5")
    ok8 = check(cbi > 0, f"인지 CBI={cbi:.4f} > 0")
    all_pass = all_pass and ok6 and ok7 and ok8

    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  결과: {'ALL PASS ✅' if all_pass else 'SOME FAIL ❌'}")
    print("=" * 65)

    print("\n  ── 수식 동일성 요약 ──────────────────────────────────")
    print("  행성 (GaiaFire)              인지 (ForgetEngine)")
    print("  ─────────────────────────────────────────────────────")
    print(f"  O₂ 과잉 임계 (25%)     ↔   부하 임계 (70%)")
    print(f"  fire_sink ∝ max(0,O2-th)²  forget_sink ∝ max(0,L-th)²")
    print(f"  산불 hot spot (위도)   ↔   pruning hot spot (뇌 영역)")
    print(f"  전지구 GFI = {gfi:.4f}      ↔   전뇌 CBI = {cbi:.4f}")
    print(f"  북반구 여름 건기       ↔   새벽 3시 수면 청소")
    print(f"  biomass 소각           ↔   시냅스 가지치기")
    print(f"  재생을 위한 파괴       ↔   새 학습을 위한 망각")
    print("  둘 다: ∂(d상태/dt)/∂상태 < 0  ← 음의 피드백 attractor")

    return all_pass


if __name__ == "__main__":
    success = run_forget_demo()
    sys.exit(0 if success else 1)
