"""day6_demo.py — Day6 검증 스위트

V1~V22 ALL PASS 목표.

V1  genome_state    recombine + mutate 기본 동작
V2  genome_state    child traits 길이 = 부모 길이
V3  reproduction    produce() 결과 타입 및 길이 일치
V4  reproduction    crossover 결과 부모 A/B trait 범위 내
V5  selection       select() Exploitation 적합도 비례 선택
V6  selection       select_exploration() Exploration 균등 범위
V7  contact_engine  P_contact = ρ_i * ρ_j * k / V 수식 검증
V8  contact_engine  scalar = mean(matrix)
V9  mutation_engine fitness_pressure 환경 스트레스 반응
V10 mutation_engine step() n_traits*(n_traits-1) 쌍 최대 이벤트 수
V11 mutation_engine binary_convergence_pressure → via_recombination=True
V12 species_engine  graph 없음 폴백: 성장 > 경쟁 → N 증가
V13 species_engine  graph 연결: competition 행렬 C[i][j] 반영
V14 niche_model     자원 충분 → 점유 증가 / 자원 부족 → 비례 배분
V15 selection       n_select > population 크기 → 오류 없이 처리 (rng.randint 버그 수정 검증)
V16 species_engine  graph 크기 불일치 → ValueError 발생
V17 niche_model     capacity=0 셀 → 전 종 점유 0
V18 day5_coupling   flux 없음 → k_base 반환
V19 day5_coupling   bird_flux 클수록 k_encounter 증가
V20 gaia_feedback   genome traits → CO₂/albedo 환경 수정
V21 gaia_feedback   clamp: CO₂ 물리 한계 내 클램핑
V22 selection       recombination_bonus: 분산 낮은 genome 이 더 높은 fitness
"""

from __future__ import annotations

import random
import sys
import os

# day6 패키지를 직접 경로로 추가 (스크립트 실행 시 상대 임포트 우회)
_HERE = os.path.dirname(os.path.abspath(__file__))
_SOLAR = os.path.dirname(_HERE)
if _SOLAR not in sys.path:
    sys.path.insert(0, _SOLAR)

# ── 임포트 ──────────────────────────────────────────────────────────────────
from day6.genome_state import GenomeState, recombine, mutate
from day6.reproduction_engine import ReproductionEngine, make_reproduction_engine
from day6.selection_engine import SelectionEngine, make_selection_engine
from day6.contact_engine import ContactEngine, make_contact_engine
from day6.mutation_engine import MutationEngine, make_mutation_engine
from day6.species_engine import SpeciesEngine, SpeciesState, make_species_engine
from day6.niche_model import NicheModel, NicheState, make_niche_model
from day6.interaction_graph import InteractionGraph, make_interaction_graph
from day6.day5_coupling import Day5Coupler, make_day5_coupler
from day6.gaia_feedback import GaiaFeedbackEngine, make_gaia_feedback_engine


# ── 헬퍼 ────────────────────────────────────────────────────────────────────
_rng = random.Random(42)
_passed = 0
_failed = 0


def ok(label: str, cond: bool, detail: str = "") -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✓ {label}")
    else:
        _failed += 1
        msg = f"  ✗ {label}"
        if detail:
            msg += f"  ({detail})"
        print(msg)


# ════════════════════════════════════════════════════════════════════════════
# V1 ~ V2  genome_state
# ════════════════════════════════════════════════════════════════════════════
print("\n── V1~V2  genome_state ─────────────────────────────────────────────")

ga = GenomeState(traits=[1.0, 2.0, 3.0])
gb = GenomeState(traits=[4.0, 5.0, 6.0])
child = recombine(ga, gb, crossover_rate=0.5, rng=_rng)
child_mut = mutate(child, rate=1.0, scale=0.05, rng=_rng)  # rate=1.0 → 모든 locus 변이

ok("V1  recombine 반환 타입", isinstance(child, GenomeState))
ok("V2  child 길이 = 부모 길이", len(child.traits) == len(ga.traits),
   f"got {len(child.traits)}")


# ════════════════════════════════════════════════════════════════════════════
# V3 ~ V4  reproduction_engine
# ════════════════════════════════════════════════════════════════════════════
print("\n── V3~V4  reproduction_engine ──────────────────────────────────────")

repro = make_reproduction_engine(crossover_rate=0.5, mutation_rate=0.0)
child2 = repro.produce(ga, gb, rng=_rng)

ok("V3  produce() 반환 타입", isinstance(child2, GenomeState))
ok("V4  child traits 범위 (A 또는 B)", all(
    t in (ga.traits[i], gb.traits[i]) for i, t in enumerate(child2.traits)
), str(child2.traits))


