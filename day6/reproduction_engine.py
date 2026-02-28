"""reproduction_engine — Day6 이중 재조합 (crossover, 재생산 프로토콜)

Genome_child = recombine(Genome_A, Genome_B) + mutation

Exploration(♂) + Exploitation(♀) → crossover → 안정적 진화 엔진.
같은 프로토콜끼리만 교배 가능 = 종(species) 개념과 연동.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Callable
import random

from .genome_state import GenomeState, recombine as genome_recombine, mutate as genome_mutate


@dataclass
class ReproductionResult:
    """한 번의 재생산 결과."""
    child: GenomeState
    parent_a_idx: int
    parent_b_idx: int


class ReproductionEngine:
    """이중 유전자 재조합 엔진.
    parent_a (Exploitation 선택) + parent_b (Exploration 선택) → crossover + mutation.
    """
    def __init__(
        self,
        crossover_rate: float = 0.5,
        mutation_rate: float = 1e-4,
        mutation_scale: float = 0.1,
    ) -> None:
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.mutation_scale = mutation_scale

    def produce(
        self,
        parent_a: GenomeState,
        parent_b: GenomeState,
        rng: Optional[random.Random] = None,
    ) -> GenomeState:
        """Genome_child = recombine(A, B) + mutation."""
        rng = rng or random.Random()
        child = genome_recombine(
            parent_a, parent_b,
            crossover_rate=self.crossover_rate,
            rng=rng,
        )
        child = genome_mutate(
            child,
            rate=self.mutation_rate,
            scale=self.mutation_scale,
            rng=rng,
        )
        return child

    def step(
        self,
        population: List[GenomeState],
        select_parent_a: Callable[[List[GenomeState]], int],
        select_parent_b: Callable[[List[GenomeState]], int],
        n_offspring: int = 1,
        rng: Optional[random.Random] = None,
    ) -> List[ReproductionResult]:
        """population 에서 부모 선택 함수로 두 명 뽑아 재조합, n_offspring 회 반복."""
        rng = rng or random.Random()
        results: List[ReproductionResult] = []
        for _ in range(n_offspring):
            i = select_parent_a(population)
            j = select_parent_b(population)
            child = self.produce(population[i], population[j], rng=rng)
            results.append(ReproductionResult(child=child, parent_a_idx=i, parent_b_idx=j))
        return results


def make_reproduction_engine(
    crossover_rate: float = 0.5,
    mutation_rate: float = 1e-4,
    mutation_scale: float = 0.1,
) -> ReproductionEngine:
    return ReproductionEngine(
        crossover_rate=crossover_rate,
        mutation_rate=mutation_rate,
        mutation_scale=mutation_scale,
    )


__all__ = ["ReproductionEngine", "ReproductionResult", "make_reproduction_engine"]
