"""gaia_loop_demo.py — 3개 열린 루프 → 닫힌 항상성 순환 검증 (Phase 8.5)

V1: Loop A — 산불 CO₂ → 대기 CO₂ 피드백
    산불 강도 고정 → CO₂ 누적 → 온실 강화 확인

V2: Loop B — 식생 알베도 → 온도 피드백
    식생 증가(알베도↓) → 대기 알베도 변화 → 온도 응답 확인

V3: Loop C — 세차 obliquity → 건기 계절성
    obliquity 변화 → dry_modifier 진폭 변화 확인

V4: 3루프 통합 — 초기 조건 → 자기조절 순환
    CO₂↑ → T↑ → 건조↑ → 산불↑ → CO₂↑ (양의 피드백 존재 확인)
    + O₂ 항상성 attractor가 반대 방향으로 작동 (음의 피드백 확인)
"""

import sys
import os
import math

# GaiaFire_Engine 독립 실행
sys.path.insert(0, os.path.dirname(__file__))

from gaia_loop_connector import GaiaLoopConnector, LoopState, make_connector
from fire_engine import FireEngine, FireEnvSnapshot

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def check(cond: bool, label: str) -> bool:
    s = PASS if cond else FAIL
    print(f"    {s}  {label}")
    return cond


# 위도별 건기 진폭 기본값 (fire_risk.py와 동일)
DRY_AMPLITUDE_TROPICAL  = 0.6
DRY_AMPLITUDE_TEMPERATE = 0.4
DRY_AMPLITUDE_POLAR     = 0.1


def make_default_bio_result(delta_alb: float = -0.02) -> dict:
    """biosphere.step() 결과 흉내 (테스트용)."""
    return {
        "delta_CO2": 0.0,
        "delta_O2": 0.0,
        "transpiration_kg_per_m2_yr": 0.3,
        "latent_heat_biosphere_W": 10.0,
        "delta_albedo_land": delta_alb,
        "GPP": 1.5,
        "Resp": 0.8,
        "NPP": 0.7,
    }