# ════════════════════════════════════════════════════════════════════════════
# V5 ~ V6  selection_engine
# ════════════════════════════════════════════════════════════════════════════
print("\n── V5~V6  selection_engine ─────────────────────────────────────────")

# 적합도 fn: traits[0] 값이 클수록 유리
sel = make_selection_engine(fitness_fn=lambda g, e: g.traits[0])
pop = [GenomeState(traits=[float(i)]) for i in range(1, 6)]  # 1~5
env_test = {"T_surface": 288.0}

result = sel.select(pop, env_test, n_select=100, rng=_rng)
# traits[0]=5 인 개체(인덱스 4)가 가장 많이 선택되어야 함
counts = [0] * 5
for idx in result.survivors:
    counts[idx] += 1
most_selected = counts.index(max(counts))

ok("V5  Exploitation: 고적합도 개체 가장 많이 선택", most_selected == 4,
   f"most_selected=idx{most_selected}, counts={counts}")

expl = sel.select_exploration(pop, n_select=50, rng=_rng)
ok("V6  Exploration: 인덱스 범위 [0, len-1]",
   all(0 <= i < len(pop) for i in expl), str(expl))


# ════════════════════════════════════════════════════════════════════════════
# V7 ~ V8  contact_engine
# ════════════════════════════════════════════════════════════════════════════
print("\n── V7~V8  contact_engine ───────────────────────────────────────────")

ce = make_contact_engine(k_encounter=2.0, V_cell=1.0)
rho_i, rho_j = 3.0, 5.0
expected_p = rho_i * rho_j * 2.0 / 1.0  # = 30.0
got_p = ce.p_contact_pair(rho_i, rho_j)
ok("V7  P_contact 수식 = ρ_i·ρ_j·k/V", abs(got_p - expected_p) < 1e-9,
   f"expected {expected_p}, got {got_p}")

rho_vec = [1.0, 2.0, 3.0]
cr = ce.compute(rho_vec)
n = len(rho_vec)
total_mat = sum(cr.p_contact_matrix[i][j] for i in range(n) for j in range(n))
expected_scalar = total_mat / (n * n)
ok("V8  scalar = mean(matrix)",
   abs(cr.p_contact_scalar - expected_scalar) < 1e-9,
   f"expected {expected_scalar:.6f}, got {cr.p_contact_scalar:.6f}")


# ════════════════════════════════════════════════════════════════════════════
# V9 ~ V11  mutation_engine
# ════════════════════════════════════════════════════════════════════════════
print("\n── V9~V11  mutation_engine ─────────────────────────────────────────")

me = make_mutation_engine(base_mutation_rate=1.0, stress_sensitivity=1.0)

# 스트레스 없음 (기본 환경)
fp_norm = me.fitness_pressure({"T_surface": 288.0, "CO2_ppm": 400.0})
# 스트레스 높음
fp_stress = me.fitness_pressure({"T_surface": 350.0, "CO2_ppm": 800.0})
ok("V9  환경 스트레스 → fitness_pressure 증가",
   fp_stress > fp_norm,
   f"normal={fp_norm:.3f}, stress={fp_stress:.3f}")

# p_contact=1.0, mu=1.0, dt=1e6 → prob_per_pair=1.0 → 모든 쌍 이벤트
n_tr = 5
events_all = me.step(
    p_contact=1.0,
    env={"T_surface": 288.0, "CO2_ppm": 400.0},
    dt_yr=1e6,
    band_idx=0,
    n_traits=n_tr,
    rng=random.Random(99),
)
max_pairs = n_tr * (n_tr - 1)
ok("V10 step() 최대 이벤트 수 = n*(n-1)",
   len(events_all) == max_pairs,
   f"expected {max_pairs}, got {len(events_all)}")

me_bcp = make_mutation_engine(base_mutation_rate=1.0, binary_convergence_pressure=True)
events_bcp = me_bcp.step(
    p_contact=1.0,
    env={"T_surface": 288.0, "CO2_ppm": 400.0},
    dt_yr=1e6,
    band_idx=0,
    n_traits=3,
    rng=random.Random(7),
)
ok("V11 binary_convergence_pressure → via_recombination=True",
   all(e.via_recombination for e in events_bcp),
   f"events={len(events_bcp)}")


# ════════════════════════════════════════════════════════════════════════════
# V12 ~ V13  species_engine
# ════════════════════════════════════════════════════════════════════════════
print("\n── V12~V13  species_engine ─────────────────────────────────────────")

se = make_species_engine(
    n_traits=2,
    growth_rate=0.5,
    competition_strength=0.001,
)
s0 = SpeciesState(n_species=[10.0, 10.0])
env_s = {"GPP_scale": 1.0}

