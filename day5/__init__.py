"""solar/day5 — 생물 이동 / 정보 네트워크 레이어 (다섯째날)

Day5 = 움직이는 생물 + 씨드 분산 + 먹이사슬 (Loop F/G/H)

레이어 포지션:
    Day3 biosphere/latitude_bands → "확산 결합 없음 (독립 기어)"
    Day5 → 그 위에 transport term 추가

핵심 방정식:
    dB[i]/dt = f_local(B[i]) + transport_in[i] - transport_out[i]

    f_local  = 기존 Day3 BiosphereColumn (광합성/산불/...)
    K[j→i]  = 위도 밴드 j → i 로의 transport 커널

Loop 연결:
    Loop F: BirdAgent 씨드 분산 → pioneer B[i] 증가
    Loop G: BirdAgent 구아노 → nitrogen.N_soil[i] 증가
    Loop H: FishAgent 포식 → phyto 감소 → CO₂ 호흡 변화

모듈:
    mobility_engine.py  — BirdAgent / FishAgent (이동률 계산)
    seed_transport.py   — 위도 밴드 간 보존형 transport 커널
    food_web.py         — 트로픽 레벨 ODE (phyto/herbivore/carnivore)
"""

__version__ = "1.0.0"

from .mobility_engine import (
    BirdAgent,
    FishAgent,
    make_bird_agent,
    make_fish_agent,
)
from .seed_transport import (
    SeedTransport,
    TransportKernel,
    make_transport,
)
from .food_web import (
    FoodWeb,
    TrophicState,
    make_food_web,
)

__all__ = [
    # mobility
    "BirdAgent",
    "FishAgent",
    "make_bird_agent",
    "make_fish_agent",
    # transport
    "SeedTransport",
    "TransportKernel",
    "make_transport",
    # food web
    "FoodWeb",
    "TrophicState",
    "make_food_web",
]
