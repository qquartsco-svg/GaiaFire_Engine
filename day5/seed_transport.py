"""seed_transport — Day5 보존형 transport 커널 (Loop F/G)

이 모듈은 위도 밴드별 스칼라 필드(예: B_seed)를
보존형 transport 법칙으로 업데이트하는 helper 를 제공한다.

핵심 방정식 (연속형에서 이산화):

    dB[i]/dt = Σ_j K[j→i] * B[j] - Σ_j K[i→j] * B[i]

여기서 K[*] 는 [1/yr] 차원의 rate 로 해석한다.
dt_yr * Σ_j K[i→j] <= 1 이면 양수성이 잘 유지된다.

Loop 연결:
    Loop F: BirdAgent.seed_flux → pioneer transport
    Loop G: BirdAgent.guano_flux → N_soil transport

latitude_bands.py 독립 기어 원칙 유지:
    - 각 밴드 BiosphereColumn은 여전히 로컬 독립 계산
    - transport 결과는 외부에서 pioneer / N_soil에 더하기
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Optional


# ── TransportKernel ───────────────────────────────────────────────────────────

@dataclass
class TransportKernel:
    """위도 밴드 간 transport 커널.

    Attributes
    ----------
    n_bands : int
        밴드 수.
    neighbors : List[List[int]]
        각 밴드가 씨드를 보낼 이웃 밴드 인덱스 목록.
    rates : List[float]
        각 밴드의 기본 이동률 [1/yr]. 길이 = n_bands.
    """

    n_bands: int
    neighbors: List[List[int]]
    rates: List[float]


# ── SeedTransport ─────────────────────────────────────────────────────────────

class SeedTransport:
    """보존형 seed transport 연산자.

    사용법::

        from solar.day5.mobility_engine import make_bird_agent
        from solar.day5.seed_transport import make_transport

        bird = make_bird_agent(n_bands=12)
        rates = bird.migration_rates()
        transport = make_transport(
            n_bands=12,
            neighbors=bird.neighbors,
            rates=rates,
        )

        B_new = transport.step(B_pioneer, dt_yr=1.0)
        N_new = transport.step_with_source(N_soil, guano_flux, dt_yr=1.0)
    """

    def __init__(self, kernel: TransportKernel) -> None:
        self.kernel = kernel

    def step(self, B: Sequence[float], dt_yr: float) -> List[float]:
        """스칼라 필드 B 를 transport 후 반환 (Loop F: 씨드).

        Parameters
        ----------
        B : Sequence[float]
            각 밴드의 양 (예: B_seed). 길이 = n_bands.
        dt_yr : float
            시간 스텝 [yr]. dt_yr * rate_i <= 1 권장.

        Returns
        -------
        List[float]
            transport 후 새 값. 총합 보존.
        """
        n         = self.kernel.n_bands
        neighbors = self.kernel.neighbors
        rates     = self.kernel.rates

        if len(B) != n:
            raise ValueError(f"len(B)={len(B)} != n_bands={n}")

        current = list(B)
        # 입력 값은 비음수가 되어야 한다 (seed/N_soil 등).
        if any(b < 0.0 for b in current):
            raise ValueError("SeedTransport.step: B contains negative values")
        delta   = [0.0] * n

        for i in range(n):
            nb = neighbors[i]
            if not nb:
                continue
            rate         = max(0.0, rates[i])
            max_fraction = min(1.0, dt_yr * rate)
            out          = max_fraction * current[i]
            if out <= 0.0:
                continue
            share = out / float(len(nb))
            delta[i] -= out
            for j in nb:
                delta[j] += share

        new_vals: List[float] = []
        for i in range(n):
            val = current[i] + delta[i]
            # 이론적으로는 val >= 0 이어야 한다.
            # 부동소수 오차를 고려해 작은 음수만 0으로 클램프하고,
            # 큰 음수는 버그로 간주해 예외를 던진다.
            if val < -1e-12:
                raise ValueError(f"SeedTransport.step: negative value at band {i}: {val}")
            new_vals.append(0.0 if val < 0.0 else val)
        return new_vals

    def step_with_source(
        self,
        B: Sequence[float],
        source: Sequence[float],
        dt_yr: float,
    ) -> List[float]:
        """transport + 외부 source 주입 (Loop G: 구아노 N).

        Parameters
        ----------
        B : Sequence[float]
            현재 필드 값 (N_soil 등).
        source : Sequence[float]
            외부 소스 flux [단위/yr] (구아노 N 등).
        dt_yr : float
            타임스텝 [yr].

        Returns
        -------
        List[float]
            transport + source 적용 후 새 값.
        """
        # transport 먼저
        B_transported = self.step(B, dt_yr)
        # source 주입
        return [B_transported[i] + source[i] * dt_yr for i in range(self.kernel.n_bands)]


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_transport(
    n_bands: int,
    neighbors: List[List[int]],
    rates: List[float],
) -> SeedTransport:
    """주어진 이웃/이동률로 SeedTransport 생성.

    Args:
        n_bands:    위도 밴드 수 (BAND_COUNT=12 권장)
        neighbors:  각 밴드의 이웃 인덱스 목록 (BirdAgent.neighbors)
        rates:      각 밴드의 이동률 [1/yr] (BirdAgent.migration_rates())
    """
    if len(neighbors) != n_bands:
        raise ValueError(f"neighbors length {len(neighbors)} != n_bands {n_bands}")
    if len(rates) != n_bands:
        raise ValueError(f"rates length {len(rates)} != n_bands {n_bands}")
    kernel = TransportKernel(n_bands=n_bands, neighbors=neighbors, rates=rates)
    return SeedTransport(kernel)


__all__ = [
    "TransportKernel",
    "SeedTransport",
    "make_transport",
]
