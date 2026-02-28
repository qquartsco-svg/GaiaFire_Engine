"""genome_state — Day6 상속 가능 정보 (Genome, recombine, mutate)

Genome_child = recombine(Genome_A, Genome_B) + mutation

이중 유전자 재조합의 피연산자·결과 타입.
trait 벡터 또는 비트열로 표현된 "상속 가능한 정보".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import random


@dataclass
class GenomeState:
    """상속 가능 정보 (trait 벡터).
    재조합·변이 연산의 입출력.
    """
    traits: List[float]  # 연속 trait 또는 이산 대립유전자 표현

    def copy(self) -> GenomeState:
        return GenomeState(traits=list(self.traits))


def recombine(
    parent_a: GenomeState,
    parent_b: GenomeState,
    crossover_rate: float = 0.5,
    rng: Optional[random.Random] = None,
) -> GenomeState:
    """이중 재조합: Genome_child = recombine(A, B).
    locus 별로 A 또는 B에서 채움 (균일 crossover).
    """
    rng = rng or random.Random()
    n = min(len(parent_a.traits), len(parent_b.traits))
    child_traits: List[float] = []
    for i in range(n):
        if rng.random() < crossover_rate:
            child_traits.append(parent_a.traits[i])
        else:
            child_traits.append(parent_b.traits[i])
    # 길이 불일치 시 긴 쪽 나머지 유지
    if len(parent_a.traits) > n:
        child_traits.extend(parent_a.traits[n:])
    elif len(parent_b.traits) > n:
        child_traits.extend(parent_b.traits[n:])
    return GenomeState(traits=child_traits)


def mutate(
    genome: GenomeState,
    rate: float = 1e-4,
    scale: float = 0.1,
    rng: Optional[random.Random] = None,
) -> GenomeState:
    """변이: locus 별 독립 확률로 perturbation.
    Genome_{t+1} = mutate(Genome_t) (단순 복제) 또는
    recombine(A,B) 후 mutate 적용 (이중 재조합).
    """
    rng = rng or random.Random()
    out = [x for x in genome.traits]
    for i in range(len(out)):
        if rng.random() < rate:
            out[i] = out[i] + rng.gauss(0.0, scale)
    return GenomeState(traits=out)


__all__ = ["GenomeState", "recombine", "mutate"]