# graph 없음: 성장률 >> 경쟁 → N 증가
s1 = se.step(s0, env_s, dt_yr=1.0, graph=None)
ok("V12 graph 없음 폴백: 성장 > 경쟁 → N 증가",
   all(s1.n_species[i] > s0.n_species[i] for i in range(2)),
   f"{s0.n_species} → {s1.n_species}")

# graph 있음: 경쟁 강도를 아주 세게 → N 감소
g = make_interaction_graph(
    n_species=2,
    competition=[[10.0, 10.0], [10.0, 10.0]],  # 강한 경쟁
    predation=[[0.0, 0.0], [0.0, 0.0]],
)
se2 = make_species_engine(n_traits=2, growth_rate=0.1, competition_strength=0.001)
s2 = se2.step(s0, env_s, dt_yr=1.0, graph=g)
ok("V13 graph 연결: 강한 경쟁 행렬 → N 감소",
   all(s2.n_species[i] < s0.n_species[i] for i in range(2)),
   f"{s0.n_species} → {s2.n_species}")


# ════════════════════════════════════════════════════════════════════════════
# V14  niche_model
# ════════════════════════════════════════════════════════════════════════════
print("\n── V14  niche_model ────────────────────────────────────────────────")

nm = make_niche_model(n_bands=2, n_species=2, growth_rate=0.2)

# 밴드 0: 자원 충분 → 점유 증가
band0 = NicheState(band_idx=0, land_fraction=1.0,
                   resource_capacity=1000.0, occupancy=[1.0, 1.0])
# 밴드 1: 자원 부족 → 비례 배분
band1 = NicheState(band_idx=1, land_fraction=1.0,
                   resource_capacity=0.01, occupancy=[3.0, 1.0])

env_ab = [{"GPP_scale": 1.0}, {"GPP_scale": 1.0}]
result_bands = nm.step([band0, band1], env_ab, dt_yr=1.0)

new0 = result_bands[0]
new1 = result_bands[1]

ok("V14a 자원 충분 → 점유 증가",
   sum(new0.occupancy) > sum(band0.occupancy),
   f"{band0.occupancy} → {new0.occupancy}")

# 자원 부족: total 점유 ≤ capacity * land_fraction
cap_eff = band1.resource_capacity * band1.land_fraction
ok("V14b 자원 부족 → 총 점유 ≤ capacity",
   sum(new1.occupancy) <= cap_eff + 1e-9,
   f"cap={cap_eff:.4f}, total_occ={sum(new1.occupancy):.6f}")

# 자원 부족: 비례 배분 (species 0 점유 비율 > species 1)
ok("V14c 자원 부족: 많은 종이 비례적으로 더 많이 점유",
   new1.occupancy[0] > new1.occupancy[1],
   f"{new1.occupancy}")


# ════════════════════════════════════════════════════════════════════════════
# V15 ~ V17  안정성·확장성 검증 (버그 수정 결과 확인)
# ════════════════════════════════════════════════════════════════════════════
print("\n── V15~V17  안정성·확장성 ──────────────────────────────────────────")

# V15: n_select > population 크기 → rng.sample 버그 수정 검증
sel_zero = make_selection_engine(fitness_fn=lambda g, e: 0.0)  # 모든 적합도 0 → total=0 경로
pop_small = [GenomeState(traits=[1.0]), GenomeState(traits=[2.0])]
res15 = sel_zero.select(pop_small, {}, n_select=10, rng=_rng)
ok("V15 n_select(10) > pop(2), 전 적합도=0 → 오류 없이 10개 반환",
   len(res15.survivors) == 10 and all(0 <= i < 2 for i in res15.survivors),
   f"survivors={res15.survivors}")

# V16: species_engine — graph 크기 불일치 → ValueError
se3 = make_species_engine(n_traits=3)
g_wrong = make_interaction_graph(n_species=2)  # 크기 2 ≠ state 크기 3
s_wrong = SpeciesState(n_species=[1.0, 2.0, 3.0])
raised_v16 = False
try:
    se3.step(s_wrong, {}, dt_yr=1.0, graph=g_wrong)
except ValueError:
    raised_v16 = True
ok("V16 graph 크기 불일치 → ValueError 발생", raised_v16)

# V17: niche_model — capacity=0 셀 → 전 종 점유 0
band_zero = NicheState(band_idx=0, land_fraction=0.0,
                       resource_capacity=100.0, occupancy=[5.0, 3.0])
nm2 = make_niche_model(n_bands=1, n_species=2, growth_rate=0.5)
res17 = nm2.step([band_zero], [{"GPP_scale": 1.0}], dt_yr=1.0)
ok("V17 land_fraction=0 → 전 종 점유 = 0",
   all(o == 0.0 for o in res17[0].occupancy),
   f"occupancy={res17[0].occupancy}")


