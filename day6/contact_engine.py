"""contact_engine — Day6 조우 확률 (혼돈의 핵심 수식)

P_contact(i,j) = ρ_i * ρ_j * k_encounter * V_cell⁻¹

땅 위 같은 셀에서 종 i, j 가 물리적으로 만날 확률.
2차(quadratic) 밀도 의존 → 상호작용 쌍 수 ∝ N(N-1)/2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ContactResult:
    """한 셀(밴드) 내 조우 확률 결과."""
    p_contact_matrix: List[List[float]]  # P[i][j] i,j 종 쌍 조우율
    p_contact_scalar: float  # 전체 스칼라 요약 (예: 평균 또는 합)


class ContactEngine:
    """조우 확률 P_contact(i,j) = ρ_i ρ_j k_encounter / V_cell.
    같은 토양 셀(밴드) 내에서 종 밀도 ρ로 2차 밀도 의존.
    """
    def __init__(
        self,
        k_encounter: float = 1.0,
        V_cell: float = 1.0,
    ) -> None:
        """
        Parameters
        ----------
        k_encounter : float
            이동 속도 의존 조우율 [m²/yr].
        V_cell : float
            셀 부피(토양층 깊이 포함) 또는 무차원 정규화.
        """
        self.k_encounter = max(1e-12, k_encounter)
        self.V_cell = max(1e-12, V_cell)

    def p_contact_pair(self, rho_i: float, rho_j: float) -> float:
        """한 쌍 (i, j) 의 조우율. P_contact(i,j) = ρ_i * ρ_j * k / V."""
        return rho_i * rho_j * self.k_encounter / self.V_cell

    def compute(
        self,
        rho: List[float],
        band_idx: Optional[int] = None,
    ) -> ContactResult:
        """밀도 벡터 ρ (종별) 로 조우 확률 행렬 및 스칼라 요약 계산.

        Parameters
        ----------
        rho : List[float]
            종별 밀도 [개체/m²] (또는 바이오매스).
        band_idx : Optional[int]
            밴드 인덱스 (로깅용).

        Returns
        -------
        ContactResult
            p_contact_matrix[i][j] = P_contact(i,j), p_contact_scalar = Σ_ij P(i,j) 또는 평균.
        """
        n = len(rho)
        matrix: List[List[float]] = [[0.0] * n for _ in range(n)]
        total = 0.0
        for i in range(n):
            for j in range(n):
                p = self.p_contact_pair(rho[i], rho[j])
                matrix[i][j] = p
                total += p
        # 스칼라: 쌍 수 N(N-1)/2 가 아닌 총 조우 강도 합. 평균으로 나눌 수도 있음.
        scalar = total / max(1, n * n)
        return ContactResult(p_contact_matrix=matrix, p_contact_scalar=scalar)

    def p_contact_scalar_for_mutation(self, rho: List[float]) -> float:
        """mutation_engine.step() 에 넣을 단일 스칼라."""
        r = self.compute(rho)
        return r.p_contact_scalar


def make_contact_engine(
    k_encounter: float = 1.0,
    V_cell: float = 1.0,
) -> ContactEngine:
    return ContactEngine(k_encounter=k_encounter, V_cell=V_cell)


__all__ = ["ContactEngine", "ContactResult", "make_contact_engine"]
