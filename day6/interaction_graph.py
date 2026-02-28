"""interaction_graph — Day6 포식·경쟁 네트워크

종 간 포식/피식, 경쟁 관계를 그래프로 표현.
ContactEngine 의 P_contact(i,j) 와 연동하여 상호작용 강도 제공.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional


@dataclass
class InteractionGraph:
    """종 간 상호작용: 포식 행렬 A[s][s'], 경쟁 행렬 C[s][s'].
    A[i][j] > 0: i 가 j 를 포식.
    C[i][j] > 0: i 와 j 가 자원 경쟁.
    """
    n_species: int
    predation: List[List[float]]  # A[s][s']
    competition: List[List[float]]  # C[s][s']

    def predators_of(self, species_idx: int) -> List[Tuple[int, float]]:
        """species_idx 를 먹는 종 목록 (인덱스, 강도)."""
        return [
            (i, self.predation[i][species_idx])
            for i in range(self.n_species)
            if self.predation[i][species_idx] > 0
        ]

    def competitors_of(self, species_idx: int) -> List[Tuple[int, float]]:
        """species_idx 와 경쟁하는 종 목록."""
        return [
            (i, self.competition[i][species_idx])
            for i in range(self.n_species)
            if i != species_idx and self.competition[i][species_idx] > 0
        ]


def make_interaction_graph(
    n_species: int = 4,
    predation: Optional[List[List[float]]] = None,
    competition: Optional[List[List[float]]] = None,
) -> InteractionGraph:
    """기본 삼각형 먹이망 등 스켈레톤 그래프."""
    if predation is None:
        predation = [[0.0] * n_species for _ in range(n_species)]
    if competition is None:
        competition = [[0.01 if i != j else 0.0 for j in range(n_species)] for i in range(n_species)]
    return InteractionGraph(n_species=n_species, predation=predation, competition=competition)


__all__ = ["InteractionGraph", "make_interaction_graph"]
