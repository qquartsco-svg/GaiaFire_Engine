"""milankovitch_demo.py — Milankovitch 3주기 + GaiaLoopConnector 연결 검증

V1: 기본 주기 검증 — 경사각 41kyr, 이심률 100kyr 진동 확인
V2: 빙하기-간빙기 판단 — 21kyr 전 마지막 최성기(LGM) vs 현재
V3: Loop C 연결 — obliquity_scale GaiaLoopConnector에 주입
V4: 시간 드라이버 — 200kyr 시계열, 계절성 진폭 변화 확인
"""

import sys
import os
import math

# GaiaFire_Engine 독립 실행 경로 설정
_ENGINE_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, _ENGINE_ROOT)

from cycles import (
    MilankovitchCycle, make_earth_cycle,
    MilankovitchDriver, make_earth_driver,
    insolation_at,
)
from gaia_loop_connector import make_connector

PASS = "✅ PASS"
FAIL = "❌ FAIL"


def check(cond: bool, label: str) -> bool:
    s = PASS if cond else FAIL
    print(f"    {s}  {label}")
    return cond


def run_milankovitch_demo():
    print("=" * 65)
    print("  Milankovitch — 장주기 순환 드라이버 검증 (넷째날 순환 2)")
    print("  이심률(100kyr) + 경사(41kyr) + 세차(26kyr) → 빙하기 창발")
    print("=" * 65)
    all_pass = True

    # ──────────────────────────────────────────────────────────────
    print("\n  [V1] 기본 주기 검증 — 경사각 41kyr 진동")

    cycle = make_earth_cycle()

    # 현재 (t=0)
    s0 = cycle.state(0.0)
    print(f"    현재(t=0):     e={s0.eccentricity:.4f}  ε={s0.obliquity_deg:.2f}°  "
          f"e×sinψ={s0.precession_index:+.4f}")

    # 41kyr 뒤 (경사 주기 1사이클)
    s41 = cycle.state(41_000.0)
    print(f"    41kyr 뒤:      e={s41.eccentricity:.4f}  ε={s41.obliquity_deg:.2f}°  "
          f"e×sinψ={s41.precession_index:+.4f}")

    # 100kyr 뒤 (이심률 주기 1사이클)
    s100 = cycle.state(100_000.0)
    print(f"    100kyr 뒤:     e={s100.eccentricity:.4f}  ε={s100.obliquity_deg:.2f}°  "
          f"e×sinψ={s100.precession_index:+.4f}")

    # 경사각 범위 검증 (200kyr 탐색)
    eps_vals = [cycle.obliquity(float(t)) for t in range(-200_000, 200_001, 1000)]
    eps_min_found = min(eps_vals)
    eps_max_found = max(eps_vals)
    print(f"    경사각 탐색 범위: {eps_min_found:.2f}° ~ {eps_max_found:.2f}° "
          f"(이론: 22.1°~24.5°)")

    ok1 = check(22.0 <= eps_min_found <= 22.5,
                f"경사각 최솟값 22.0~22.5° 범위 ({eps_min_found:.2f}°)")
    ok2 = check(24.0 <= eps_max_found <= 24.8,
                f"경사각 최댓값 24.0~24.8° 범위 ({eps_max_found:.2f}°)")
    all_pass = all_pass and ok1 and ok2

    # 이심률 범위 검증
    e_vals = [cycle.eccentricity(float(t)) for t in range(-500_000, 500_001, 1000)]
    e_min_found = min(e_vals)
    e_max_found = max(e_vals)
    print(f"    이심률 탐색 범위: {e_min_found:.4f} ~ {e_max_found:.4f} "
          f"(이론: 0.001~0.058)")
    ok3 = check(e_min_found < 0.01,
                f"이심률 최솟값 < 0.01 ({e_min_found:.4f})")
    ok4 = check(e_max_found > 0.02,
                f"이심률 최댓값 > 0.02 ({e_max_found:.4f})")
    all_pass = all_pass and ok3 and ok4

    # ──────────────────────────────────────────────────────────────
    print("\n  [V2] LGM vs 현재 — 빙하기 판단")

    # Last Glacial Maximum: ~21,000년 전
    t_lgm = -21_000.0
    s_lgm = cycle.state(t_lgm)
    q_lgm = cycle.insolation_summer_solstice(t_lgm, 65.0)
    is_lgm = cycle.is_glacial(t_lgm, phi_deg=65.0, insolation_threshold=510.0)

    # 현재
    q_now = cycle.insolation_summer_solstice(0.0, 65.0)
    is_now = cycle.is_glacial(0.0, phi_deg=65.0, insolation_threshold=510.0)

    print(f"    LGM(-21kyr):  ε={s_lgm.obliquity_deg:.2f}°  e={s_lgm.eccentricity:.4f}"
          f"  Q(65°N,여름)={q_lgm:.1f}W/m²  → {'빙하기✓' if is_lgm else '간빙기'}")
    print(f"    현재(t=0):    ε={s0.obliquity_deg:.2f}°  e={s0.eccentricity:.4f}"
          f"  Q(65°N,여름)={q_now:.1f}W/m²  → {'빙하기' if is_now else '간빙기✓'}")

    ok5 = check(not is_now, f"현재 = 간빙기 판단")
    all_pass = all_pass and ok5

    # ──────────────────────────────────────────────────────────────
    print("\n  [V3] Loop C 연결 — obliquity_scale GaiaLoopConnector 주입")

    driver = make_earth_driver()
    _, connector = make_connector(T_init=288.0, CO2_ppm=400.0)
    try:
        from solar.fire import FireEngine, FireEnvSnapshot
    except ImportError:
        from fire_engine import FireEngine, FireEnvSnapshot

    fire_engine = FireEngine()

    # 현재 obliquity로 env 생성
    out_now = driver.step(0.0)
    env_now = connector.make_fire_env(
        FireEnvSnapshot(O2_frac=0.21, CO2_ppm=400.0, time_yr=0.5),
        obliquity_deg=out_now.milank_state.obliquity_deg,
    )

    # 10kyr 뒤 (경사각 변화 구간)
    out_10k = driver.step(10_000.0)
    env_10k = connector.make_fire_env(
        FireEnvSnapshot(O2_frac=0.21, CO2_ppm=400.0, time_yr=0.5),
        obliquity_deg=out_10k.milank_state.obliquity_deg,
    )

    print(f"    t=0:      ε={out_now.milank_state.obliquity_deg:.2f}°  "
          f"scale={out_now.obliquity_scale:.4f}  "
          f"obliq_env={env_now.obliquity_deg:.2f}°")
    print(f"    t=10kyr:  ε={out_10k.milank_state.obliquity_deg:.2f}°  "
          f"scale={out_10k.obliquity_scale:.4f}  "
          f"obliq_env={env_10k.obliquity_deg:.2f}°")

    ok6 = check(
        abs(env_now.obliquity_deg - out_now.milank_state.obliquity_deg) < 0.01,
        f"obliquity GaiaLoopConnector에 정확히 전달됨"
    )
    ok7 = check(
        out_now.obliquity_scale != out_10k.obliquity_scale,
        f"시간에 따라 obliquity_scale 변화 ({out_now.obliquity_scale:.4f}≠{out_10k.obliquity_scale:.4f})"
    )
    all_pass = all_pass and ok6 and ok7

    # ──────────────────────────────────────────────────────────────
    print("\n  [V4] 시계열 — 200kyr 계절성 진폭 변화")

    series = cycle.time_series(-200_000, 0, dt=5_000)
    amp_vals    = [s.season_amplitude for s in series]
    obliq_vals  = [s.obliquity_deg    for s in series]
    e_vals_t    = [s.eccentricity     for s in series]

    amp_min  = min(amp_vals)
    amp_max  = max(amp_vals)
    glac_cnt = sum(1 for s in series if cycle.is_glacial(s.time_yr, insolation_threshold=480.0))

    print(f"    200kyr 시계열 ({len(series)} 포인트, dt=5kyr)")
    print(f"    계절성 진폭:  {amp_min:.4f} ~ {amp_max:.4f}")
    print(f"    경사각 범위:  {min(obliq_vals):.2f}° ~ {max(obliq_vals):.2f}°")
    print(f"    이심률 범위:  {min(e_vals_t):.4f} ~ {max(e_vals_t):.4f}")
    print(f"    빙하기 포인트: {glac_cnt}/{len(series)}")

    ok8 = check(amp_max > amp_min * 1.1,
                f"계절성 진폭 시간에 따라 진동 (max/min={amp_max/max(amp_min,1e-9):.2f}×)")
    ok9 = check(glac_cnt > 0,
                f"빙하기 포인트 존재 ({glac_cnt}개)")
    all_pass = all_pass and ok8 and ok9

    # 샘플 출력 (5만년 간격)
    print(f"\n    {'시간(kyr)':>10}  {'경사(°)':>8}  {'이심률':>8}  "
          f"{'e×sinψ':>9}  {'빙하기?':>7}  {'계절진폭':>8}")
    print("    " + "-" * 62)
    for s in series[::10]:
        glac = "🧊빙하기" if cycle.is_glacial(s.time_yr, insolation_threshold=480.0) else "  간빙기"
        print(f"    {s.time_yr/1000:>9.0f}  {s.obliquity_deg:>8.2f}  "
              f"{s.eccentricity:>8.4f}  {s.precession_index:>+9.4f}  "
              f"{glac}  {s.season_amplitude:>8.4f}")

    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  결과: {'ALL PASS ✅' if all_pass else 'SOME FAIL ❌'}")
    print("=" * 65)

    print("\n  ── 넷째날 순환 2 파이프라인 ────────────────────────────────")
    print("  MilankovitchCycle → obliquity(t) → GaiaLoopConnector.Loop C")
    print("  MilankovitchCycle → F0_corrected → FireEnvSnapshot.F0")
    print("  MilankovitchCycle → is_glacial(t) → [ice_albedo 예정]")
    print()
    print(f"  현재 (t=0):   ε={s0.obliquity_deg:.2f}°  e={s0.eccentricity:.4f}  "
          f"scale={s0.obliquity_scale:.4f}")
    print(f"  21kyr전(LGM): ε={s_lgm.obliquity_deg:.2f}°  e={s_lgm.eccentricity:.4f}  "
          f"Q(65°N)={q_lgm:.1f}W/m²")

    return all_pass


if __name__ == "__main__":
    success = run_milankovitch_demo()
    sys.exit(0 if success else 1)
