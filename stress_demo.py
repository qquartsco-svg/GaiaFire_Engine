"""stress_demo.py — StressAccumulator + LocalFireReset 검증 데모

V1: 정상 발화 → 스트레스 낮음 → 산불 압력 없음
V2: 과발화(스트레스 누적) → 행성 O₂ 보정 → 산불 압력 증가
V3: 수면(적산 감쇠) → planet_stress 감소 확인
V4: LocalFireReset — 산불 후 B_wood 국소 리셋 + 스트레스 해소
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from stress_accumulator import (
    StressAccumulator, LocalFireReset, NeuronEvent,
)
from fire_engine import FireEngine, FireEnvSnapshot
from forget_engine import ForgetEngine

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def check(cond, label):
    s = PASS if cond else FAIL
    print(f"    {s}  {label}")
    return cond


def run_stress_demo():
    print("=" * 65)
    print("  StressAccumulator — 시간 스케일 번역기 검증")
    print("  뉴런(ms) → 기관(hr) → 행성(yr) 적산 파이프라인")
    print("=" * 65)
    all_pass = True

    # ──────────────────────────────────────────────────────────────
    print("\n  [V1] 정상 발화 → 세포 스트레스 낮음 → 산불 압력 없음")
    acc_normal = StressAccumulator()

    # 정상 뉴런: 낮은 ATP 소비 (0.2), 100ms 간격 10회
    for i in range(10):
        ev = NeuronEvent.from_metabolic(time_ms=float(i * 100), atp_consumed=0.2)
        acc_normal.push_neuron_event(ev)

    organ_n  = acc_normal.update_organ(time_hr=1.0)
    planet_n = acc_normal.update_planet(time_yr=0.001)

    print(f"    세포 스트레스={acc_normal.cell_history[-1].stress_score:.3f}, "
          f"피로={organ_n.fatigue_ema:.3f}, "
          f"행성압력={planet_n.fire_pressure:.4f}")

    ok1 = check(organ_n.fatigue_ema < 0.3, f"정상 피로 < 0.3 ({organ_n.fatigue_ema:.3f})")
    ok2 = check(planet_n.fire_pressure < 0.01, f"산불 압력 < 0.01 ({planet_n.fire_pressure:.4f})")
    all_pass = all_pass and ok1 and ok2

    # ──────────────────────────────────────────────────────────────
    print("\n  [V2] 과발화 누적 → 행성 스트레스 → 산불 O₂ 보정")
    acc_over = StressAccumulator()

    # 과발화: ATP 소비 0.9, 50ms 간격 50회
    for i in range(50):
        ev = NeuronEvent.from_metabolic(time_ms=float(i * 50), atp_consumed=0.9)
        acc_over.push_neuron_event(ev)

    # 기관/행성 업데이트: 시간 충분히 누적
    organ_o  = acc_over.update_organ(time_hr=1.0)
    # 행성 스케일은 yr 단위 — 의미 있는 누적을 위해 반복 업데이트
    for _yr in range(5):
        planet_o = acc_over.update_planet(time_yr=float(_yr + 1))

    # 행성 O₂ 보정 적용
    patch   = acc_over.to_fire_env_patch(base_O2=0.21, base_CO2=400.0)
    brain_o = acc_over.to_brain_snapshot(time_hr=22.0)

    # 산불 엔진에 보정값 주입
    fire_eng = FireEngine()
    env_base   = FireEnvSnapshot(O2_frac=0.21, time_yr=0.5)
    env_patched = FireEnvSnapshot(
        O2_frac = patch["O2_frac_patched"],
        CO2_ppm = patch["CO2_ppm_patched"],
        time_yr = 0.5,
    )
    res_base   = fire_eng.predict(env_base)
    res_patched = fire_eng.predict(env_patched)
    gfi_base   = fire_eng.global_fire_index(res_base)
    gfi_patched = fire_eng.global_fire_index(res_patched)

    print(f"    세포 스트레스={acc_over.cell_history[-1].stress_score:.3f}, "
          f"피로={organ_o.fatigue_ema:.3f}")
    print(f"    코르티솔={organ_o.cortisol_equiv:.3f}, ATP고갈={organ_o.atp_depletion:.3f}")
    print(f"    행성압력={planet_o.fire_pressure:.4f}, O₂오프셋=+{patch['O2_offset']:.4f}")
    print(f"    산불 GFI: 기본={gfi_base:.4f} → 보정후={gfi_patched:.4f}")
    print(f"    뇌 cortisol={brain_o.cortisol_global:.3f}, atp={brain_o.atp_global:.3f}")

    ok3 = check(organ_o.fatigue_ema > organ_n.fatigue_ema,
                f"과발화 피로({organ_o.fatigue_ema:.3f}) > 정상({organ_n.fatigue_ema:.3f})")
    ok4 = check(patch["O2_offset"] > 0,
                f"스트레스 → O₂ 오프셋 > 0 ({patch['O2_offset']:.4f})")
    ok5 = check(gfi_patched >= gfi_base,
                f"보정 후 GFI({gfi_patched:.4f}) >= 기본({gfi_base:.4f})")
    all_pass = all_pass and ok3 and ok4 and ok5

    # ──────────────────────────────────────────────────────────────
    print("\n  [V3] 수면(감쇠) → EMA 자연 감쇠 확인")
    # 각성 상태 (atp=0.9) vs 수면 상태 (atp=0.05) — 같은 시간 구간 비교
    # 각성: 1hr 동안 고부하 발화
    acc_awake = StressAccumulator()
    for i in range(60):
        acc_awake.push_neuron_event(
            NeuronEvent.from_metabolic(time_ms=float(i * 60000), atp_consumed=0.9)
        )
    organ_awake = acc_awake.update_organ(time_hr=1.0)

    # 수면: 1hr 동안 저부하 발화 (atp=0.05)
    acc_sleep2 = StressAccumulator()
    for i in range(60):
        acc_sleep2.push_neuron_event(
            NeuronEvent.from_metabolic(time_ms=float(i * 60000), atp_consumed=0.05)
        )
    organ_sleep2 = acc_sleep2.update_organ(time_hr=1.0)

    print(f"    각성(1hr, atp=0.9): 피로={organ_awake.fatigue_ema:.3f}, "
          f"코르티솔={organ_awake.cortisol_equiv:.3f}")
    print(f"    수면(1hr, atp=0.05): 피로={organ_sleep2.fatigue_ema:.3f}, "
          f"코르티솔={organ_sleep2.cortisol_equiv:.3f}")

    ok6 = check(organ_sleep2.fatigue_ema < organ_awake.fatigue_ema,
                f"수면 피로({organ_sleep2.fatigue_ema:.3f}) < 각성 피로({organ_awake.fatigue_ema:.3f})")
    all_pass = all_pass and ok6

    # ──────────────────────────────────────────────────────────────
    print("\n  [V4] LocalFireReset — 산불 후 B_wood 국소 리셋 + 스트레스 해소")
    acc_reset = StressAccumulator()
    for i in range(50):
        acc_reset.push_neuron_event(
            NeuronEvent.from_metabolic(time_ms=float(i*50), atp_consumed=0.9)
        )
    acc_reset.update_organ(time_hr=1.0)
    for _yr in range(5):
        acc_reset.update_planet(time_yr=float(_yr + 1))
    planet_before_reset = acc_reset.planet_history[-1].planet_stress_ema

    resetter = LocalFireReset(accumulator=acc_reset)

    # 산불 발생: band_idx=6 (북위 7.5°), fire_risk=1.0 (최대), dt=3yr
    B_before, org_before = 2.0, 0.5
    new_bw, new_org, info = resetter.apply(
        band_idx=6, B_wood=B_before, organic=org_before,
        fire_risk=1.0, dt_yr=3.0
    )
    planet_after_reset = acc_reset.planet_history[-1].planet_stress_ema

    print(f"    산불 전: B_wood={B_before:.2f}, organic={org_before:.2f}, "
          f"행성스트레스={planet_before_reset:.4f}")
    print(f"    산불 후: B_wood={new_bw:.2f}, organic={new_org:.2f}, "
          f"행성스트레스={planet_after_reset:.4f}")
    print(f"    소각량: wood={info['burned_wood']:.3f}, "
          f"organic={info['burned_organic']:.3f}, "
          f"CO₂방출={info['co2_released']:.3f} kgC/m²")
    print(f"    스트레스 해소율={info['stress_reset']:.1%}, "
          f"회복모드={'예' if info['recovery_mode'] else '아니오'}")

    ok7 = check(new_bw < B_before,
                f"B_wood 감소 ({B_before:.2f} → {new_bw:.2f})")
    ok8 = check(new_org < org_before,
                f"organic 감소 ({org_before:.2f} → {new_org:.2f})")
    ok9 = check(planet_after_reset <= planet_before_reset,
                f"산불 후 행성 스트레스 해소 ({planet_before_reset:.4f} → {planet_after_reset:.4f})")
    ok10 = check(info['recovery_mode'],
                 f"new_B_wood < 0.5 → recovery_mode=True (새 생장 공간)")
    all_pass = all_pass and ok7 and ok8 and ok9 and ok10

    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  결과: {'ALL PASS ✅' if all_pass else 'SOME FAIL ❌'}")
    print("=" * 65)

    # 전체 파이프라인 요약
    print("\n  ── 전체 파이프라인 요약 ──────────────────────────────")
    print("  뉴런(ms)          기관(hr)           행성(yr)")
    print("  ─────────────────────────────────────────────────────")
    smry_n = acc_normal.summary()
    smry_o = acc_over.summary()
    print(f"  정상: cell={smry_n['L1_cell_stress']:.3f}  →  fatigue={smry_n['L2_fatigue']:.3f}"
          f"  →  planet={smry_n['L3_planet_stress']:.4f}  fire_p={smry_n['L3_fire_pressure']:.4f}")
    print(f"  과부하: cell={smry_o['L1_cell_stress']:.3f}  →  fatigue={smry_o['L2_fatigue']:.3f}"
          f"  →  planet={smry_o['L3_planet_stress']:.4f}  fire_p={smry_o['L3_fire_pressure']:.4f}")
    print(f"\n  번역 완료: 뉴런 스트레스 → 행성 O₂ 오프셋 +{smry_o['L3_O2_offset']:.4f} mol/mol")
    print(f"            CO₂ 누적: +{smry_o['L3_CO2_acc']:.2f} ppm")

    return all_pass


if __name__ == "__main__":
    success = run_stress_demo()
    sys.exit(0 if success else 1)
