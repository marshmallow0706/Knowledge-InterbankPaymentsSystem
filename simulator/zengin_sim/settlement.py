"""多角的ネッティングと資金決済（全銀ネットを CCP とする小口内為決済）。"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .config import ZENGIN_NET_ACCOUNT
from .risk import RiskError


class NettingError(RuntimeError):
    pass


class NettingEngine:
    """決済日ごとに清算参加者間のグロス受払を集計し、ネットポジションを計算する。"""

    def __init__(self):
        self.gross: dict[date, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
        self.counts: dict[date, int] = defaultdict(int)
        self.closed: set[date] = set()

    def record(self, d: date, payer: str, payee: str, amount: int) -> None:
        if d in self.closed:
            raise NettingError(f"{d} は決済済みのため計上できません")
        if payer == payee:
            return
        self.gross[d][(payer, payee)] += amount
        self.counts[d] += 1

    def net_positions(self, d: date) -> dict[str, int]:
        """正 = 受取超過、負 = 支払超過（仕向超過）。"""
        pos: dict[str, int] = defaultdict(int)
        for (payer, payee), amt in self.gross.get(d, {}).items():
            pos[payer] -= amt
            pos[payee] += amt
        return dict(pos)

    def net_debit(self, code: str, d: date) -> int:
        return max(0, -self.net_positions(d).get(code, 0))

    def report(self, d: date) -> dict:
        sent: dict[str, int] = defaultdict(int)
        recv: dict[str, int] = defaultdict(int)
        for (payer, payee), amt in self.gross.get(d, {}).items():
            sent[payer] += amt
            recv[payee] += amt
        codes = sorted(set(sent) | set(recv))
        rows = [{"code": c, "sent": sent[c], "recv": recv[c], "net": recv[c] - sent[c]} for c in codes]
        total_gross = sum(sent.values())
        total_net = sum(-r["net"] for r in rows if r["net"] < 0)
        if sum(r["net"] for r in rows) != 0:
            raise NettingError("ネットポジションの合計が0になりません")
        return {
            "date": d.isoformat(), "count": self.counts.get(d, 0), "rows": rows,
            "total_gross": total_gross, "total_net": total_net,
            "reduction": (1 - total_net / total_gross) if total_gross else 0.0,
            "closed": d in self.closed,
        }

    def close(self, d: date) -> None:
        self.closed.add(d)


@dataclass
class SettlementResult:
    date: date
    payments: list[tuple[str, int]] = field(default_factory=list)
    receipts: list[tuple[str, int]] = field(default_factory=list)
    defaults: list[dict] = field(default_factory=list)
    ok: bool = True

    def summary(self) -> str:
        p = sum(a for _, a in self.payments)
        s = f"{self.date} 決済: 支払 {len(self.payments)}先 / 受取 {len(self.receipts)}先 / 決済総額 {p:,}円"
        if self.defaults:
            s += f" / 決済不能 {len(self.defaults)}先（流動性供給により決済完了）"
        return s


class SettlementService:
    def __init__(self, boj, risk, netting, log):
        self.boj = boj
        self.risk = risk
        self.netting = netting
        self.log = log
        self.results: dict[date, SettlementResult] = {}

    def settle(self, d: date) -> SettlementResult:
        if d in self.results:
            return self.results[d]
        pos = self.netting.net_positions(d)
        self.netting.close(d)
        res = SettlementResult(d)
        z = ZENGIN_NET_ACCOUNT
        start = self.boj.balance(z)
        self.log.add("SETTLE", f"{d} 分の小口内為決済を開始（参加者 {len(pos)}）")

        # 1) 支払超過の参加者 → 全銀ネット口
        for code, net in sorted(pos.items()):
            if net >= 0:
                continue
            need = -net
            if self.boj.transfer(code, z, need, f"小口内為決済 支払({d})"):
                res.payments.append((code, need))
                continue
            avail = self.boj.balance(code)
            if avail > 0:
                self.boj.transfer(code, z, avail, f"小口内為決済 一部支払({d})")
            shortfall = need - avail
            self.log.add("SETTLE", f"⚠ {code} 決済資金不足 必要 {need:,}円 / 不足 {shortfall:,}円 → 決済不能処理")
            res.defaults.append(self._handle_default(code, shortfall))
            res.payments.append((code, need))

        # 2) 全銀ネット口 → 受取超過の参加者
        for code, net in sorted(pos.items()):
            if net <= 0:
                continue
            if not self.boj.transfer(z, code, net, f"小口内為決済 受取({d})"):
                res.ok = False
                raise NettingError("全銀ネット口の残高不足（本来起こり得ない）")
            res.receipts.append((code, net))

        if self.boj.balance(z) != start:
            res.ok = False
            raise NettingError("決済後の全銀ネット口残高が開始時と一致しません")
        self.results[d] = res
        self.log.add("SETTLE", res.summary())
        return res

    def _handle_default(self, code: str, shortfall: int) -> dict:
        z = ZENGIN_NET_ACCOUNT
        info = {"participant": code, "shortfall": shortfall, "liquidity": [], "collateral_raised": 0, "loss": 0}
        try:
            draws = self.risk.draw_liquidity(shortfall, exclude=code)
        except RiskError as e:
            self.log.add("ERROR", f"流動性供給不能: {e}")
            raise
        for prov, amt in draws:
            if not self.boj.transfer(prov, z, amt, f"流動性供給（{code}の決済不能）"):
                # 供給銀行自身の残高不足：模擬上は日銀の資金供給で補う
                self.boj.inject(prov, amt, "日銀による資金供給(模擬)")
                self.boj.transfer(prov, z, amt, f"流動性供給（{code}の決済不能）")
            info["liquidity"].append((prov, amt))
        raised = self.risk.liquidate(code, shortfall)
        info["collateral_raised"] = raised
        self.boj.inject(z, raised, f"{code} 担保処分代り金")
        repay_total = min(raised, shortfall)
        # 担保処分代り金で流動性供給銀行に返済（按分）。超過分は不履行参加者へ返還。
        remaining = repay_total
        for i, (prov, amt) in enumerate(draws):
            pay = remaining if i == len(draws) - 1 else amt * repay_total // shortfall
            self.boj.transfer(z, prov, pay, "流動性供給の返済（担保処分代り金）")
            remaining -= pay
        if raised > shortfall:
            self.boj.transfer(z, code, raised - shortfall, "担保処分代り金の余剰返還")
        if raised < shortfall:
            info["loss"] = shortfall - raised
            self.log.add("RISK", f"担保不足による損失 {info['loss']:,}円 → 流動性供給銀行が負担（損失分担）")
        self.log.add("RISK", f"{code} の決済不能を処理: 流動性供給 {draws} / 担保処分 {raised:,}円")
        return info
