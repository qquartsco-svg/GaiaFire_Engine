"""day6_demo.py — Day6 검증 스위트

V1~V14 ALL PASS 목표.

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
