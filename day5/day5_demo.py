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
        long_range_neighbors,
        SeedTransport, TransportKernel, make_transport,
        FoodWeb, TrophicState, make_food_web,
        M_HERBIVORE, R_GUANO_N,
    )
except ImportError:
    from day5 import (
        BirdAgent, FishAgent,
        make_bird_agent, make_fish_agent,
        long_range_neighbors,
        SeedTransport, TransportKernel, make_transport,
        FoodWeb, TrophicState, make_food_web,
        M_HERBIVORE, R_GUANO_N,
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

    # 이웃 구조: 극지(밴드 0, 11)는 1개, 나머지는 2개
    ok4 = check(
        len(bird.neighbors[0]) == 1
        and len(bird.neighbors[N_BANDS - 1]) == 1
        and all(len(bird.neighbors[i]) == 2 for i in range(1, N_BANDS - 1)),
        f"극지 1개 / 중위도 2개 이웃 구조 확인"
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
    print("\n  [V6] 극지 topology — 양 끝 밴드 단방향 이웃")

    ok15 = check(
        bird.neighbors[0] == [1],
        f"밴드 0(남극) 이웃 = [1] only → {bird.neighbors[0]}"
    )
    ok16 = check(
        bird.neighbors[N_BANDS - 1] == [N_BANDS - 2],
        f"밴드 {N_BANDS-1}(북극) 이웃 = [{N_BANDS-2}] only → {bird.neighbors[N_BANDS-1]}"
    )
    ok17 = check(
        bird.neighbors[6] == [5, 7],
        f"밴드 6(중위도) 이웃 = [5, 7] → {bird.neighbors[6]}"
    )
    all_pass = all_pass and ok15 and ok16 and ok17

    # ──────────────────────────────────────────────────────────────
    print("\n  [V7] carnivore 사망률 — 장기 폭증 방지")

    fw2 = make_food_web()
    s = TrophicState(phyto=0.5, herbivore=0.2, carnivore=0.5, co2_resp_yr=0.0)
    # GPP=0, grazing 극소 → carnivore는 사망률로 감소해야 함
    for _ in range(20):
        s = fw2.step(s, env={"GPP": 0.0}, dt_yr=1.0)
    ok18 = check(
        s.carnivore < 0.5,
        f"carnivore 20yr 후 감소: 0.500 → {s.carnivore:.4f}"
    )
    all_pass = all_pass and ok18

    # ──────────────────────────────────────────────────────────────
    print("\n  [V8] FishAgent→FoodWeb 포트 — env[fish_predation] 주입")

    fish = make_fish_agent(n_bands=N_BANDS)
    phyto_by_band = [0.4] * N_BANDS
    fish_pred = fish.predation_flux(phyto_by_band)

    s_no_fish  = TrophicState(phyto=0.5, herbivore=0.2, carnivore=0.1, co2_resp_yr=0.0)
    s_with_fish = TrophicState(phyto=0.5, herbivore=0.2, carnivore=0.1, co2_resp_yr=0.0)
    fw3 = make_food_web()
    s_no_fish   = fw3.step(s_no_fish,   env={"GPP": 0.3},                              dt_yr=1.0)
    s_with_fish = fw3.step(s_with_fish, env={"GPP": 0.3, "fish_predation": fish_pred[6]}, dt_yr=1.0)

    ok19 = check(
        s_with_fish.phyto < s_no_fish.phyto,
        f"fish_predation 주입 시 phyto 감소: {s_no_fish.phyto:.4f} → {s_with_fish.phyto:.4f}"
    )
    ok20 = check(
        s_with_fish.co2_resp_yr > s_no_fish.co2_resp_yr,
        f"fish_predation 주입 시 CO₂ 증가: {s_no_fish.co2_resp_yr:.4f} → {s_with_fish.co2_resp_yr:.4f}"
    )
    all_pass = all_pass and ok19 and ok20

    # ──────────────────────────────────────────────────────────────
    print("\n  [V9] herbivore 사망률 — 장기 폭증 방지")

    fw4 = make_food_web()
    s_h = TrophicState(phyto=0.5, herbivore=0.5, carnivore=0.0, co2_resp_yr=0.0)
    # GPP=0, carnivore=0 → predation 없음 → herbivore는 사망률만으로 감소
    for _ in range(20):
        s_h = fw4.step(s_h, env={"GPP": 0.0}, dt_yr=1.0)
    ok21 = check(
        s_h.herbivore < 0.5,
        f"herbivore 20yr 후 감소: 0.500 → {s_h.herbivore:.4f}"
    )
    # M_HERBIVORE < M_CARNIVORE: herbivore가 더 천천히 감소
    s_c2 = TrophicState(phyto=0.5, herbivore=0.0, carnivore=0.5, co2_resp_yr=0.0)
    for _ in range(20):
        s_c2 = fw4.step(s_c2, env={"GPP": 0.0}, dt_yr=1.0)
    ok22 = check(
        s_h.herbivore > s_c2.carnivore,
        f"herbivore(mh={fw4.mh}) 감소 < carnivore(mc={fw4.mc}) 감소: "
        f"{s_h.herbivore:.4f} > {s_c2.carnivore:.4f}"
    )
    all_pass = all_pass and ok21 and ok22

    # ──────────────────────────────────────────────────────────────
    print("\n  [V10] guano 단위 — R_GUANO_N * rate = [g N/m²/yr]")

    bird_g = make_bird_agent(n_bands=N_BANDS)
    guano_vals = bird_g.guano_flux()
    # guano[i] = R_GUANO_N * rate_i = 0.1 [g N·yr/m²] * 0.05 [1/yr] = 0.005 [g N/m²/yr]
    expected_guano = R_GUANO_N * bird_g.base_rate
    ok23 = check(
        all(abs(g - expected_guano) < 1e-9 for g in guano_vals),
        f"guano = R_GUANO_N({R_GUANO_N}) × base_rate({bird_g.base_rate}) "
        f"= {expected_guano:.5f} g N/m²/yr (모든 밴드 동일)"
    )
    ok24 = check(
        0.001 <= expected_guano <= 0.1,
        f"guano 합리적 범위 [0.001, 0.1] g N/m²/yr: {expected_guano:.5f}"
    )
    all_pass = all_pass and ok23 and ok24

    # ──────────────────────────────────────────────────────────────
    print("\n  [V11] 장거리 이동(long_range) — 전 지구 네트워킹")

    # long_range_neighbors 구조 검증
    lr_nb = long_range_neighbors(N_BANDS, max_jump=2)
    ok25 = check(
        len(lr_nb) == N_BANDS,
        f"long_range_neighbors 길이 = {N_BANDS} ({len(lr_nb)})"
    )
    # 중위도 밴드 6 → ±2 이웃 [4,5,7,8] 4개
    ok26 = check(
        lr_nb[6] == [4, 5, 7, 8],
        f"밴드 6 long_range 이웃 = [4,5,7,8] (±2) → {lr_nb[6]}"
    )
    # 극지 밴드 0 → [1, 2] (범위 내만)
    ok27 = check(
        lr_nb[0] == [1, 2],
        f"밴드 0(남극) long_range 이웃 = [1,2] → {lr_nb[0]}"
    )

    # 장거리 vs 인접: 씨드가 더 빠르게 전파되는지 비교 (10yr)
    B_short = [0.0] * N_BANDS;  B_short[6] = 1.0
    B_long  = [0.0] * N_BANDS;  B_long[6]  = 1.0

    bird_short = BirdAgent(n_bands=N_BANDS)                        # 기본: 인접만
    bird_long  = BirdAgent(n_bands=N_BANDS, long_range_max_jump=2) # 장거리 ±2

    for _ in range(10):
        tr_s = make_transport(N_BANDS, bird_short.neighbors, bird_short.migration_rates())
        tr_l = make_transport(N_BANDS, bird_long.neighbors,  bird_long.migration_rates())
        B_short = tr_s.step(B_short, dt_yr=1.0)
        B_long  = tr_l.step(B_long,  dt_yr=1.0)

    # 극지(밴드 0) 도달량: 장거리가 인접보다 많아야 함
    ok28 = check(
        B_long[0] > B_short[0],
        f"10yr 후 극지 도달: 장거리 {B_long[0]:.5f} > 인접 {B_short[0]:.5f}"
    )
    # 총합 보존 둘 다
    ok29 = check(
        abs(sum(B_short) - 1.0) < 1e-9 and abs(sum(B_long) - 1.0) < 1e-9,
        f"장거리/인접 모두 총합 보존 (short={sum(B_short):.6f}, long={sum(B_long):.6f})"
    )
    all_pass = all_pass and ok25 and ok26 and ok27 and ok28 and ok29

    # ──────────────────────────────────────────────────────────────
    print("\n  [V12] 도메인 분리 — Bird 육상/Fish 해양")

    # 반반 시나리오: 밴드 0~5 = 육지, 밴드 6~11 = 해양
    land_frac = [1.0] * 6 + [0.0] * 6   # 0~5 육지, 6~11 해양

    # Bird: 육지(0~5)에서만 활동 → 해양 밴드 rate=0
    bird_dom = make_bird_agent(n_bands=N_BANDS)
    rates_land = bird_dom.migration_rates(land_fraction_by_band=land_frac)
    ok30 = check(
        all(rates_land[i] > 0 for i in range(6)),
        f"Bird: 육지 밴드(0~5) rate > 0 (mean={sum(rates_land[:6])/6:.4f})"
    )
    ok31 = check(
        all(rates_land[i] == 0.0 for i in range(6, N_BANDS)),
        f"Bird: 해양 밴드(6~11) rate = 0 (도메인 분리)"
    )

    # Fish: 해양(6~11)에서만 활동 → 육지 밴드 rate=0
    fish_dom = make_fish_agent(n_bands=N_BANDS)
    rates_sea = fish_dom.migration_rates(land_fraction_by_band=land_frac)
    ok32 = check(
        all(rates_sea[i] == 0.0 for i in range(6)),
        f"Fish: 육지 밴드(0~5) rate = 0 (도메인 분리)"
    )
    ok33 = check(
        all(rates_sea[i] > 0 for i in range(6, N_BANDS)),
        f"Fish: 해양 밴드(6~11) rate > 0 (mean={sum(rates_sea[6:])/6:.4f})"
    )

    # 구아노: 육지 밴드에서만 발생, 해양 밴드 = 0
    guano_dom = bird_dom.guano_flux(land_fraction_by_band=land_frac)
    ok34 = check(
        all(guano_dom[i] > 0 for i in range(6)) and
        all(guano_dom[i] == 0.0 for i in range(6, N_BANDS)),
        f"구아노: 육지 >0, 해양 =0  "
        f"(land_mean={sum(guano_dom[:6])/6:.5f}, sea_mean={sum(guano_dom[6:])/6:.5f})"
    )
    all_pass = all_pass and ok30 and ok31 and ok32 and ok33 and ok34

    # ──────────────────────────────────────────────────────────────
    print("\n  [V13] biomass 스케일링 — 대형 생명체 개체수 비례 플럭스")

    # 시나리오: 밴드 6(적도)에만 새 무리 집중 (biomass=5.0), 나머지=1.0
    biomass_bird = [1.0] * N_BANDS
    biomass_bird[6] = 5.0   # 적도 새 무리 5배

    pioneer_b = [0.3] * N_BANDS
    bird_b = make_bird_agent(n_bands=N_BANDS)

    seed_no_bm = bird_b.seed_flux(pioneer_b)                         # biomass 없음
    seed_with_bm = bird_b.seed_flux(pioneer_b, biomass_by_band=biomass_bird)  # biomass 적용

    # 적도(밴드 6)에서 이웃으로 나가는 플럭스: biomass 5배면 이웃 유입도 5배
    ok35 = check(
        seed_with_bm[5] > seed_no_bm[5] and seed_with_bm[7] > seed_no_bm[7],
        f"밴드 6 이웃 유입: biomass 적용 시 증가 "
        f"(band5: {seed_no_bm[5]:.5f}→{seed_with_bm[5]:.5f}, "
        f"band7: {seed_no_bm[7]:.5f}→{seed_with_bm[7]:.5f})"
    )
    # 밴드 5 유입 = 밴드 6(biomass=5) 방출분 + 밴드 4(biomass=1) 방출분
    # biomass=1 일 때: in_5 = out_6/2 + out_4/2  (밴드 6,4 각각 이웃 2개)
    # biomass 적용:    in_5 = out_6*5/2 + out_4*1/2  → 비율 = (5/2 + 1/2)/(1/2 + 1/2) = 3.0
    expected_ratio = (5.0 / 2 + 1.0 / 2) / (1.0 / 2 + 1.0 / 2)
    ok36 = check(
        abs(seed_with_bm[5] / seed_no_bm[5] - expected_ratio) < 0.01,
        f"밴드 5 유입 비율 = {expected_ratio:.1f}x "
        f"(band6×5/2 + band4×1/2) / (band6×1/2 + band4×1/2) "
        f"→ 실측={seed_with_bm[5]/seed_no_bm[5]:.3f}"
    )

    # Fish biomass: 물고기 많은 밴드에서 포식량 비례 증가
    biomass_fish = [1.0] * N_BANDS
    biomass_fish[3] = 3.0   # 밴드 3에 물고기 집중
    phyto_b = [0.5] * N_BANDS
    fish_b = make_fish_agent(n_bands=N_BANDS)

    pred_no_bm   = fish_b.predation_flux(phyto_b)
    pred_with_bm = fish_b.predation_flux(phyto_b, biomass_by_band=biomass_fish)

    ok37 = check(
        abs(pred_with_bm[3] / pred_no_bm[3] - 3.0) < 0.01,
        f"Fish 밴드 3: biomass 3배 → 포식량 3배 "
        f"(비율={pred_with_bm[3]/pred_no_bm[3]:.3f})"
    )
    ok38 = check(
        all(abs(pred_with_bm[i] - pred_no_bm[i]) < 1e-9
            for i in range(N_BANDS) if i != 3),
        f"Fish biomass=1 밴드: 포식량 변화 없음 (비-3밴드 동일)"
    )
    all_pass = all_pass and ok35 and ok36 and ok37 and ok38

    # ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"  결과: {'ALL PASS ✅' if all_pass else 'SOME FAIL ❌'}")
    print("=" * 65)

    print("\n  ── 다섯째날 파이프라인 ──────────────────────────────────────")
    print("  BirdAgent.migration_rates() → SeedTransport.step(B_pioneer)")
    print("  BirdAgent.seed_flux()       → (보조) 이웃 유입만 (비보존)")
    print("  BirdAgent.guano_flux()      → nitrogen.N_soil[i] += Δ  [g N/m²/yr]")
    print("  FishAgent.predation_flux()  → env['fish_predation'] → FoodWeb.phyto -= Δ")
    print("  FoodWeb.co2_resp_yr         → atmosphere.CO₂ += co2_resp_yr * dt_yr")
    print()
    print(f"  Bird base_rate={bird.base_rate}/yr  Fish base_rate={make_fish_agent().base_rate}/yr")
    print(f"  carnivore 사망률={fw2.mc}/yr  herbivore 사망률={M_HERBIVORE}/yr  극지 wrap-around=없음")

    return all_pass


if __name__ == "__main__":
    success = run_day5_demo()
    sys.exit(0 if success else 1)
