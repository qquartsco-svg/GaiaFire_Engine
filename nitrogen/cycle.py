"""nitrogen/cycle.py — 질소 순환 통합 ODE (넷째날 순환 1-B)

설계 철학:
    토양 질소 N_soil 이 단 하나의 상태 변수.
    입력: 고정(fix) + 낙엽분해(decomp)
    출력: 식물흡수(uptake) + 탈질(denitrify) + 침출(leach)

수식 (DAY4_DESIGN.md):
    dN_soil/dt = N_fix + N_decomp - N_uptake - N_denitrify - N_leach

    N_uptake    = K_uptake × N_soil × GPP_rate    [g N m⁻² yr⁻¹]
    N_denitrify = K_denit × N_soil × (1 - f_O2)  [혐기성 조건]
    N_decomp    = K_decomp × N_litter × f_T × f_W  [낙엽분해]
    N_leach     = K_leach × N_soil × W_moisture   [수분 침출]

항상성:
    N_soil↑ → uptake↑ → N_soil↓  (음의 피드백)
    N_soil↓ → fix↑(pioneer↑) → N_soil↑  (복원 피드백)
    O₂=0% → denitrify↑ → N_soil↓  (혐기성 제거)

v1.0 (넷째날 순환 1-B):
    NitrogenCycle: 질소순환 통합 ODE
    NitrogenState: 질소 상태 스냅샷
    make_nitrogen_cycle(): 기본 지구 파라미터
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .fixation import NitrogenFixation, FixationResult, make_fixation_engine

# ── 속도 상수 ─────────────────────────────────────────────────────────────────

# 식물 질소 흡수
K_UPTAKE       = 0.15    # [yr⁻¹] N_soil 중 식물 흡수 분율/년
                          # 현재 지구 육상: 흡수 ~1200 Tg N/yr

# 탈질 (혐기성)
K_DENITRIFY    = 0.05    # [yr⁻¹] 혐기성 조건 탈질 속도 상수

# 낙엽 분해 → 토양 질소
K_DECOMP       = 0.3     # [yr⁻¹] 낙엽 분해 속도 (낙엽량 × K → N_soil)

# 침출 (강수에 의한 질소 손실)
K_LEACH        = 0.02    # [yr⁻¹ per unit moisture]

# 식물 질소 함량 (GPP → N_litter 변환)
N_CONTENT_PLANT = 0.015  # [g N / g 건물] 식물 질소 함량 (~1.5%)
GPP_TO_LITTER   = 0.1    # GPP 중 낙엽으로 가는 비율 (간략화)

# 토양 질소 범위
N_SOIL_MIN = 0.01        # [g N m⁻²] 최소 (영양 제한 극한)
N_SOIL_MAX = 30.0        # [g N m⁻²] 최대 (포화 상태)
N_LITTER_MAX = 50.0      # [g N m⁻²] 낙엽 최대

# O₂ 팩터 참조값
O2_REF = 0.21            # 현재 대기 O₂

EPS = 1e-30


# ── 스냅샷 ────────────────────────────────────────────────────────────────────

@dataclass
class NitrogenState:
    """질소 순환 상태 스냅샷.

    Attributes:
        time_yr:      현재 시간 [yr]
        N_soil:       토양 가용 질소 [g N m⁻²]
        N_litter:     낙엽 질소 풀 [g N m⁻²]
        N_fix:        질소고정 속도 [g N m⁻² yr⁻¹]
        N_uptake:     식물 흡수 속도 [g N m⁻² yr⁻¹]
        N_denitrify:  탈질 속도 [g N m⁻² yr⁻¹]
        N_decomp:     분해 속도 [g N m⁻² yr⁻¹]
        N_leach:      침출 속도 [g N m⁻² yr⁻¹]
        dN_soil_dt:   토양 질소 변화율 [g N m⁻² yr⁻¹]
        N_limitation: 질소 제한 팩터 [0~1] (GPP 게이트)
    """
    time_yr:     float
    N_soil:      float
    N_litter:    float
    N_fix:       float
    N_uptake:    float
    N_denitrify: float
    N_decomp:    float
    N_leach:     float
    dN_soil_dt:  float
    N_limitation: float

    def summary(self) -> str:
        return (
            f"t={self.time_yr:.0f}yr | "
            f"N_soil={self.N_soil:.3f} g/m² | "
            f"fix={self.N_fix:.4f} uptake={self.N_uptake:.4f} "
            f"denitr={self.N_denitrify:.4f} decomp={self.N_decomp:.4f} | "
            f"N_lim={self.N_limitation:.3f}"
        )


# ── NitrogenCycle ─────────────────────────────────────────────────────────────

class NitrogenCycle:
    """질소 순환 통합 ODE 시뮬레이터.

    상태 변수:
        N_soil  [g N m⁻²]  — 토양 가용 질소
        N_litter [g N m⁻²] — 낙엽/유기물 질소 풀

    사용법::

        nc = make_nitrogen_cycle(N_soil_init=2.0)

        state = nc.step(
            dt=1.0,
            B_pioneer=0.3,
            GPP_rate=5.0,      # [g C m⁻² yr⁻¹]
            O2_frac=0.21,
            T_K=293.0,
            W_moisture=0.5,
        )

        print(state.N_soil)
        print(state.N_limitation)   # → GPP 게이트로 주입
    """

    def __init__(
        self,
        N_soil_init: float = 2.0,     # [g N m⁻²] 초기 토양 질소
        N_litter_init: float = 5.0,   # [g N m⁻²] 초기 낙엽 질소
        fixation_engine: Optional[NitrogenFixation] = None,
        K_uptake: float = K_UPTAKE,
        K_denitrify: float = K_DENITRIFY,
        K_decomp: float = K_DECOMP,
        K_leach: float = K_LEACH,
        N_soil_ref: float = 8.0,       # [g N m⁻²] N_limitation = 1.0 기준점
    ):
        self.N_soil   = max(N_SOIL_MIN, N_soil_init)
        self.N_litter = max(0.0, N_litter_init)

        self._fixer = fixation_engine or make_fixation_engine()

        self.K_uptake    = K_uptake
        self.K_denitrify = K_denitrify
        self.K_decomp    = K_decomp
        self.K_leach     = K_leach
        self.N_soil_ref  = N_soil_ref

        self._time_yr = 0.0

    # ── 보조 팩터 ─────────────────────────────────────────────────────────────

    def n_limitation(self) -> float:
        """질소 제한 팩터 [0~1].

        N_soil / (N_soil + N_soil_ref) — Michaelis-Menten 포화
        → biosphere.GPP 게이트로 주입
        """
        return self.N_soil / (self.N_soil + self.N_soil_ref + EPS)

    @staticmethod
    def f_O2_denitrify(O2_frac: float) -> float:
        """탈질 O₂ 팩터.

        f_denitr = 1 - O2_frac/O2_REF  (O₂가 낮을수록 탈질 활발)
        최솟값 0 클램프.
        """
        return max(0.0, 1.0 - O2_frac / O2_REF)

    @staticmethod
    def f_T_decomp(T_K: float) -> float:
        """분해 온도 팩터 (Q10 = 2).

        f_T = Q10^((T_K - T_ref)/10)  (T_ref = 288K)
        [0.1, 3.0] 클램프
        """
        Q10 = 2.0
        T_REF = 288.0
        factor = Q10 ** ((T_K - T_REF) / 10.0)
        return max(0.1, min(3.0, factor))

    @staticmethod
    def f_W_decomp(W_moisture: float) -> float:
        """분해 수분 팩터 (최적: 0.5~0.7, 건조/포수 억제).

        포물선: f_W = 4 × W × (1 - W)  최대값 1.0 (W=0.5)
        """
        W = max(0.0, min(1.0, W_moisture))
        return 4.0 * W * (1.0 - W)

    # ── ODE step ──────────────────────────────────────────────────────────────

    def step(
        self,
        dt: float,
        B_pioneer: float,
        GPP_rate: float,
        O2_frac: float,
        T_K: float,
        W_moisture: float,
        f_thunderstorm: float = 0.1,
    ) -> NitrogenState:
        """질소 순환 1 타임스텝 (오일러 적분).

        Args:
            dt:            타임스텝 [yr]
            B_pioneer:     pioneer 식물 피복도 [0~1]
            GPP_rate:      총일차생산력 [g C m⁻² yr⁻¹]
            O2_frac:       대기 O₂ 분율
            T_K:           지표 온도 [K]
            W_moisture:    토양 수분 포화도 [0~1]
            f_thunderstorm: 뇌우 빈도 [0~1]

        Returns:
            NitrogenState
        """
        # 1. 질소고정
        fix_result = self._fixer.compute(B_pioneer, O2_frac, T_K, W_moisture, f_thunderstorm)
        N_fix = fix_result.N_fix_total

        # 2. 낙엽분해 → 토양 질소
        f_t = self.f_T_decomp(T_K)
        f_w = self.f_W_decomp(W_moisture)
        N_decomp = self.K_decomp * self.N_litter * f_t * f_w

        # 3. 식물 흡수 (N_soil × uptake × GPP 활성)
        # GPP_rate를 [0~1] 상대값으로 정규화 (기준: 100 g C m⁻² yr⁻¹)
        GPP_norm = min(1.0, max(0.0, GPP_rate / 100.0))
        N_uptake = self.K_uptake * self.N_soil * GPP_norm

        # 4. 탈질 (혐기성)
        f_denitr = self.f_O2_denitrify(O2_frac)
        N_denitrify = self.K_denitrify * self.N_soil * f_denitr

        # 5. 침출
        N_leach = self.K_leach * self.N_soil * max(0.0, W_moisture)

        # 6. 토양 질소 ODE
        dN_soil = N_fix + N_decomp - N_uptake - N_denitrify - N_leach

        # 7. 낙엽 풀 업데이트
        # 식물 흡수 질소 중 일부는 낙엽으로 환원 (GPP × N_content × litter_ratio)
        N_to_litter = GPP_rate * N_CONTENT_PLANT * GPP_TO_LITTER
        dN_litter = N_to_litter - N_decomp

        # 8. 오일러 적분
        self.N_soil   = max(N_SOIL_MIN, min(N_SOIL_MAX,   self.N_soil   + dN_soil   * dt))
        self.N_litter = max(0.0,        min(N_LITTER_MAX, self.N_litter + dN_litter * dt))
        self._time_yr += dt

        # 9. N_limitation 팩터 계산 (GPP 게이트용)
        N_lim = self.n_limitation()

        return NitrogenState(
            time_yr     = self._time_yr,
            N_soil      = self.N_soil,
            N_litter    = self.N_litter,
            N_fix       = N_fix,
            N_uptake    = N_uptake,
            N_denitrify = N_denitrify,
            N_decomp    = N_decomp,
            N_leach     = N_leach,
            dN_soil_dt  = dN_soil,
            N_limitation = N_lim,
        )

    def reset(self, N_soil: float, N_litter: float = 5.0) -> None:
        """상태 초기화."""
        self.N_soil   = max(N_SOIL_MIN, N_soil)
        self.N_litter = max(0.0, N_litter)
        self._time_yr = 0.0


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_nitrogen_cycle(
    N_soil_init: float = 2.0,
    N_litter_init: float = 5.0,
) -> NitrogenCycle:
    """기본 지구 파라미터 질소 순환기.

    Args:
        N_soil_init:   초기 토양 질소 [g N m⁻²]
            원시 토양: ~0.5, 현재 지구 목초지: ~5~15
        N_litter_init: 초기 낙엽 질소 [g N m⁻²]
    """
    return NitrogenCycle(
        N_soil_init   = N_soil_init,
        N_litter_init = N_litter_init,
    )


__all__ = [
    "NitrogenCycle",
    "NitrogenState",
    "make_nitrogen_cycle",
    "K_UPTAKE",
    "K_DENITRIFY",
    "K_DECOMP",
]
