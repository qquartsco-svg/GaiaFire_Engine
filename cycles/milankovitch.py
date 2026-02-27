"""cycles/milankovitch.py — Milankovitch 3주기 해석적 계산 (넷째날 순환 2-A)

설계 철학:
    "장주기 드라이버가 단주기 항상성에 파동을 만든다"
    세차(26kyr) + 경사(41kyr) + 이심률(100kyr/413kyr) 중첩
    → 계절성 진폭 진동 → 빙하기-간빙기 자연 창발

물리 근거 (Berger 1978):
    이심률:  e(t) = e₀ + Σ aᵢ cos(λᵢt + φᵢ)   주기 ~100kyr, 413kyr
    경사각:  ε(t) = ε₀ + Σ bᵢ cos(μᵢt + ψᵢ)   주기 ~41kyr
    세차:    ψ(t) = ψ₀ + Ωt + Σ cᵢ sin(νᵢt + χᵢ) 주기 ~26kyr

    지구 실제값 (Berger & Loutre 1991):
      e: 0.0167 (현재) ~ [0.001, 0.058] 범위
      ε: 23.44° (현재) ~ [22.1°, 24.5°] 범위, 주기 41kyr
      ψ: 세차운동 주기 ~25.7kyr (evolution_engine과 동일)

GaiaLoopConnector 연결 포인트:
    milankovitch.obliquity(t_yr) → GaiaLoopConnector.make_fire_env(obliquity_deg)
    milankovitch.eccentricity(t_yr) → FireEnvSnapshot.F0 보정
    milankovitch.insolation_scale(t_yr, phi) → fire_risk 입력 F_solar 보정

항상성 의미:
    e↑ → 근일점 일사량↑ → 북반구 여름↑ → 빙하기 탈출 (Milankovitch 가설)
    ε↑ → 계절성↑ → 여름 고위도 일사량↑ → 빙하 융해 촉진
    ψ → 근일점 계절 위치 결정 → 현재 북반구 겨울에 근일점

단순화 원칙:
    Berger 원논문의 26개 주기 항목을 주요 3~4개 항으로 단순화
    → 관측 진폭 ±10% 오차 허용
    → 계산 속도 최우선 (매 yr 스텝에서 호출)

v1.0 (넷째날 순환 2-A):
    MilankovitchCycle: 해석적 3주기 계산기
    MilankovitchState: 매 스텝 스냅샷
    make_earth_cycle(): 지구 기본 파라미터 세트
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# ── 물리 상수 ─────────────────────────────────────────────────────────────────

# 지구 현재값 (J2000 기준)
E0_EARTH       = 0.0167   # 현재 이심률
EPS0_EARTH_DEG = 23.44    # 현재 경사각 [deg]
PSI0_EARTH_DEG = 102.94   # 현재 근일점 경도 [deg]

# 진폭 클램프
E_MIN, E_MAX        = 0.001, 0.058    # 이심률 물리 범위
EPS_MIN, EPS_MAX    = 22.0, 24.5      # 경사각 물리 범위 [deg]

EPS = 1e-30

# ── Berger 1978 주요 항목 (단순화 버전) ──────────────────────────────────────
#
# 이심률 주기 항 (Berger 1978 Table 1, 상위 3개):
#   (진폭, 주기[yr], 위상[deg])
ECCENTRICITY_TERMS: List[Tuple[float, float, float]] = [
    (0.0116,  95_000.0,    0.0),   # ~100kyr 주 주기
    (0.0100, 413_000.0,   90.0),   # ~413kyr 장주기
    (0.0040,  54_000.0,  180.0),   # ~54kyr 단주기
]

# 경사각 주기 항 (Berger 1978 Table 4, 상위 3개):
#   (진폭[deg], 주기[yr], 위상[deg])
OBLIQUITY_TERMS: List[Tuple[float, float, float]] = [
    (1.32,  41_000.0,   0.0),   # ~41kyr 주 주기
    (0.74,  54_000.0,  60.0),   # ~54kyr
    (0.29,  29_000.0, 120.0),   # ~29kyr
]

# 세차 주기 항 (precession index: e × sin(ψ), Berger 1978 Table 6):
#   (진폭, 주기[yr], 위상[deg])
PRECESSION_TERMS: List[Tuple[float, float, float]] = [
    (0.0199,  23_700.0,   0.0),   # ~23.7kyr
    (0.0166,  22_400.0,  60.0),   # ~22.4kyr
    (0.0072,  18_900.0, 120.0),   # ~18.9kyr
]


# ── 스냅샷 ────────────────────────────────────────────────────────────────────

@dataclass
class MilankovitchState:
    """매 스텝 Milankovitch 궤도 파라미터 스냅샷.

    Attributes:
        time_yr: 현재 시간 [yr] (0 = J2000 현재)
        eccentricity: 이심률 e [0, 1)
        obliquity_deg: 황도경사각 ε [deg]
        precession_index: e × sin(ψ) [세차 강도 지표, -0.06~+0.06]
        longitude_perihelion_deg: 근일점 경도 ψ [deg]
        insolation_W365: 연평균 전지구 일사량 [W/m²] (태양상수 기준)
        season_amplitude: 계절성 진폭 지표 [0~1]
            = ε × e (경사 × 이심률 교차항, 빙하기 민감도)
        obliquity_scale: GaiaLoopConnector.Loop C에 주입할 배율
            = 1.0 + K_OBLIQ × (obliquity_deg - 23.5) / 23.5
    """
    time_yr: float
    eccentricity: float
    obliquity_deg: float
    precession_index: float
    longitude_perihelion_deg: float
    insolation_W365: float
    season_amplitude: float
    obliquity_scale: float

    def summary(self) -> str:
        return (
            f"t={self.time_yr/1000:.1f}kyr | "
            f"e={self.eccentricity:.4f} "
            f"ε={self.obliquity_deg:.2f}° "
            f"e×sinψ={self.precession_index:+.4f} | "
            f"insol={self.insolation_W365:.1f}W/m² "
            f"season_amp={self.season_amplitude:.4f} "
            f"obliq_scale={self.obliquity_scale:.4f}"
        )


# ── MilankovitchCycle ─────────────────────────────────────────────────────────

class MilankovitchCycle:
    """Milankovitch 3주기 해석적 계산기.

    사용법::

        cycle = make_earth_cycle()

        # 단일 시점
        state = cycle.state(t_yr=0.0)       # 현재 (J2000)
        state = cycle.state(t_yr=-21_000)   # 21kyr 전 (마지막 빙하 최성기)
        state = cycle.state(t_yr=100_000)   # 10만 년 후

        # GaiaLoopConnector 연결
        obliquity = cycle.obliquity(t_yr)
        env = connector.make_fire_env(base_env, obliquity_deg=obliquity)

        # 시계열
        series = cycle.time_series(t_start=-200_000, t_end=0, dt=1000)

    부호 규약:
        t_yr > 0: 미래 (현재에서 t_yr년 뒤)
        t_yr < 0: 과거 (현재에서 |t_yr|년 전)
        t_yr = 0: J2000 현재
    """

    def __init__(
        self,
        e0: float = E0_EARTH,
        eps0_deg: float = EPS0_EARTH_DEG,
        psi0_deg: float = PSI0_EARTH_DEG,
        eccentricity_terms: Optional[List[Tuple[float, float, float]]] = None,
        obliquity_terms: Optional[List[Tuple[float, float, float]]] = None,
        precession_terms: Optional[List[Tuple[float, float, float]]] = None,
        F0: float = 1361.0,
        obliq_scale_K: float = 0.8,
    ):
        """
        Args:
            e0: 현재 이심률 기준값
            eps0_deg: 현재 경사각 기준값 [deg]
            psi0_deg: 현재 근일점 경도 기준값 [deg]
            eccentricity_terms: [(진폭, 주기yr, 위상deg), ...]
            obliquity_terms: [(진폭deg, 주기yr, 위상deg), ...]
            precession_terms: [(진폭, 주기yr, 위상deg), ...]
            F0: 태양상수 기준값 [W/m²]
            obliq_scale_K: Loop C 연결 obliquity_scale 감도
        """
        self.e0     = e0
        self.eps0   = eps0_deg
        self.psi0   = psi0_deg
        self.F0     = F0
        self.K_obliq = obliq_scale_K

        self._ecc_terms  = eccentricity_terms or ECCENTRICITY_TERMS
        self._obl_terms  = obliquity_terms    or OBLIQUITY_TERMS
        self._prec_terms = precession_terms   or PRECESSION_TERMS

    # ── 핵심 계산 ─────────────────────────────────────────────────────────────

    def eccentricity(self, t_yr: float) -> float:
        """이심률 e(t) [0, 1).

        e(t) = e₀ + Σ aᵢ cos(2πt/Tᵢ + φᵢ)
        """
        e = self.e0
        for amp, period, phase_deg in self._ecc_terms:
            phi = math.radians(phase_deg)
            e += amp * math.cos(2.0 * math.pi * t_yr / period + phi)
        return max(E_MIN, min(E_MAX, e))

    def obliquity(self, t_yr: float) -> float:
        """황도경사각 ε(t) [deg].

        ε(t) = ε₀ + Σ bᵢ cos(2πt/Tᵢ + ψᵢ)
        """
        eps = self.eps0
        for amp, period, phase_deg in self._obl_terms:
            phi = math.radians(phase_deg)
            eps += amp * math.cos(2.0 * math.pi * t_yr / period + phi)
        return max(EPS_MIN, min(EPS_MAX, eps))

    def precession_index(self, t_yr: float) -> float:
        """세차 지표 e(t) × sin(ψ(t)).

        = Σ cᵢ sin(2πt/Tᵢ + χᵢ)
        """
        p = 0.0
        for amp, period, phase_deg in self._prec_terms:
            phi = math.radians(phase_deg)
            p += amp * math.sin(2.0 * math.pi * t_yr / period + phi)
        return p

    def longitude_perihelion(self, t_yr: float) -> float:
        """근일점 경도 ψ(t) [deg, 0~360).

        세차 지표와 이심률로 근사:
          sin(ψ) ≈ precession_index / e
        """
        e = self.eccentricity(t_yr)
        p = self.precession_index(t_yr)
        if e < EPS:
            return self.psi0
        sin_psi = max(-1.0, min(1.0, p / e))
        psi_rad = math.asin(sin_psi)
        psi_deg = math.degrees(psi_rad) % 360.0
        return psi_deg

    def insolation_annual_mean(self, t_yr: float) -> float:
        """연평균 전지구 일사량 [W/m²].

        Q̄ = F₀/4 × (1 - e²)^(-1/2)  (케플러 타원 적분)

        이심률이 클수록 연평균 일사량이 약간 증가.
        """
        e = self.eccentricity(t_yr)
        return self.F0 / 4.0 / math.sqrt(max(1.0 - e * e, EPS))

    def insolation_summer_solstice(self, t_yr: float, phi_deg: float) -> float:
        """하지점 일일 평균 일사량 Q_ss(t, φ) [W/m²].

        Berger 1978 / Laskar 2004 표준 공식:
          Q_ss = (F₀/π) × (a/r_ss)² × (H₀ sin φ sin ε + cos φ cos ε sin H₀)

        여기서:
          r_ss: 하지 태양-지구 거리 (궤도 방정식)
          H₀  : 일출/일몰 시간각 cos H₀ = -tan φ tan ε → 극권 보정
          (a/r)² = (1 - e cos E)^-2 ≈ (1 + e_prec) × 보정항

        근사: (a/r_ss)² ≈ (1 - e sin(ψ-90°))^-2 (세차 보정)
              현재 지구 ψ≈103° → 하지(90°) ≈ 원일점측 → 일사량 약함
        """
        e   = self.eccentricity(t_yr)
        eps = self.obliquity(t_yr)
        psi = self.longitude_perihelion(t_yr)

        # 하지 진근점이각: 하지(황경 90°) 기준
        # (a/r)² = (1 + e·cos(v))² / (1-e²)²
        # 하지에서 진근점이각 v_ss = 90° - ψ (근일점 기준)
        v_ss_rad = math.radians(90.0 - psi)
        one_minus_e2 = max(1.0 - e * e, EPS)
        # (a/r_ss)^2
        r_factor = ((1.0 + e * math.cos(v_ss_rad)) ** 2) / (one_minus_e2 ** 2)

        # 위도 φ, 경사각 ε (라디안 변환)
        phi_rad = math.radians(abs(phi_deg))
        eps_rad = math.radians(eps)

        # 시간각 H₀: cos H₀ = -tan φ tan ε (극권 클램프)
        cos_H0 = -math.tan(phi_rad) * math.tan(eps_rad)
        if cos_H0 >= 1.0:
            # 극야 (일출 없음) → Q = 0
            return 0.0
        elif cos_H0 <= -1.0:
            # 백야 (24시간 낮) → H₀ = π
            H0 = math.pi
        else:
            H0 = math.acos(cos_H0)

        sin_phi = math.sin(phi_rad)
        cos_phi = math.cos(phi_rad)
        sin_eps = math.sin(eps_rad)
        cos_eps = math.cos(eps_rad)

        # 하루 평균 일사량 공식
        Q_ss = (self.F0 / math.pi) * r_factor * (
            H0 * sin_phi * sin_eps + cos_phi * cos_eps * math.sin(H0)
        )
        return max(0.0, Q_ss)

    def season_amplitude(self, t_yr: float) -> float:
        """계절성 진폭 지표 [0~1].

        = (ε/EPS_MAX) × (1 + e) / 2
        ε↑ → 계절성↑, e↑ → 이심률 강화
        빙하기 민감도 지표.
        """
        eps = self.obliquity(t_yr)
        e   = self.eccentricity(t_yr)
        return ((eps - EPS_MIN) / (EPS_MAX - EPS_MIN)) * (1.0 + e) / 2.0

    def obliquity_scale(self, t_yr: float) -> float:
        """GaiaLoopConnector.Loop C 주입용 배율.

        = 1.0 + K × (ε - 23.5°) / 23.5°
        [0.5, 2.0] 클램프
        """
        eps = self.obliquity(t_yr)
        ref = 23.5
        scale = 1.0 + self.K_obliq * (eps - ref) / ref
        return max(0.5, min(2.0, scale))

    # ── 통합 스냅샷 ───────────────────────────────────────────────────────────

    def state(self, t_yr: float) -> MilankovitchState:
        """특정 시점의 전체 Milankovitch 상태 스냅샷."""
        e     = self.eccentricity(t_yr)
        eps   = self.obliquity(t_yr)
        p_idx = self.precession_index(t_yr)
        psi   = self.longitude_perihelion(t_yr)
        insol = self.insolation_annual_mean(t_yr)
        s_amp = self.season_amplitude(t_yr)
        o_scl = self.obliquity_scale(t_yr)

        return MilankovitchState(
            time_yr                  = t_yr,
            eccentricity             = e,
            obliquity_deg            = eps,
            precession_index         = p_idx,
            longitude_perihelion_deg = psi,
            insolation_W365          = insol,
            season_amplitude         = s_amp,
            obliquity_scale          = o_scl,
        )

    def time_series(
        self,
        t_start: float,
        t_end: float,
        dt: float = 1000.0,
    ) -> List[MilankovitchState]:
        """시간 범위에 대한 시계열 계산.

        Args:
            t_start: 시작 시간 [yr] (음수 = 과거)
            t_end: 끝 시간 [yr]
            dt: 시간 간격 [yr]

        Returns:
            List[MilankovitchState]
        """
        states = []
        t = t_start
        while t <= t_end + dt * 0.5:
            states.append(self.state(t))
            t += dt
        return states

    # ── 빙하기 판단 ───────────────────────────────────────────────────────────

    def is_glacial(
        self,
        t_yr: float,
        insolation_threshold: float = 480.0,
        phi_deg: float = 65.0,
    ) -> bool:
        """현재 시점이 빙하기 진입 조건인지 판단.

        Milankovitch 가설: 북위 65° 하지 일사량이 임계값 이하 → 빙하기.

        Args:
            insolation_threshold: 빙하기 임계 일사량 [W/m²]
                480 W/m² = 현재 지구 65°N 하지 일사량(~534) 대비 ~10% 감소 기준
            phi_deg: 판단 기준 위도 (고위도 빙하 형성 지점)

        Returns:
            True = 빙하기 조건
        """
        Q = self.insolation_summer_solstice(t_yr, phi_deg)
        return Q < insolation_threshold


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_earth_cycle(obliq_scale_K: float = 0.8) -> MilankovitchCycle:
    """지구 Milankovitch 파라미터 기본 세트.

    Berger & Loutre 1991 기준 단순화 버전.
    """
    return MilankovitchCycle(
        e0          = E0_EARTH,
        eps0_deg    = EPS0_EARTH_DEG,
        psi0_deg    = PSI0_EARTH_DEG,
        F0          = 1361.0,
        obliq_scale_K = obliq_scale_K,
    )


def make_custom_cycle(
    e0: float,
    eps0_deg: float,
    F0: float = 1361.0,
) -> MilankovitchCycle:
    """다른 행성이나 변형 조건용 커스텀 사이클."""
    return MilankovitchCycle(e0=e0, eps0_deg=eps0_deg, F0=F0)


__all__ = [
    "MilankovitchCycle",
    "MilankovitchState",
    "make_earth_cycle",
    "make_custom_cycle",
    "ECCENTRICITY_TERMS",
    "OBLIQUITY_TERMS",
    "PRECESSION_TERMS",
]
