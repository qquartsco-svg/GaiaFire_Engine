"""gaia_bridge_demo.py — GaiaBridge 검증 데모 (Phase 8)

V1: 정상 뇌 상태 → 낮은 스트레스 → 산불 압력 없음
V2: 과활성 뇌    → 스트레스 누적 → 산불 압력 증가
V3: 회복(저활성) → EMA 감쇠 → 압력 감소
V4: 요약 출력 + FireEngine 예측 비교

CookiieBrainEngine 없이 GlobalState 수동 시뮬레이션으로 브리지만 검증.
"""
import sys
import os
import math

# GaiaFire_Engine 폴더를 path에 추가 (독립 실행)
sys.path.insert(0, os.path.dirname(__file__))

from gaia_bridge import GaiaBridge, GaiaBridgeConfig, make_bridge

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def check(cond: bool, label: str) -> bool:
    s = PASS if cond else FAIL
    print(f"    {s}  {label}")
    return cond


def fake_state_vector(dim: int = 4, v_norm: float = 1.0):
    """가짜 state_vector (위치 dim/2 + 속도 dim/2)."""
    n = dim // 2
    pos = [0.0] * n
    # 속도 벡터: 크기 v_norm
    vel = [v_norm / math.sqrt(n)] * n
    return pos + vel