# ════════════════════════════════════════════════════════════════════════════
# V18 ~ V22  시스템 결합 검증 (A B C 갭 수정 확인)
# ════════════════════════════════════════════════════════════════════════════
print("\n── V18~V22  시스템 결합 (Day5 coupling / Gaia / Sexual convergence) ─")

# V18: Day5 coupling — flux 없음 → k_base 그대로
coupler = make_day5_coupler(k_base=0.2, k_transport=1.0)
res18 = coupler.compute_k_encounter(n_bands=3)
ok("V18 flux 없음 → k_encounter = k_base(0.2) 전 밴드",
   all(abs(k - 0.2) < 1e-9 for k in res18.k_encounter_by_band),
   str(res18.k_encounter_by_band))

# V19: Day5 coupling — bird_flux 증가 → k_encounter 증가
bird_flux_strong = [0.0, 5.0, 0.0]   # 밴드1만 강한 플럭스
bird_flux_weak   = [0.0, 1.0, 0.0]
res19_strong = coupler.compute_k_encounter(bird_flux_by_band=bird_flux_strong)
res19_weak   = coupler.compute_k_encounter(bird_flux_by_band=bird_flux_weak)
ok("V19 bird_flux 강할수록 k_encounter 증가",
   res19_strong.k_encounter_by_band[1] > res19_weak.k_encounter_by_band[1],
   f"strong={res19_strong.k_encounter_by_band[1]:.3f}, weak={res19_weak.k_encounter_by_band[1]:.3f}")

# V20: Gaia feedback — genome traits → CO₂/albedo 수정
gaia = make_gaia_feedback_engine(
    trait_env_map={0: "albedo", 1: "CO2_ppm"},
    trait_weights={0: 1e-3, 1: 0.1},
)
env_init = {"albedo": 0.3, "CO2_ppm": 400.0}
genomes_g = [[0.5, 2.0], [0.3, 1.0]]   # trait[0]=albedo기여, trait[1]=CO2기여
densities_g = [10.0, 5.0]
res20 = gaia.step(env_init, genomes_g, densities_g, dt_yr=1.0)
ok("V20 genome traits → CO₂ 환경 수정 (증가)",
   res20.env_new["CO2_ppm"] > env_init["CO2_ppm"],
   f"CO2: {env_init['CO2_ppm']} → {res20.env_new['CO2_ppm']:.4f}")
ok("V20b genome traits → albedo 환경 수정 (증가)",
   res20.env_new["albedo"] > env_init["albedo"],
   f"albedo: {env_init['albedo']} → {res20.env_new['albedo']:.6f}")

# V21: Gaia feedback — clamp: CO₂ 물리 한계 내 클램핑
gaia_extreme = make_gaia_feedback_engine(
    trait_env_map={0: "CO2_ppm"},
    trait_weights={0: 1e6},  # 극단적으로 큰 값
)
res21 = gaia_extreme.step({"CO2_ppm": 400.0}, [[1.0]], [1000.0], dt_yr=1.0)
ok("V21 CO₂ 극단 변화 → clamp 5000 ppm 이하",
   res21.env_new["CO2_ppm"] <= 5000.0,
   f"CO2={res21.env_new['CO2_ppm']:.1f}")

# V22: Sexual convergence — recombination_bonus: 분산 낮은 genome이 더 높은 fitness
sel_conv = make_selection_engine(
    fitness_fn=lambda g, e: 1.0,  # 기본 적합도 동일
    recombination_bonus=2.0,
)
genome_stable   = GenomeState(traits=[1.0, 1.0, 1.0, 1.0])  # 분산=0 → 보너스 최대
genome_chaotic  = GenomeState(traits=[0.0, 5.0, -3.0, 8.0]) # 분산 높음 → 보너스 작음
fit_stable  = sel_conv.fitness(genome_stable,  {})
fit_chaotic = sel_conv.fitness(genome_chaotic, {})
ok("V22 recombination_bonus: 수렴(저분산) genome > 혼돈(고분산) genome",
   fit_stable > fit_chaotic,
   f"stable={fit_stable:.4f}, chaotic={fit_chaotic:.4f}")


# ════════════════════════════════════════════════════════════════════════════
# 결과 요약
# ════════════════════════════════════════════════════════════════════════════
total = _passed + _failed
print(f"\n{'='*60}")
print(f"  Day6 Demo: {_passed}/{total} PASS  |  {_failed} FAIL")
print(f"{'='*60}")
if _failed == 0:
    print("  ✅  ALL PASS")
else:
    print("  ❌  SOME FAILED — 위 로그 확인 요망")
    sys.exit(1)
