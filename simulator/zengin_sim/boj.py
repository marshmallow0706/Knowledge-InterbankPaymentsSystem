"""日銀ネット（日本銀行当座預金）の模擬。

- 大口内為取引（1件1億円以上）の即時グロス決済（RTGS）
- 小口内為取引の受払差額の決済（全銀ネット名義口座を介した CCP 決済）
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class BojEntry:
    ts: datetime
    frm: str
    to: str
    amount: int
    purpose: str


class InsufficientFunds(Exception):
    pass


class BOJNet:
    EXTERNAL = "EXTERNAL"   # 担保処分代り金など、当座預金の外部からの資金

    def __init__(self, clock, log):
        self.clock = clock
        self.log = log
        self.balances: dict[str, int] = {}
        self.journal: list[BojEntry] = []

    def open(self, code: str, balance: int = 0) -> None:
        self.balances[code] = balance

    def balance(self, code: str) -> int:
        return self.balances.get(code, 0)

    def has(self, code: str) -> bool:
        return code in self.balances

    def transfer(self, frm: str, to: str, amount: int, purpose: str) -> bool:
        """当座預金間の振替。残高不足なら False（何もしない）。"""
        if amount <= 0:
            return True
        if frm not in self.balances or to not in self.balances:
            raise KeyError(f"日銀当座預金がありません: {frm} → {to}")
        if self.balances[frm] < amount:
            self.log.add("BOJ", f"残高不足 {frm}→{to} {amount:,}円 ({purpose}) 残高 {self.balances[frm]:,}円")
            return False
        self.balances[frm] -= amount
        self.balances[to] += amount
        self.journal.append(BojEntry(self.clock.now, frm, to, amount, purpose))
        self.log.add("BOJ", f"振替 {frm}→{to} {amount:,}円 ({purpose})")
        return True

    def inject(self, to: str, amount: int, purpose: str) -> None:
        """外部からの入金（担保処分代り金・オペによる資金供給等の模擬）。"""
        self.balances[to] = self.balances.get(to, 0) + amount
        self.journal.append(BojEntry(self.clock.now, self.EXTERNAL, to, amount, purpose))
        self.log.add("BOJ", f"入金 {to} {amount:,}円 ({purpose})")
