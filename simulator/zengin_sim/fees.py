"""内国為替制度運営費（1件あたり定額、仕向側→被仕向側）の集計。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from .config import INTERBANK_FEE_YEN


class FeeLedger:
    def __init__(self, fee: int = INTERBANK_FEE_YEN):
        self.fee = fee
        self.counts: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))

    def add(self, payer_bank: str, payee_bank: str, when: datetime) -> None:
        self.counts[when.strftime("%Y-%m")][(payer_bank, payee_bank)] += 1

    def summary(self, month: str) -> list[dict]:
        pay: dict[str, int] = defaultdict(int)
        rec: dict[str, int] = defaultdict(int)
        for (a, b), n in self.counts.get(month, {}).items():
            pay[a] += n * self.fee
            rec[b] += n * self.fee
        codes = sorted(set(pay) | set(rec))
        return [{"code": c, "payable": pay[c], "receivable": rec[c], "net": rec[c] - pay[c]} for c in codes]