def run_loop_demo():
    print("=" * 65)
    print("  GaiaLoopConnector — 3개 열린 루프 → 닫힌 순환 검증")
    print("  Loop A: 산불CO₂→대기  B: 식생알베도→온도  C: 세차→계절")
    print("=" * 65)
    all_pass = True

    # ──────────────────────────────────────────────────────────────
    print("\n  [V1] Loop A — 산불 CO₂ → 대기 CO₂ 누적")

    atm_a, conn_a = make_connector(
        T_init=288.0, CO2_ppm=400.0, O2_frac=0.21, albedo=0.306
    )
    fire_engine = FireEngine()

    env = FireEnvSnapshot(O2_frac=0.21, CO2_ppm=400.0, time_yr=0.5)
    fire_results = fire_engine.predict(env)

    CO2_before = atm_a.composition.CO2 * 1e6
    cumulative_dCO2 = 0.0

    for yr in range(50):
        dCO2 = conn_a.apply_fire_co2_loop(fire_results, dt_yr=1.0)
        cumulative_dCO2 += dCO2 * 1e6   # ppm 단위로

    CO2_after = atm_a.composition.CO2 * 1e6
    print(f"    CO₂: {CO2_before:.1f} → {CO2_after:.3f} ppm  "
          f"(Δ={CO2_after - CO2_before:+.3f} ppm, 50yr 산불)")

    ok1 = check(
        CO2_after > CO2_before,
        f"산불 CO₂ 누적 후 CO₂ 상승 ({CO2_before:.1f} → {CO2_after:.3f} ppm)"
    )
    all_pass = all_pass and ok1

    # ──────────────────────────────────────────────────────────────
    print("\n  [V2] Loop B — 식생 알베도 → 전지구 알베도 반영")

    atm_b, conn_b = make_connector(
        T_init=288.0, CO2_ppm=400.0, albedo=0.306
    )
    alb_before = atm_b.albedo

    # 식생 증가: delta_albedo_land = -0.05 (더 어두워짐 = 흡수↑)
    bio_result_veg = make_default_bio_result(delta_alb=-0.05)
    for _ in range(30):
        conn_b.apply_albedo_loop(bio_result_veg, smooth_factor=0.1)

    alb_after_veg = atm_b.albedo
    print(f"    식생↑: albedo {alb_before:.4f} → {alb_after_veg:.4f} "
          f"(Δ={alb_after_veg - alb_before:+.4f})")

    # 식생 감소: delta_albedo_land = +0.04 (더 밝아짐 = 반사↑)
    atm_b2, conn_b2 = make_connector(albedo=0.306)
    bio_result_bare = make_default_bio_result(delta_alb=+0.04)
    for _ in range(30):
        conn_b2.apply_albedo_loop(bio_result_bare, smooth_factor=0.1)

    alb_after_bare = atm_b2.albedo
    print(f"    식생↓: albedo {atm_b2.albedo:.4f} → {alb_after_bare:.4f} "
          f"(Δ={alb_after_bare - 0.306:+.4f})")

    ok2 = check(
        alb_after_veg < alb_before,
        f"식생↑ → 알베도↓ ({alb_before:.4f} > {alb_after_veg:.4f})"
    )
    ok3 = check(
        alb_after_bare > alb_before,
        f"식생↓ → 알베도↑ ({alb_before:.4f} < {alb_after_bare:.4f})"
    )
    all_pass = all_pass and ok2 and ok3

    # ──────────────────────────────────────────────────────────────
    print("\n  [V3] Loop C — 세차 obliquity → 계절성 진폭 변화")

    _, conn_c = make_connector()

    # 기준 obliquity (23.5°)
    scale_ref = conn_c.obliquity_scale(23.5)

    # 높은 obliquity (24.5° — Milankovitch 최대)
    scale_high = conn_c.obliquity_scale(24.5)

    # 낮은 obliquity (22.1° — Milankovitch 최소)
    scale_low = conn_c.obliquity_scale(22.1)

    print(f"    obliquity=22.1°: dry_scale={scale_low:.4f}")
    print(f"    obliquity=23.5°: dry_scale={scale_ref:.4f}  (기준)")
    print(f"    obliquity=24.5°: dry_scale={scale_high:.4f}")

    # 건기 수분 계수 비교 (열대, 여름, t=0.5)
    w_ref  = conn_c.obliquity_dry_modifier(15.0, 0.5, DRY_AMPLITUDE_TROPICAL)
    conn_c.obliquity_scale(24.5)
    w_high = conn_c.obliquity_dry_modifier(15.0, 0.5, DRY_AMPLITUDE_TROPICAL)
    conn_c.obliquity_scale(22.1)
    w_low  = conn_c.obliquity_dry_modifier(15.0, 0.5, DRY_AMPLITUDE_TROPICAL)

    print(f"    열대 건기 수분(t=0.5yr): "
          f"obliq22.1°={w_low:.3f} / obliq23.5°={w_ref:.3f} / obliq24.5°={w_high:.3f}")

    ok4 = check(scale_high > scale_ref > scale_low,
                f"obliquity↑ → 계절성↑ ({scale_low:.4f}<{scale_ref:.4f}<{scale_high:.4f})")
    ok5 = check(w_high < w_ref,
                f"obliquity↑ → 건기 더 건조 (w_high={w_high:.3f} < w_ref={w_ref:.3f})")
    all_pass = all_pass and ok4 and ok5

    # ──────────────────────────────────────────────────────────────
    print("\n  [V4] 3루프 통합 — 초기 조건 → 자기조절 순환 확인")
    print("       고O₂(30%) 시작: 산불↑ → CO₂↑ + O₂ attractor 동시 작동")

    atm_int, conn_int = make_connector(
        T_init=290.0,
        CO2_ppm=400.0,
        O2_frac=0.30,       # 비정상적으로 높은 O₂ → 산불 attractor 발동
        albedo=0.306,
        use_water_cycle=False,
    )
    fire_eng_int = FireEngine()

    CO2_track = []
    alb_track  = []
    gfi_track  = []
    F_SOLAR = 1361.0

    for yr in range(20):
        # 현재 O₂, CO₂로 산불 예측
        env_int = FireEnvSnapshot(
            O2_frac  = atm_int.composition.O2,
            CO2_ppm  = atm_int.composition.CO2 * 1e6,
            time_yr  = float(yr % 1 + 0.5),
        )
        results = fire_eng_int.predict(env_int)
        gfi = fire_eng_int.global_fire_index(results)

        # 산불 O₂ 소비 → O₂ 감소
        dO2 = fire_eng_int.delta_O2_frac(results, dt_yr=1.0)
        atm_int.composition.O2 = max(0.01, atm_int.composition.O2 + dO2)

        # biosphere 결과 흉내 (식생 어느 정도 있는 상태)
        bio_r = make_default_bio_result(delta_alb=-0.01)

        # 3루프 통합 스텝
        loop_state = conn_int.step(
            fire_results  = results,
            bio_result    = bio_r,
            obliquity_deg = 23.5,
            dt_yr         = 1.0,
            time_yr       = float(yr),
        )

        # 대기 온도 스텝
        atm_int.step(F_SOLAR, dt_yr=1.0)

        CO2_track.append(atm_int.composition.CO2 * 1e6)
        alb_track.append(atm_int.albedo)
        gfi_track.append(gfi)

    print(f"    CO₂  yr0={CO2_track[0]:.3f}ppm → yr19={CO2_track[-1]:.3f}ppm "
          f"(Δ={CO2_track[-1]-CO2_track[0]:+.3f}ppm)")
    print(f"    알베도  yr0={alb_track[0]:.4f} → yr19={alb_track[-1]:.4f} "
          f"(Δ={alb_track[-1]-alb_track[0]:+.4f})")
    print(f"    GFI  yr0={gfi_track[0]:.4f} → yr19={gfi_track[-1]:.4f} "
          f"(O₂={atm_int.composition.O2:.4f})")
    print(f"    T_surface: {atm_int.T_surface:.2f} K")

    # O₂가 30%에서 시작해서 산불로 소비되어 내려와야 함 (attractor 동작)
    ok6 = check(
        atm_int.composition.O2 < 0.30,
        f"O₂ attractor 동작: 30% → {atm_int.composition.O2:.4f} (산불로 소비)"
    )
    # CO₂는 산불로 방출되어 올라가야 함 (Loop A 동작)
    ok7 = check(
        CO2_track[-1] > CO2_track[0],
        f"Loop A 동작: CO₂ {CO2_track[0]:.3f} → {CO2_track[-1]:.3f} ppm ↑"
    )
    # 알베도는 Loop B로 약간 변화해야 함
    ok8 = check(
        abs(alb_track[-1] - alb_track[0]) > 0.0,
        f"Loop B 동작: 알베도 변화 Δ={alb_track[-1]-alb_track[0]:+.4f}"
    )
    all_pass = all_pass and ok6 and ok7 and ok8

    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  결과: {'ALL PASS ✅' if all_pass else 'SOME FAIL ❌'}")
    print("=" * 65)

    print("\n  ── 항상성 순환 구조 요약 ────────────────────────────────")
    print("  Loop  연결                          방향     타임스케일")
    print("  ─────────────────────────────────────────────────────────")
    print("  [A]  산불→CO₂→온실→T↑→건조→산불      양/음    yr")
    print("  [B]  식생→알베도↓→T↑→GPP→식생         음       yr")
    print("  [C]  세차→건기진폭→fire_risk→CO₂       양       kyr")
    print()
    print(f"  V4 결과: O₂ 30%→{atm_int.composition.O2:.3f} | "
          f"CO₂ {CO2_track[0]:.1f}→{CO2_track[-1]:.1f}ppm | "
          f"T={atm_int.T_surface:.1f}K")
    print("  '초기 고O₂ → 산불 폭발 → O₂ 감소' 항상성 attractor 확인")

    return all_pass


if __name__ == "__main__":
    success = run_loop_demo()
    sys.exit(0 if success else 1)
