"""stress_accumulator.py — 시간 스케일 번역기 + 스트레스 적산기 (v1.2)

핵심 문제:
  뉴런(ms) ↔ 행성(yr) 직접 연결 불가.
  뉴런의 스트레스 신호가 쌓여서 행성 산불 압력이 되려면
  "적산(Accumulation) + 스케일 변환" 레이어가 필요하다.

해결 구조:
  3단계 적산 파이프라인

  Level 1 — 뉴런/세포 스케일 (ms ~ s)
    CO2_pulse(t)    : 뉴런 발화 시 CO₂ 방출 이벤트 [μmol/s]
    Heat_pulse(t)   : 발화 열 방출 [mW]
    → 적산 → Cell_stress_score [0~1] (s 단위 평균)

  Level 2 — 기관/뇌 스케일 (s ~ hr)
    cell_stress[]   : 다수 뉴런 집합 스트레스
    → 적산 → Organ_fatigue [0~1] (수면주기 단위 평균)
    → cortisol_equivalent [0~1]

  Level 3 — 행성 스케일 (hr ~ yr)
    organ_fatigue[] : 생명체/생태계 전체 스트레스
    → 적산 → Planet_stress_index [0~1]
    → ForgetEngine + FireEngine 입력으로 주입

설계 원칙:
  각 레벨은 지수이동평균(EMA) + 임계 초과 누적으로 구현
  → "서서히 쌓이다가 임계 초과 시 폭발" = 산불 ODE와 동일 구조
  → EMA 감쇠 = "망각 없으면 스트레스도 안 사라짐"

수학적 핵심:
  S(t+dt) = S(t) × (1 - dt/τ) + input(t) × dt   ← 지수 감쇠 적산
  excess  = max(0, S - S_th)                       ← 임계 초과
  output  = K × excess²                            ← 비선형 증폭 (= 산불 ODE)

  τ (시정수):
    Level 1: τ_cell    = 0.1  s   (뉴런 회복 시간)
    Level 2: τ_organ   = 3600 s   (1시간, 코르티솔 반감기)
    Level 3: τ_planet  = 3e7  s   (1년, 생태계 회복)
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import deque

EPS = 1e-30

# ── 시정수 (각 레벨별 감쇠 속도) ─────────────────────────────────────────────
TAU_CELL_S      = 0.1        # [s] 뉴런 회복 (100ms)
TAU_ORGAN_S     = 3600.0     # [s] 기관 피로 (1hr, 코르티솔 반감기)
TAU_PLANET_S    = 3.156e7    # [s] 행성 복원 (1yr)

# 시간 단위 변환
MS_TO_S   = 1e-3
S_TO_HR   = 1.0 / 3600.0
HR_TO_YR  = 1.0 / 8760.0

# 임계값
S_TH_CELL   = 0.3   # 세포 스트레스 임계
S_TH_ORGAN  = 0.4   # 기관 피로 임계
S_TH_PLANET = 0.5   # 행성 스트레스 임계

# 증폭 계수
K_CELL   = 2.0
K_ORGAN  = 1.5
K_PLANET = 1.0


# ── NeuronEvent ───────────────────────────────────────────────────────────────

@dataclass
class NeuronEvent:
    """뉴런 발화 이벤트 — Level 1 입력.

    뉴런 모델(CookiieBrain)에서 받아오는 단일 이벤트.
    """
    time_ms:      float   # 발화 시각 [ms]
    co2_umol_s:   float   # CO₂ 방출률 [μmol/s]
    heat_mw:      float   # 열 방출 [mW]
    atp_consumed: float   # ATP 소비 [0~1 정규화]
    neuron_id:    int = 0

    @classmethod
    def from_metabolic(cls, time_ms: float, atp_consumed: float,
                        neuron_id: int = 0) -> "NeuronEvent":
        """ATP 소비량만 알 때 나머지 추정 (CookiieBrain MetabolicFeedback 연결)."""
        co2  = atp_consumed * 8.0    # ATP 1 → CO₂ ~8 μmol/s (추정)
        heat = atp_consumed * 20.0   # ATP 1 → heat ~20 mW
        return cls(time_ms=time_ms, co2_umol_s=co2,
                   heat_mw=heat, atp_consumed=atp_consumed,
                   neuron_id=neuron_id)


# ── Level 1: CellStressState ──────────────────────────────────────────────────

@dataclass
class CellStressState:
    """뉴런 집합의 세포 스트레스 상태 [s 단위].

    여러 NeuronEvent를 지수이동평균으로 적산한 결과.
    """
    time_s:        float
    co2_ema:       float   # [μmol/s] CO₂ 지수이동평균
    heat_ema:      float   # [mW] 열 지수이동평균
    atp_ema:       float   # [0~1] ATP 소비 지수이동평균
    stress_score:  float   # [0~1] 종합 세포 스트레스
    excess:        float   # [0~1] 임계 초과량


# ── Level 2: OrganFatigueState ────────────────────────────────────────────────

@dataclass
class OrganFatigueState:
    """뇌/기관 피로 상태 [hr 단위].

    CellStressState들을 1시간 단위 코르티솔 등가값으로 변환.
    """
    time_hr:           float
    cell_stress_avg:   float   # [0~1] 시간 평균 세포 스트레스
    fatigue_ema:       float   # [0~1] 기관 피로 지수이동평균
    cortisol_equiv:    float   # [0~1] 코르티솔 등가값
    atp_depletion:     float   # [0~1] ATP 고갈 정도
    pruning_pressure:  float   # [0~1] 망각 압력 → ForgetEngine 입력


# ── Level 3: PlanetStressIndex ────────────────────────────────────────────────

@dataclass
class PlanetStressIndex:
    """행성 스트레스 지수 [yr 단위].

    OrganFatigueState들을 연 단위 생태계 스트레스로 변환.
    → FireEngine의 O2_frac 보정값 또는 fuel_provider 입력으로 사용.
    """
    time_yr:            float
    organ_fatigue_avg:  float   # [0~1] 기관 피로 평균
    planet_stress_ema:  float   # [0~1] 행성 스트레스 지수이동평균
    fire_pressure:      float   # [0~1] 산불 압력 → FireEngine 입력
    O2_stress_offset:   float   # [mol/mol] O₂ 교란량 (행성 대기 스트레스)
    co2_accumulated:    float   # [ppm] 누적 CO₂ 증가분


# ── StressAccumulator ─────────────────────────────────────────────────────────

class StressAccumulator:
    """3단계 시간 스케일 번역기.

    뉴런(ms) → 기관(hr) → 행성(yr) 스트레스 적산.

    사용:
        acc = StressAccumulator()

        # Level 1: 뉴런 이벤트 주입 (ms 단위)
        acc.push_neuron_event(NeuronEvent.from_metabolic(
            time_ms=100.0, atp_consumed=0.8
        ))

        # Level 2: 기관 피로 업데이트 (hr 단위)
        organ = acc.update_organ(time_hr=1.0)

        # Level 3: 행성 스트레스 변환 (yr 단위)
        planet = acc.update_planet(time_yr=0.001)

        # ForgetEngine 입력 생성
        brain = acc.to_brain_snapshot(time_hr=14.0)

        # FireEngine 입력 보정
        delta_O2 = acc.to_fire_delta_O2()
    """

    def __init__(self, tau_cell: float = TAU_CELL_S,
                 tau_organ: float = TAU_ORGAN_S,
                 tau_planet: float = TAU_PLANET_S):
        self.tau_cell   = tau_cell
        self.tau_organ  = tau_organ
        self.tau_planet = tau_planet

        # Level 1 내부 상태
        self._co2_ema   = 0.0
        self._heat_ema  = 0.0
        self._atp_ema   = 0.0
        self._last_time_s = 0.0

        # Level 2 내부 상태
        self._fatigue_ema      = 0.0
        self._cortisol_ema     = 0.0
        self._cell_stress_buf: deque = deque(maxlen=3600)  # 1hr 버퍼
        self._last_organ_hr    = 0.0

        # Level 3 내부 상태
        self._planet_ema        = 0.0
        self._co2_accumulated   = 0.0
        self._organ_buf: deque  = deque(maxlen=8760)  # 1yr 버퍼
        self._last_planet_yr    = 0.0

        # 히스토리
        self.cell_history:   List[CellStressState]   = []
        self.organ_history:  List[OrganFatigueState] = []
        self.planet_history: List[PlanetStressIndex] = []

    # ── Level 1: 뉴런 이벤트 → 세포 스트레스 ───────────────────────────────

    def push_neuron_event(self, event: NeuronEvent) -> CellStressState:
        """뉴런 이벤트 → 지수이동평균으로 세포 스트레스 업데이트.

        S(t+dt) = S(t) × exp(-dt/τ) + input × (1 - exp(-dt/τ))
        """
        t_s  = event.time_ms * MS_TO_S
        dt_s = max(EPS, t_s - self._last_time_s)
        self._last_time_s = t_s

        # 지수 감쇠 계수
        alpha = 1.0 - math.exp(-dt_s / self.tau_cell)

        # EMA 업데이트
        self._co2_ema  = self._co2_ema  * (1 - alpha) + event.co2_umol_s  * alpha
        self._heat_ema = self._heat_ema * (1 - alpha) + event.heat_mw     * alpha
        self._atp_ema  = self._atp_ema  * (1 - alpha) + event.atp_consumed * alpha

        # 종합 세포 스트레스 (정규화)
        co2_norm  = min(1.0, self._co2_ema  / 8.0)   # 최대 8 μmol/s
        heat_norm = min(1.0, self._heat_ema / 20.0)  # 최대 20 mW
        stress    = (co2_norm + heat_norm + self._atp_ema) / 3.0

        # 임계 초과 (= 산불 ODE의 O₂ 임계 초과와 동일)
        excess = K_CELL * max(0.0, stress - S_TH_CELL) ** 2

        state = CellStressState(
            time_s       = t_s,
            co2_ema      = self._co2_ema,
            heat_ema     = self._heat_ema,
            atp_ema      = self._atp_ema,
            stress_score = stress,
            excess       = min(1.0, excess),
        )
        self._cell_stress_buf.append(stress)
        self.cell_history.append(state)
        return state

    # ── Level 2: 세포 스트레스 → 기관 피로 ──────────────────────────────────

    def update_organ(self, time_hr: float) -> OrganFatigueState:
        """버퍼의 세포 스트레스 평균 → 기관 피로 + 코르티솔 등가값.

        dt_s = (time_hr - last_hr) × 3600
        S_organ(t+dt) = S_organ(t) × exp(-dt/τ_organ) + cell_avg × alpha
        """
        dt_hr = max(EPS, time_hr - self._last_organ_hr)
        self._last_organ_hr = time_hr
        dt_s  = dt_hr * 3600.0

        # 버퍼 평균 (최근 세포 스트레스)
        cell_avg = (sum(self._cell_stress_buf) /
                    max(1, len(self._cell_stress_buf)))

        alpha = 1.0 - math.exp(-dt_s / self.tau_organ)
        self._fatigue_ema  = (self._fatigue_ema  * (1 - alpha)
                              + cell_avg          * alpha)
        self._cortisol_ema = (self._cortisol_ema * (1 - alpha)
                              + cell_avg * 1.2    * alpha)  # 코르티솔 약간 증폭

        # ATP 고갈 = fatigue의 역방향
        atp_depletion = min(1.0, self._fatigue_ema * 1.5)

        # 망각 압력 = 임계 초과 비선형
        excess_organ = K_ORGAN * max(0.0, self._fatigue_ema - S_TH_ORGAN) ** 2
        pruning_pressure = min(1.0, excess_organ)

        state = OrganFatigueState(
            time_hr          = time_hr,
            cell_stress_avg  = cell_avg,
            fatigue_ema      = self._fatigue_ema,
            cortisol_equiv   = min(1.0, self._cortisol_ema),
            atp_depletion    = atp_depletion,
            pruning_pressure = pruning_pressure,
        )
        self._organ_buf.append(self._fatigue_ema)
        self.organ_history.append(state)
        return state

    # ── Level 3: 기관 피로 → 행성 스트레스 ──────────────────────────────────

    def update_planet(self, time_yr: float) -> PlanetStressIndex:
        """기관 피로 → 행성 스트레스 지수 + O₂ 교란량.

        행성 시정수 τ_planet = 1yr
        CO₂ 누적 = 기관 피로 × 변환 계수 [ppm/yr]
        """
        dt_yr = max(EPS, time_yr - self._last_planet_yr)
        self._last_planet_yr = time_yr
        dt_s  = dt_yr * TAU_PLANET_S

        organ_avg = (sum(self._organ_buf) /
                     max(1, len(self._organ_buf)))

        alpha = 1.0 - math.exp(-dt_s / self.tau_planet)
        self._planet_ema = (self._planet_ema * (1 - alpha)
                            + organ_avg       * alpha)

        # 산불 압력 (= 행성 레벨 fire_risk 보정값)
        excess_planet = K_PLANET * max(0.0, self._planet_ema - S_TH_PLANET) ** 2
        fire_pressure = min(1.0, excess_planet)

        # O₂ 교란량 — 생명체 스트레스가 O₂ 소비를 증가시킴
        # 단위: [mol/mol] — FireEngine의 O2_frac에 더해서 산불 압력 증가
        O2_stress_offset = fire_pressure * 0.02  # 최대 2% O₂ 변화

        # CO₂ 누적 — 적산
        self._co2_accumulated += organ_avg * 5.0 * dt_yr  # 최대 5ppm/yr

        state = PlanetStressIndex(
            time_yr           = time_yr,
            organ_fatigue_avg = organ_avg,
            planet_stress_ema = self._planet_ema,
            fire_pressure     = fire_pressure,
            O2_stress_offset  = O2_stress_offset,
            co2_accumulated   = self._co2_accumulated,
        )
        self.planet_history.append(state)
        return state

    # ── 출력: ForgetEngine / FireEngine 입력 생성 ─────────────────────────────

    def to_brain_snapshot(self, time_hr: float = 14.0):
        """현재 적산 상태 → CognitiveBrainSnapshot (ForgetEngine 입력).

        기관 피로 → cortisol_global, atp_global 매핑.
        """
        try:
            from forget_engine import CognitiveBrainSnapshot
        except ImportError:
            from .forget_engine import CognitiveBrainSnapshot

        organ = self.organ_history[-1] if self.organ_history else None
        cortisol = organ.cortisol_equiv   if organ else 0.2
        atp      = 1.0 - (organ.atp_depletion if organ else 0.0)
        load_raw = organ.fatigue_ema      if organ else 0.3

        return CognitiveBrainSnapshot(
            memory_load_global = min(1.0, load_raw),
            cortisol_global    = cortisol,
            atp_global         = max(0.0, atp),
            time_hr            = time_hr,
        )

    def to_fire_env_patch(self, base_O2: float = 0.21,
                          base_CO2: float = 400.0):
        """현재 적산 상태 → FireEnvSnapshot 보정값 딕셔너리.

        행성 스트레스 → O2_frac / CO2_ppm 보정.
        FireEnvSnapshot 생성 시 이 값을 더해서 사용:
            env = FireEnvSnapshot(
                O2_frac = base_O2 + patch["O2_offset"],
                CO2_ppm = base_CO2 + patch["CO2_offset"],
            )
        """
        planet = self.planet_history[-1] if self.planet_history else None
        O2_offset  = planet.O2_stress_offset if planet else 0.0
        CO2_offset = planet.co2_accumulated  if planet else 0.0

        return {
            "O2_offset":    O2_offset,
            "CO2_offset":   CO2_offset,
            "fire_pressure": planet.fire_pressure if planet else 0.0,
            "O2_frac_patched": base_O2 + O2_offset,
            "CO2_ppm_patched": base_CO2 + CO2_offset,
        }

    def summary(self) -> Dict[str, float]:
        """현재 전체 적산 상태 요약."""
        cell   = self.cell_history[-1]   if self.cell_history   else None
        organ  = self.organ_history[-1]  if self.organ_history  else None
        planet = self.planet_history[-1] if self.planet_history else None
        return {
            "L1_cell_stress":    cell.stress_score       if cell   else 0.0,
            "L2_fatigue":        organ.fatigue_ema        if organ  else 0.0,
            "L2_cortisol":       organ.cortisol_equiv     if organ  else 0.0,
            "L2_pruning_press":  organ.pruning_pressure   if organ  else 0.0,
            "L3_planet_stress":  planet.planet_stress_ema if planet else 0.0,
            "L3_fire_pressure":  planet.fire_pressure     if planet else 0.0,
            "L3_O2_offset":      planet.O2_stress_offset  if planet else 0.0,
            "L3_CO2_acc":        planet.co2_accumulated   if planet else 0.0,
        }


# ── LocalFireReset ────────────────────────────────────────────────────────────

class LocalFireReset:
    """산불 발생 시 해당 위도 밴드 B_wood 국소 리셋 + 스트레스 초기화.

    산불 = 망각: 특정 구역의 바이오매스(기억)를 초기화하여
    새 생장(새 학습) 공간을 만드는 메커니즘.

    사용:
        resetter = LocalFireReset(accumulator)
        new_eco  = resetter.apply(band_idx=6, eco=current_eco,
                                  fire_risk=0.8, dt_yr=1.0)
    """

    # 산불 소각률: fire_risk 1.0 → 1년에 B_wood의 최대 60% 소각
    MAX_BURN_FRACTION = 0.60
    # 낙엽 소각률: 목본보다 더 쉽게 탐
    ORGANIC_BURN_MULT = 1.5
    # 최소 잔존 B_wood (완전 멸종 방지)
    MIN_B_WOOD = 0.01

    def __init__(self, accumulator: Optional[StressAccumulator] = None):
        self.accumulator = accumulator
        self.reset_log: List[Dict] = []   # 리셋 이력 (감사 로그)

    def apply(self, band_idx: int, B_wood: float, organic: float,
              fire_risk: float, dt_yr: float = 1.0) -> Tuple[float, float, Dict]:
        """산불 위험도에 따라 B_wood/organic 국소 소각.

        fire_risk = 0   → 변화 없음
        fire_risk = 1.0 → dt_yr 동안 최대 60% 소각

        반환: (new_B_wood, new_organic, reset_info)
        reset_info: 소각량, 방출 CO₂, 리셋 강도 포함

        산불(망각) 후 회복:
          소각된 B_wood → CO₂ 방출 → 대기 보정 (fire_engine.delta_O2_frac)
          빈 토지 → pioneer 종 정착 → 새 바이오매스 성장 시작
        """
        burn_fraction = self.MAX_BURN_FRACTION * fire_risk * dt_yr
        burn_fraction = min(burn_fraction, 1.0 - self.MIN_B_WOOD / max(B_wood, EPS))

        burned_wood    = B_wood  * burn_fraction
        burned_organic = organic * min(1.0, burn_fraction * self.ORGANIC_BURN_MULT)

        new_B_wood  = max(self.MIN_B_WOOD, B_wood  - burned_wood)
        new_organic = max(0.0,             organic - burned_organic)

        # CO₂ 방출 [kg C/m²] (탄소 보존)
        co2_released = burned_wood + burned_organic

        # 스트레스 적산기 부분 리셋 (산불 = 스트레스 방출)
        reset_fraction = 0.0
        if self.accumulator and fire_risk > 0.1:
            # 산불이 크면 행성 스트레스 일부 해소 (= 망각 후 개운함)
            reset_fraction = fire_risk * 0.3
            self.accumulator._planet_ema *= (1.0 - reset_fraction)
            self.accumulator._co2_accumulated *= (1.0 - reset_fraction * 0.5)

        info = {
            "band_idx":       band_idx,
            "fire_risk":      fire_risk,
            "burned_wood":    burned_wood,
            "burned_organic": burned_organic,
            "co2_released":   co2_released,
            "new_B_wood":     new_B_wood,
            "new_organic":    new_organic,
            "stress_reset":   reset_fraction,
            "recovery_mode":  new_B_wood < 0.5,  # 회복 모드 여부
        }
        self.reset_log.append(info)
        return new_B_wood, new_organic, info

    def apply_to_snapshot(self, results, env):
        """FireBandResult 리스트 → 산불 발생 밴드 국소 리셋 적용.

        hot spot 밴드의 BandEco를 소각량만큼 업데이트한 새 band_ecosystems 반환.
        """
        try:
            from fire_engine import BandEco, BAND_CENTERS_DEG
        except ImportError:
            from .fire_engine import BandEco, BAND_CENTERS_DEG

        new_ecos = []
        for r in results:
            eco = env.get_band(r.band_idx)
            if r.fire_risk > 0.001:
                new_bw, new_org, _ = self.apply(
                    band_idx  = r.band_idx,
                    B_wood    = eco.B_wood,
                    organic   = eco.organic,
                    fire_risk = r.fire_risk,
                    dt_yr     = 1.0,
                )
                new_ecos.append(BandEco(
                    band_idx   = r.band_idx,
                    phi_deg    = r.phi_deg,
                    B_wood     = new_bw,
                    organic    = new_org,
                    W_override = eco.W_override,
                ))
            else:
                new_ecos.append(eco)
        return new_ecos
