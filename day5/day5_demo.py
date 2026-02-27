"""day5_demo.py — Day5 생물 이동 레이어 검증 (다섯째날)

V1: BirdAgent 이동률 — O₂ 반응, 이웃 구조 확인
V2: SeedTransport 보존성 — transport 후 총합 보존
V3: Loop F/G 연결 — 씨드 분산 + 구아노 N 주입
V4: FoodWeb Loop H — phyto/zoo/fish ODE + CO₂ 호흡
V5: 통합 시계열 — 50yr BirdAgent 이동 + SeedTransport 진화

실행 환경 (3가지 모두 지원):
    1. CookiieBrain:  python solar/day5/day5_demo.py
    2. day5/ 직접:   python day5_demo.py
"""

import sys
import os

# 3단 fallback import 경로 등록
_HERE   = os.path.dirname(os.path.abspath(__file__))   # day5/
_PARENT = os.path.dirname(_HERE)                        # solar/
_ROOT   = os.path.dirname(_PARENT)                      # CookiieBrain/
for _p in (_HERE, _PARENT, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from solar.day5 import (
        BirdAgent, FishAgent,
        make_bird_agent, make_fish_agent,
        SeedTransport, TransportKernel, make_transport,
        FoodWeb, TrophicState, make_food_web,
    )
except ImportError:
    from day5 import (
        BirdAgent, FishAgent,
        make_bird_agent, make_fish_agent,
        SeedTransport, TransportKernel, make_transport,
        FoodWeb, TrophicState, make_food_web,
    )

PASS = "✅ PASS"
FAIL = "❌ FAIL"

N_BANDS = 12


def check(cond: bool, label: str) -> bool:
    s = PASS if cond else FAIL
    print(f"    {s}  {label}")
    return cond


def run_day5_demo():
    print("=" * 65)
    print("  Day5 — 생물 이동 레이어 검증 (Loop F/G/H)")
    print("  BirdAgent + SeedTransport + FoodWeb")
    print("=" * 65)
    all_pass = True

    # ──────────────────────────────────────────────────────────────
    print("\n  [V1] BirdAgent 이동률 — O₂ 반응 + 이웃 구조")

    bird = make_bird_agent(n_bands=N_BANDS)

    # 기본 이동률
    rates_default = bird.migration_rates()
    ok1 = check(
        len(rates_default) == N_BANDS,
        f"이동률 벡터 길이 = {N_BANDS} ({len(rates_default)})"
    )
    ok2 = check(
        all(r > 0 for r in rates_default),
        f"기본 이동률 > 0 (base={bird.base_rate})"
    )

    # O₂ 반응: O₂ 높을수록 이동률 증가
    o2_low  = [0.10] * N_BANDS
    o2_high = [0.30] * N_BANDS
    rates_low  = bird.migration_rates(o2_low)
    rates_high = bird.migration_rates(o2_high)
    ok3 = check(
        rates_high[0] > rates_low[0],
        f"O₂ 높을수록 이동률 증가 ({rates_high[0]:.4f} > {rates_low[0]:.4f})"
    )

    # 이웃 구조: 각 밴드는 2개 이웃 (링 구조)
    ok4 = check(
        all(len(nb) == 2 for nb in bird.neighbors),
        f"모든 밴드 이웃 수 = 2 (링 구조)"
    )
    all_pass = all_pass and ok1 and ok2 and ok3 and ok4

    # ──────────────────────────────────────────────────────────────
    print("\n  [V2] SeedTransport 보존성 — transport 후 총합 보존")

    rates = bird.migration_rates()
    transport = make_transport(
        n_bands=N_BANDS,
        neighbors=bird.neighbors,
        rates=rates,
    )

    # 초기 B: 밴드 6(적도)에만 씨드 집중
    B_init = [0.0] * N_BANDS
    B_init[6] = 1.0
    total_init = sum(B_init)

    B_after = transport.step(B_init, dt_yr=1.0)
    total_after = sum(B_after)

    ok5 = check(
        abs(total_after - total_init) < 1e-9,
        f"총합 보존: {total_init:.6f} → {total_after:.6f} (차이={abs(total_after-total_init):.2e})"
    )
    ok6 = check(
        B_after[5] > 0 or B_after[7] > 0,
        f"씨드 이웃 밴드로 확산: B[5]={B_after[5]:.4f}, B[7]={B_after[7]:.4f}"
    )
    all_pass = all_pass and ok5 and ok6

    # ──────────────────────────────────────────────────────────────
    print("\n  [V3] Loop F/G — 씨드 분산 + 구아노 N 주입")

    pioneer = [0.1] * N_BANDS
    pioneer[6] = 0.5  # 적도 pioneer 풍부

    # Loop F: 씨드 분산
    seed_in = bird.seed_flux(pioneer)
    ok7 = check(
        sum(seed_in) > 0,
        f"Loop F: 씨드 분산 발생 (total={sum(seed_in):.5f})"
    )
    ok8 = check(
        seed_in[6] == 0.0 or seed_in[5] > 0 or seed_in[7] > 0,
        f"Loop F: 적도(6) 씨드 → 이웃 밴드 전달"
    )

    # Loop G: 구아노 N
    guano = bird.guano_flux()
    ok9 = check(
        all(g > 0 for g in guano),
        f"Loop G: 전 밴드 구아노 N > 0 (mean={sum(guano)/len(guano):.5f} g/m²/yr)"
    )
    all_pass = all_pass and ok7 and ok8 and ok9

    # ──────────────────────────────────────────────────────────────
    print("\n  [V4] FoodWeb Loop H — phyto/herb/carn ODE + CO₂ 호흡")

    fw = make_food_web()
    state = TrophicState(phyto=0.5, herbivore=0.2, carnivore=0.1, co2_resp_yr=0.0)

    # GPP 있는 환경 (광합성 활발)
    state_gpp = fw.step(state, env={"GPP": 0.5}, dt_yr=1.0)
    ok10 = check(
        state_gpp.phyto > 0,
        f"GPP 있는 환경: phyto > 0 ({state_gpp.phyto:.3f})"
    )
    ok11 = check(
        state_gpp.co2_resp_yr > 0,
        f"CO₂ 호흡 발생 ({state_gpp.co2_resp_yr:.4f} kgC/m²/yr)"
    )

    # GPP=0 환경 (광합성 없음 → phyto 감소)
    state_dark = fw.step(state, env={"GPP": 0.0}, dt_yr=1.0)
    ok12 = check(
        state_dark.phyto < state.phyto,
        f"GPP=0: phyto 감소 ({state.phyto:.3f} → {state_dark.phyto:.3f})"
    )
    all_pass = all_pass and ok10 and ok11 and ok12

    # ──────────────────────────────────────────────────────────────
    print("\n  [V5] 통합 시계열 — 50yr SeedTransport 진화")

    # pioneer 필드 초기화: 극지 0, 적도 0.5
    B_pioneer = [0.0] * N_BANDS
    for i in range(N_BANDS):
        phi_abs = abs(-90.0 + (i + 0.5) * 15.0)  # 극지거리
        B_pioneer[i] = max(0.0, 0.5 - phi_abs / 180.0)

    total_0 = sum(B_pioneer)

    # 50yr transport 시뮬레이션
    B = list(B_pioneer)
    for yr in range(50):
        o2 = [0.21] * N_BANDS
        rates_yr = bird.migration_rates(o2)
        tr = make_transport(N_BANDS, bird.neighbors, rates_yr)
        B = tr.step(B, dt_yr=1.0)

    total_50 = sum(B)

    print(f"\n    초기 pioneer 분포 (적도 피크):")
    print(f"    {' '.join(f'{b:.2f}' for b in B_pioneer)}")
    print(f"    50yr 후 pioneer 분포:")
    print(f"    {' '.join(f'{b:.2f}' for b in B)}")

    ok13 = check(
        abs(total_50 - total_0) < 1e-6,
        f"50yr 후 총합 보존: {total_0:.6f} → {total_50:.6f}"
    )
    # 균일화 확인: 극지 pioneer 증가
    ok14 = check(
        B[0] > B_pioneer[0],
        f"극지(밴드 0) pioneer 증가: {B_pioneer[0]:.4f} → {B[0]:.4f}"
    )
    all_pass = all_pass and ok13 and ok14

    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  결과: {'ALL PASS ✅' if all_pass else 'SOME FAIL ❌'}")
    print("=" * 65)

    print("\n  ── 다섯째날 파이프라인 ──────────────────────────────────────")
    print("  BirdAgent.migration_rates() → SeedTransport.step(B_pioneer)")
    print("  BirdAgent.seed_flux()       → latitude_bands[i].pioneer += Δ")
    print("  BirdAgent.guano_flux()      → nitrogen.N_soil[i] += Δ")
    print("  FishAgent.predation_flux()  → FoodWeb.phyto -= Δ")
    print("  FoodWeb.co2_resp_yr         → atmosphere.CO₂ += Δ")
    print()
    print(f"  Bird base_rate={bird.base_rate}/yr  Fish base_rate={make_fish_agent().base_rate}/yr")

    return all_pass


if __name__ == "__main__":
    success = run_day5_demo()
    sys.exit(0 if success else 1)
