"""selection_engine — Day6 적합도 필터 (Exploitation) + 탐색 선택 (Exploration)

Exploitation(♀): 적합도 기반 선택 (roulette wheel).
Exploration(♂): 다양성·랜덤 기반 선택 (기본: 균등 무작위).
환경 필터: T, CO₂, N, 포식 압력 등으로 fitness 계산 → 부모/생존자 선택.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Callable, Optional, Dict, Any
import random


@dataclass
class SelectionResult:
    """한 세대 선택 결과."""
    survivors: List[int]  # 인덱스
    fitness: List[float]


class SelectionEngine:
    """적합도 기반 선택 (Exploitation).
    fitness_fn(genome, env) → 스칼라. 높을수록 선택 확률 증가.
    """
    def __init__(
        self,
        fitness_fn: Optional[Callable[[Any, Dict[str, Any]], float]] = None,
    ) -> None:
        self.fitness_fn = fitness_fn or (lambda g, e: 1.0)

    def fitness(
        self,
        genome: Any,
        env: Dict[str, Any],
    ) -> float:
        """단일 genome 의 적합도."""
        return self.fitness_fn(genome, env)

    def select(
        self,
        population: List[Any],
        env: Dict[str, Any],
        n_select: int,
        rng: Optional[random.Random] = None,
    ) -> SelectionResult:
        """적합도 비례 선택 (roulette wheel). n_select 명 선택."""
        rng = rng or random.Random()
        n_pop = len(population)
        fits = [self.fitness(p, env) for p in population]
        total = sum(max(0.0, f) for f in fits)
        if total <= 0 or n_pop == 0:
            # 균등 무작위 (중복 허용) — roulette wheel 의미 유지
            idx = [rng.randint(0, max(0, n_pop - 1)) for _ in range(n_select)] if n_pop > 0 else []
            return SelectionResult(survivors=idx, fitness=fits)
        probs = [max(0.0, f) / total for f in fits]
        survivors: List[int] = []
        for _ in range(n_select):
            r = rng.random()
            cum = 0.0
            for i, p in enumerate(probs):
                cum += p
                if r <= cum:
                    survivors.append(i)
                    break
            else:
                survivors.append(len(probs) - 1)
        return SelectionResult(survivors=survivors, fitness=fits)

    def select_exploration(
        self,
        population: List[Any],
        n_select: int,
        rng: Optional[random.Random] = None,
    ) -> List[int]:
        """Exploration(♂) 선택: 적합도와 무관하게 다양성·랜덤 기반.
        기본 구현: 균등 무작위로 n_select 개 인덱스 반환 (중복 허용).
        reproduction_engine.step(..., select_parent_b= lambda pop: engine.select_exploration(pop, 1)[0]) 형태로 사용.
        """
        rng = rng or random.Random()
        n = len(population)
        if n == 0:
            return []
        return [rng.randint(0, n - 1) for _ in range(n_select)]


def make_selection_engine(
    fitness_fn: Optional[Callable[[Any, Dict[str, Any]], float]] = None,
) -> SelectionEngine:
    return SelectionEngine(fitness_fn=fitness_fn)


__all__ = ["SelectionEngine", "SelectionResult", "make_selection_engine"]
