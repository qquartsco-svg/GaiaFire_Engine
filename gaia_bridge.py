"""gaia_bridge.py — CookiieBrain ↔ GaiaFire 연결 브리지 (Phase 8)

설계 철학:
    "뉴런이 스트레스 받으면 지구 어딘가에 불이 난다"
    CookiieBrainEngine의 물리 상태(에너지, 속도)를
    NeuronEvent로 변환 → StressAccumulator → FireEnvSnapshot patch

변환 규칙:
    GlobalState.energy  → atp_consumed  (normalize: [-∞,0] → [0,1])
    ‖state_vector 속도‖ → heat_mw       (단위 없는 배수)
    step × dt × 1000   → time_ms       (시뮬레이션 시간 ms 단위)

출력:
    CognitiveBrainSnapshot  → ForgetEngine 입력
    FireEnvSnapshot patch   → FireEngine 입력
    PlanetStressIndex       → 행성 스트레스 모니터링

의존:
    fire_risk, fire_engine, stress_accumulator (동일 폴더)
    독립 사용 가능 — CookiieBrainEngine import 불필요 (순환 방지)

v1.0 (Phase 8):
    GaiaBridge: 단계별 push/update/patch 파이프라인
    GaiaBridgeConfig: 정규화 파라미터
    BrainGaiaState: 매 스텝 스냅샷
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

# 독립 레포 — 동일 폴더에서 직접 import
try:
    from .stress_accumulator import StressAccumulator, NeuronEvent
    from .fire_engine import FireEnvSnapshot, FireEngine
    from .stress_accumulator import (
        CognitiveBrainSnapshot,
        OrganFatigueState,
        PlanetStressIndex,
    )
    _STRESS_FULL = True
except ImportError:
    from stress_accumulator import StressAccumulator, NeuronEvent
    from fire_engine import FireEnvSnapshot, FireEngine
    try:
        from stress_accumulator import (
            CognitiveBrainSnapshot,
            OrganFatigueState,
            PlanetStressIndex,
        )
        _STRESS_FULL = True
    except ImportError:
        _STRESS_FULL = False


# ════════════════════════════════════════════════════════════════
#  설정
# ════════════════════════════════════════════════════════════════

@dataclass
class GaiaBridgeConfig:
    """GaiaBridge 정규화 파라미터.

    Attributes:
        energy_ref: Hopfield 에너지 기준값 (이 값에서 atp=0.5)
            음수. PFE 에너지는 보통 [-수백, 0] 범위.
        energy_scale: 에너지 정규화 스케일 (클수록 민감도 낮음)
        velocity_scale: 속도 → heat_mw 변환 배수
        dt: 시뮬레이션 스텝 간격 (초 단위)
            CookiieBrainEngine의 potential_field_config["dt"]와 일치시킬 것.
        organ_update_every_steps: 기관 EMA 업데이트 주기 (스텝)
        planet_update_every_steps: 행성 EMA 업데이트 주기 (스텝)
        base_O2_frac: 기준 대기 O2 분율 (mol/mol)
        base_CO2_ppm: 기준 대기 CO2 (ppm)
    """
    energy_ref: float = -50.0
    energy_scale: float = 100.0
    velocity_scale: float = 5.0
    dt: float = 0.01               # seconds per step
    organ_update_every_steps: int = 100
    planet_update_every_steps: int = 1000
    base_O2_frac: float = 0.21
    base_CO2_ppm: float = 400.0


# ════════════════════════════════════════════════════════════════
#  매 스텝 스냅샷
# ════════════════════════════════════════════════════════════════

@dataclass
class BrainGaiaState:
    """매 스텝 CookiieBrain → Gaia 연결 스냅샷.

    Attributes:
        step: 시뮬레이션 스텝 번호
        time_ms: 누적 시뮬레이션 시간 (ms)
        atp_consumed: 정규화된 ATP 소비량 [0,1]
        heat_mw: 열 발생 추정치 (mW 단위 없는 배수)
        cell_stress: 세포 스트레스 점수
        organ_fatigue: 기관 피로 EMA (None = 아직 미계산)
        planet_pressure: 행성 산불 압력 (None = 아직 미계산)
        O2_frac_patched: 스트레스 보정된 O2 분율
        CO2_ppm_patched: 스트레스 보정된 CO2 ppm
    """
    step: int
    time_ms: float
    atp_consumed: float
    heat_mw: float
    cell_stress: float
    organ_fatigue: Optional[float] = None
    planet_pressure: Optional[float] = None
    O2_frac_patched: float = 0.21
    CO2_ppm_patched: float = 400.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "time_ms": self.time_ms,
            "atp_consumed": self.atp_consumed,
            "heat_mw": self.heat_mw,
            "cell_stress": self.cell_stress,
            "organ_fatigue": self.organ_fatigue,
            "planet_pressure": self.planet_pressure,
            "O2_frac_patched": self.O2_frac_patched,
            "CO2_ppm_patched": self.CO2_ppm_patched,
        }


# ════════════════════════════════════════════════════════════════
#  GaiaBridge
# ════════════════════════════════════════════════════════════════

class GaiaBridge:
    """CookiieBrainEngine GlobalState → StressAccumulator → FireEngine 브리지.

    사용법 (CookiieBrainEngine 루프 안에서)::

        bridge = GaiaBridge(GaiaBridgeConfig(dt=0.01))

        for step in range(n_steps):
            state = engine.update(state)
            gaia_state = bridge.push(
                step=step,
                energy=state.energy,
                state_vector=state.state_vector,
            )

        # 최종 산불 예측
        fire_result = bridge.predict_fire()
        brain_snap  = bridge.brain_snapshot()
        summary     = bridge.summary()

    설계 원칙:
        - CookiieBrainEngine을 import하지 않음 (순환 방지)
        - GlobalState를 직접 받지 않음 (결합 최소화)
        - energy + state_vector 두 값만으로 동작
    """

    def __init__(self, config: Optional[GaiaBridgeConfig] = None):
        self.cfg = config or GaiaBridgeConfig()
        self._acc = StressAccumulator()
        self._fire_engine = FireEngine()
        self._step = 0
        self._history: List[BrainGaiaState] = []

        # 마지막 기관/행성 상태 캐시
        self._last_organ: Optional[OrganFatigueState] = None if _STRESS_FULL else None
        self._last_planet: Optional[PlanetStressIndex] = None if _STRESS_FULL else None
        self._last_patch: Dict[str, float] = {
            "O2_frac_patched": self.cfg.base_O2_frac,
            "CO2_ppm_patched": self.cfg.base_CO2_ppm,
            "O2_offset": 0.0,
            "CO2_offset": 0.0,
        }

        # 행성 시간 카운터 — planet_update 호출 횟수로 yr 추적
        # 뇌 ms를 직접 yr로 변환하면 수치가 너무 작음.
        # "planet_every 스텝마다 1yr 진행"으로 추상화.
        self._planet_yr_counter: float = 0.0
        # 기관 시간 카운터 — organ_every 스텝마다 1hr 진행
        self._organ_hr_counter: float = 0.0

    # ────────────────────────────────────────────────────────
    #  핵심: push()
    # ────────────────────────────────────────────────────────

    def push(
        self,
        step: int,
        energy: float,
        state_vector,           # numpy 배열 또는 list
        neuron_id: str = "brain",
    ) -> BrainGaiaState:
        """GlobalState 물리량 → NeuronEvent → StressAccumulator push.

        Args:
            step: 현재 스텝 번호
            energy: GlobalState.energy (Hopfield 에너지, 음수)
            state_vector: GlobalState.state_vector (위치 + 속도 concat)
            neuron_id: 뉴런 식별자 (디버그용)

        Returns:
            BrainGaiaState: 현재 스텝 스냅샷
        """
        self._step = step
        cfg = self.cfg

        # 1. 에너지 → ATP 변환
        #    Hopfield 에너지는 음수. |energy|가 클수록 깊은 attractor = 고활성
        #    atp = sigmoid((|E| - |E_ref|) / scale)
        e_abs = abs(energy)
        e_ref_abs = abs(cfg.energy_ref)
        atp_raw = (e_abs - e_ref_abs) / cfg.energy_scale
        atp_consumed = _sigmoid(atp_raw)

        # 2. 속도 → heat_mw 변환
        #    state_vector = [x0..xN, v0..vN]
        try:
            sv = list(state_vector)
            n = len(sv) // 2
            v = sv[n:]
            v_norm = math.sqrt(sum(vi ** 2 for vi in v))
        except Exception:
            v_norm = 0.0
        heat_mw = v_norm * cfg.velocity_scale

        # 3. 시간 (ms 단위)
        time_ms = step * cfg.dt * 1000.0

        # 4. NeuronEvent 생성 및 push
        # neuron_id: NeuronEvent는 int를 기대 (str → hash로 int화)
        nid = neuron_id if isinstance(neuron_id, int) else hash(neuron_id) % 100000

        ev = NeuronEvent(
            time_ms=time_ms,
            co2_umol_s=heat_mw * 0.1,          # 열 → CO2 대리 추정
            heat_mw=heat_mw,
            atp_consumed=atp_consumed,
            neuron_id=nid,
        )
        cell_state = self._acc.push_neuron_event(ev)

        # 5. 기관 EMA 주기 업데이트
        # organ_every 스텝마다 1hr씩 누적 (뇌 ms → 기관 hr 스케일 변환)
        organ_fatigue = None
        if step > 0 and step % cfg.organ_update_every_steps == 0:
            self._organ_hr_counter += 1.0
            organ = self._acc.update_organ(time_hr=self._organ_hr_counter)
            self._last_organ = organ
            organ_fatigue = organ.fatigue_ema

        elif self._last_organ is not None:
            organ_fatigue = self._last_organ.fatigue_ema

        # 6. 행성 EMA 주기 업데이트
        # planet_every 스텝마다 1yr씩 누적 (기관 hr → 행성 yr 스케일 변환)
        planet_pressure = None
        if step > 0 and step % cfg.planet_update_every_steps == 0:
            self._planet_yr_counter += 1.0
            planet = self._acc.update_planet(time_yr=self._planet_yr_counter)
            self._last_planet = planet
            planet_pressure = planet.fire_pressure

            # O2 패치 갱신
            patch = self._acc.to_fire_env_patch(
                base_O2=cfg.base_O2_frac,
                base_CO2=cfg.base_CO2_ppm,
            )
            self._last_patch = patch

        elif self._last_planet is not None:
            planet_pressure = self._last_planet.fire_pressure

        # 7. 스냅샷 기록
        gaia_state = BrainGaiaState(
            step=step,
            time_ms=time_ms,
            atp_consumed=atp_consumed,
            heat_mw=heat_mw,
            cell_stress=cell_state.stress_score,
            organ_fatigue=organ_fatigue,
            planet_pressure=planet_pressure,
            O2_frac_patched=self._last_patch.get("O2_frac_patched", cfg.base_O2_frac),
            CO2_ppm_patched=self._last_patch.get("CO2_ppm_patched", cfg.base_CO2_ppm),
        )
        self._history.append(gaia_state)
        return gaia_state

    # ────────────────────────────────────────────────────────
    #  예측 출력
    # ────────────────────────────────────────────────────────

    def predict_fire(
        self,
        time_yr: float = 0.5,
    ) -> Dict[str, Any]:
        """현재 스트레스 상태로 전지구 산불 예측.

        Args:
            time_yr: 예측 시점 (yr, 계절 결정)

        Returns:
            dict: gfi_base, gfi_patched, band_results, patch
        """
        patch = self._last_patch
        env_base = FireEnvSnapshot(
            O2_frac=self.cfg.base_O2_frac,
            CO2_ppm=self.cfg.base_CO2_ppm,
            time_yr=time_yr,
        )
        env_patched = FireEnvSnapshot(
            O2_frac=patch.get("O2_frac_patched", self.cfg.base_O2_frac),
            CO2_ppm=patch.get("CO2_ppm_patched", self.cfg.base_CO2_ppm),
            time_yr=time_yr,
        )
        res_base    = self._fire_engine.predict(env_base)
        res_patched = self._fire_engine.predict(env_patched)
        gfi_base    = self._fire_engine.global_fire_index(res_base)
        gfi_patched = self._fire_engine.global_fire_index(res_patched)

        return {
            "gfi_base":       gfi_base,
            "gfi_patched":    gfi_patched,
            "gfi_delta":      gfi_patched - gfi_base,
            "O2_offset":      patch.get("O2_offset", 0.0),
            "CO2_offset":     patch.get("CO2_offset", 0.0),
            "band_results":   res_patched,
        }

    def brain_snapshot(self, time_hr: Optional[float] = None) -> Optional["CognitiveBrainSnapshot"]:
        """현재 스트레스 상태 → CognitiveBrainSnapshot (ForgetEngine 입력).

        Returns None if StressAccumulator types not available.
        """
        if not _STRESS_FULL:
            return None
        hr = time_hr if time_hr is not None else (self._step * self.cfg.dt / 3600.0)
        return self._acc.to_brain_snapshot(time_hr=max(hr, 1e-9))

    def summary(self) -> Dict[str, Any]:
        """전체 파이프라인 요약."""
        smry = self._acc.summary()
        patch = self._last_patch
        return {
            "steps_processed": self._step,
            "L1_cell_stress":  smry.get("L1_cell_stress", 0.0),
            "L2_fatigue":      smry.get("L2_fatigue", 0.0),
            "L3_planet_stress":smry.get("L3_planet_stress", 0.0),
            "L3_fire_pressure":smry.get("L3_fire_pressure", 0.0),
            "L3_O2_offset":    smry.get("L3_O2_offset", 0.0),
            "O2_frac_patched": patch.get("O2_frac_patched", self.cfg.base_O2_frac),
            "CO2_ppm_patched": patch.get("CO2_ppm_patched", self.cfg.base_CO2_ppm),
        }

    def history(self) -> List[BrainGaiaState]:
        """전체 스텝 히스토리 반환."""
        return list(self._history)

    def reset(self):
        """브리지 + 적산기 초기화."""
        self._acc = StressAccumulator()
        self._step = 0
        self._history.clear()
        self._last_organ = None
        self._last_planet = None
        self._last_patch = {
            "O2_frac_patched": self.cfg.base_O2_frac,
            "CO2_ppm_patched": self.cfg.base_CO2_ppm,
            "O2_offset": 0.0,
            "CO2_offset": 0.0,
        }
        self._planet_yr_counter = 0.0
        self._organ_hr_counter = 0.0


# ════════════════════════════════════════════════════════════════
#  유틸
# ════════════════════════════════════════════════════════════════

def _sigmoid(x: float) -> float:
    """안전한 시그모이드 [0,1]."""
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


# ════════════════════════════════════════════════════════════════
#  간편 팩토리
# ════════════════════════════════════════════════════════════════

def make_bridge(
    dt: float = 0.01,
    energy_ref: float = -50.0,
    energy_scale: float = 100.0,
    velocity_scale: float = 5.0,
    organ_every: int = 100,
    planet_every: int = 1000,
    base_O2: float = 0.21,
    base_CO2: float = 400.0,
) -> GaiaBridge:
    """GaiaBridge 간편 생성.

    Args:
        dt: 시뮬레이션 스텝 간격 (초). CookiieBrainEngine.dt와 일치시킬 것.
        energy_ref: Hopfield 에너지 기준값 (음수, 이 값에서 ATP=0.5)
        energy_scale: 에너지 정규화 스케일
        velocity_scale: 속도 → heat_mw 배수
        organ_every: 기관 EMA 업데이트 주기 (스텝)
        planet_every: 행성 EMA 업데이트 주기 (스텝)
        base_O2: 기준 O2 분율
        base_CO2: 기준 CO2 ppm

    Returns:
        GaiaBridge 인스턴스
    """
    cfg = GaiaBridgeConfig(
        dt=dt,
        energy_ref=energy_ref,
        energy_scale=energy_scale,
        velocity_scale=velocity_scale,
        organ_update_every_steps=organ_every,
        planet_update_every_steps=planet_every,
        base_O2_frac=base_O2,
        base_CO2_ppm=base_CO2,
    )
    return GaiaBridge(cfg)


__all__ = [
    "GaiaBridge",
    "GaiaBridgeConfig",
    "BrainGaiaState",
    "make_bridge",
]
