"""リスク管理：仕向超過限度額・担保・流動性供給銀行。

- 仕向超過額 = 支払予定額 − 受取予定額（その決済日分のネット支払ポジション）
- 新たな小口取引を受け付けると限度額を超える場合、その取引は保留される
- 限度額は担保等で裏付ける（カバー率は config.COLLATERAL_COVERAGE_RATIO）
- 決済不能時は流動性供給銀行が不足資金を即時に供給し、
  その後、不履行参加者の担保処分代り金で返済する
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import COLLATERAL_COVERAGE_RATIO


@dataclass
class CollateralItem:
    name: str
    face: int
    haircut: float = 0.0

    @property
    def value(self) -> int:
        return int(self.face * (1 - self.haircut))


class RiskError(ValueError):
    pass


class RiskManager:
    def __init__(self, log, coverage_ratio: float = COLLATERAL_COVERAGE_RATIO):
        self.log = log
        self.coverage_ratio = coverage_ratio
        self.caps: dict[str, int] = {}
        self.collateral: dict[str, list[CollateralItem]] = {}
        self.liquidity_lines: dict[str, int] = {}

    # --- 担保 ---------------------------------------------------------------
    def pledge(self, code: str, item: CollateralItem) -> None:
        self.collateral.setdefault(code, []).append(item)

    def collateral_value(self, code: str) -> int:
        return sum(i.value for i in self.collateral.get(code, []))

    # --- 仕向超過限度額 -------------------------------------------------------
    def set_cap(self, code: str, cap: int) -> None:
        need = int(cap * self.coverage_ratio)
        have = self.collateral_value(code)
        if have < need:
            raise RiskError(f"{code}: 担保評価額 {have:,}円 が限度額 {cap:,}円 の必要担保 {need:,}円 に不足")
        self.caps[code] = cap
        self.log.add("RISK", f"{code} 仕向超過限度額を {cap:,}円 に設定（担保評価額 {have:,}円）")

    def cap(self, code: str) -> int:
        return self.caps.get(code, 0)

    def headroom(self, code: str, net_debit: int) -> int:
        return self.cap(code) - net_debit

    def fits(self, code: str, net_debit: int, amount: int) -> bool:
        return net_debit + amount <= self.cap(code)

    # --- 流動性供給銀行 -------------------------------------------------------
    def set_liquidity_line(self, code: str, amount: int) -> None:
        self.liquidity_lines[code] = amount

    def draw_liquidity(self, shortfall: int, exclude: str) -> list[tuple[str, int]]:
        """不足額を流動性供給枠に按分する。枠合計が足りなければ RiskError。"""
        lines = {k: v for k, v in self.liquidity_lines.items() if k != exclude and v > 0}
        total = sum(lines.values())
        if total < shortfall:
            raise RiskError(f"流動性供給枠 {total:,}円 が不足額 {shortfall:,}円 に満たない")
        draws, remaining = [], shortfall
        items = sorted(lines.items())
        for i, (code, line) in enumerate(items):
            amt = remaining if i == len(items) - 1 else min(line, shortfall * line // total)
            if amt > 0:
                draws.append((code, amt))
                remaining -= amt
        return draws

    def liquidate(self, code: str, needed: int) -> int:
        """不履行参加者の担保を処分し、調達額を返す（評価額ベース）。"""
        raised = 0
        items = self.collateral.get(code, [])
        while items and raised < needed:
            it = items.pop(0)
            raised += it.value
            self.log.add("RISK", f"{code} の担保「{it.name}」を処分 評価額 {it.value:,}円")
        # 処分で限度額の裏付けが減るため、限度額を担保残に合わせて引き下げ
        remain = self.collateral_value(code)
        if self.coverage_ratio > 0:
            self.caps[code] = min(self.cap(code), int(remain / self.coverage_ratio))
        return raised