def run_gaia_bridge_demo():
    print("=" * 65)
    print("  GaiaBridge — 뉴런-Gaia 연결 브리지 검증")
    print("  CookiieBrainEngine → StressAccumulator → FireEngine")
    print("=" * 65)
    all_pass = True

    # ──────────────────────────────────────────────────────────────
    print("\n  [V1] 정상 뇌 → 낮은 스트레스 → 산불 압력 미발생")
    bridge_normal = make_bridge(
        dt=0.01,
        energy_ref=-50.0,
        energy_scale=100.0,
        velocity_scale=5.0,
        organ_every=50,
        planet_every=200,
    )

    # 정상: energy=-50 (기준값), v_norm=1.0 → atp≈0.5, heat 낮음
    last_normal = None
    for step in range(300):
        gs = bridge_normal.push(
            step=step,
            energy=-50.0 + (step % 10) * 0.5,   # 약간의 변동
            state_vector=fake_state_vector(4, v_norm=1.0),
        )
        last_normal = gs

    smry_n = bridge_normal.summary()
    print(f"    세포스트레스={smry_n['L1_cell_stress']:.3f}, "
          f"피로={smry_n['L2_fatigue']:.3f}, "
          f"행성압력={smry_n['L3_fire_pressure']:.4f}")

    ok1 = check(smry_n["L2_fatigue"] < 0.6,
                f"정상 피로 < 0.6 ({smry_n['L2_fatigue']:.3f})")
    all_pass = all_pass and ok1

    # ──────────────────────────────────────────────────────────────
    print("\n  [V2] 과활성 뇌 → 스트레스 누적 → 산불 압력 증가")
    bridge_over = make_bridge(
        dt=0.01,
        energy_ref=-50.0,
        energy_scale=100.0,
        velocity_scale=5.0,
        organ_every=50,
        planet_every=200,
    )

    # 과활성: energy=-200 (깊은 attractor → 고활성), v_norm=10
    # planet_every=200 → 5000스텝 = 5회 planet_update = 5yr 누적
    for step in range(5000):
        bridge_over.push(
            step=step,
            energy=-200.0,
            state_vector=fake_state_vector(4, v_norm=10.0),
        )

    smry_o = bridge_over.summary()
    print(f"    세포스트레스={smry_o['L1_cell_stress']:.3f}, "
          f"피로={smry_o['L2_fatigue']:.3f}, "
          f"행성압력={smry_o['L3_fire_pressure']:.4f}")
    print(f"    O2오프셋=+{smry_o['L3_O2_offset']:.4f}, "
          f"O2보정={smry_o['O2_frac_patched']:.4f}")

    ok2 = check(smry_o["L2_fatigue"] > smry_n["L2_fatigue"],
                f"과활성 피로({smry_o['L2_fatigue']:.3f}) > 정상({smry_n['L2_fatigue']:.3f})")
    ok3 = check(smry_o["L3_fire_pressure"] >= smry_n["L3_fire_pressure"],
                f"과활성 행성압력({smry_o['L3_fire_pressure']:.4f}) >= 정상({smry_n['L3_fire_pressure']:.4f})")
    all_pass = all_pass and ok2 and ok3

    # ──────────────────────────────────────────────────────────────
    print("\n  [V3] 회복(저활성) → 피로 낮음 확인")
    bridge_rest = make_bridge(
        dt=0.01,
        energy_ref=-50.0,
        energy_scale=100.0,
        velocity_scale=5.0,
        organ_every=50,
        planet_every=200,
    )

    # 저활성: energy=-10 (얕은 attractor → 저활성), v_norm=0.1
    for step in range(300):
        bridge_rest.push(
            step=step,
            energy=-10.0,
            state_vector=fake_state_vector(4, v_norm=0.1),
        )

    smry_r = bridge_rest.summary()
    print(f"    세포스트레스={smry_r['L1_cell_stress']:.3f}, "
          f"피로={smry_r['L2_fatigue']:.3f}")

    ok4 = check(smry_r["L2_fatigue"] < smry_o["L2_fatigue"],
                f"회복 피로({smry_r['L2_fatigue']:.3f}) < 과활성({smry_o['L2_fatigue']:.3f})")
    all_pass = all_pass and ok4

    # ──────────────────────────────────────────────────────────────
    print("\n  [V4] FireEngine 예측: 정상 vs 과활성 GFI 비교")
    fire_n = bridge_normal.predict_fire(time_yr=0.5)
    fire_o = bridge_over.predict_fire(time_yr=0.5)


    print(f"    정상  GFI: base={fire_n['gfi_base']:.4f}, patched={fire_n['gfi_patched']:.4f} "
          f"(Δ={fire_n['gfi_delta']:+.4f})")
    print(f"    과활성 GFI: base={fire_o['gfi_base']:.4f}, patched={fire_o['gfi_patched']:.4f} "
          f"(Δ={fire_o['gfi_delta']:+.4f})")
    print(f"    O2오프셋: 정상={fire_n['O2_offset']:.4f}, 과활성={fire_o['O2_offset']:.4f}")

    ok5 = check(fire_o["gfi_patched"] >= fire_n["gfi_patched"],
                f"과활성 GFI({fire_o['gfi_patched']:.4f}) >= 정상({fire_n['gfi_patched']:.4f})")
    all_pass = all_pass and ok5

    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  결과: {'ALL PASS ✅' if all_pass else 'SOME FAIL ❌'}")
    print("=" * 65)

    # 파이프라인 요약
    print("\n  ── Phase 8 파이프라인 요약 ──────────────────────────────")
    print("  CookiiiBrain (물리)    Gaia (지구 산불)")
    print("  ─────────────────────────────────────────────────────────")
    print(f"  정상:  cell={smry_n['L1_cell_stress']:.3f}"
          f" → fatigue={smry_n['L2_fatigue']:.3f}"
          f" → fire_p={smry_n['L3_fire_pressure']:.4f}"
          f" → GFI={fire_n['gfi_patched']:.4f}")
    print(f"  과활성: cell={smry_o['L1_cell_stress']:.3f}"
          f" → fatigue={smry_o['L2_fatigue']:.3f}"
          f" → fire_p={smry_o['L3_fire_pressure']:.4f}"
          f" → GFI={fire_o['gfi_patched']:.4f}")
    print(f"\n  번역 완료: Hopfield 에너지 → 뉴런 ATP → 행성 O2 오프셋"
          f" +{smry_o['L3_O2_offset']:.4f} mol/mol")

    return all_pass


if __name__ == "__main__":
    success = run_gaia_bridge_demo()
    sys.exit(0 if success else 1)
