"""ProductionContext — SKU·시프트 스코프 τ·takt·recipe (T2-A S1).

τ는 카테고리뿐 아니라 SKU(제품군)와 시프트(주간/야간)로도 스코프된다.
예: 야간 시프트는 조명이 다르고 검사 허용 오차가 다를 수 있음.
인터페이스: context.py의 정적 팩토리 or env 기반 단일톤.

24h 라이프사이클(드리프트 감시)이 이 컨텍스트를 재사용한다 — 시프트별 τ·takt로 스코프.
HIL 경계는 SKU·시프트 전환 신호를 외부 이벤트(OPC UA/MQTT)로 주입한다.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field


@dataclass
class ProductionContext:
    """SKU·시프트 스코프의 생산 파라미터.

    Attributes:
        sku: 제품군 ID (예: "bottle_500ml", "cap_38mm"). "default" = 미설정.
        shift: 시프트 이름 ("day" | "night" | "weekend").
        tau_by_category: 카테고리별 τ 오버라이드. 없으면 config.inference.tau() 폴백.
        takt_s: 목표 takt time(초). 0 = 미설정.
        recipe: 자유형 레시피 파라미터(향후 확장).
    """
    sku: str = "default"
    shift: str = "day"
    tau_by_category: dict = field(default_factory=dict)
    takt_s: float = 0.0
    recipe: dict = field(default_factory=dict)

    def tau(self, category: str | None = None, base_tau: float = 0.5) -> float:
        """카테고리+SKU+시프트 스코프 τ. 오버라이드 없으면 base_tau 폴백."""
        if category and category in self.tau_by_category:
            return float(self.tau_by_category[category])
        # 시프트별 긴장도 조정(야간은 더 엄격 — 예시)
        shift_factor = {"day": 1.0, "night": 0.95, "weekend": 1.05}.get(self.shift, 1.0)
        return round(base_tau * shift_factor, 4)

    def summary(self) -> dict:
        return {"sku": self.sku, "shift": self.shift,
                "tau_by_category": dict(self.tau_by_category), "takt_s": self.takt_s}

    @classmethod
    def from_env(cls) -> "ProductionContext":
        """env에서 컨텍스트 읽기(ARIA_SKU, ARIA_SHIFT, ARIA_TAU_<CAT>…)."""
        sku = os.environ.get("ARIA_SKU", "default")
        shift = os.environ.get("ARIA_SHIFT", "day")
        # ARIA_TAU_BOTTLE=0.48 같은 패턴 수집
        tau_by_cat = {}
        prefix = "ARIA_TAU_"
        for k, v in os.environ.items():
            if k.startswith(prefix):
                cat = k[len(prefix):].lower()
                try:
                    tau_by_cat[cat] = float(v)
                except ValueError:
                    pass
        takt = float(os.environ.get("ARIA_TAKT_S", "0"))
        return cls(sku=sku, shift=shift, tau_by_category=tau_by_cat, takt_s=takt)


# 현재 공장 컨텍스트 싱글톤 — inspector/fusion이 참조.
# shift_context() 또는 set_context()로 교체 가능(SKU 전환 시).
_current: ProductionContext = ProductionContext.from_env()


def get_context() -> ProductionContext:
    return _current


def set_context(ctx: ProductionContext) -> None:
    global _current
    _current = ctx


def reload() -> None:
    """env 재읽기로 컨텍스트 초기화."""
    global _current
    _current = ProductionContext.from_env()
