"""シミュレーション全体の組み立て（架空の参加金融機関・口座・担保の初期設定）。

金融機関名・コードはすべて架空。実在の金融機関とは関係ない。
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta

from .bank import BankNode, TransferError
from .bizcal import BusinessCalendar, SimClock
from .boj import BOJNet
from .center import ZenginCenter
from .config import CORE_CLOSE, LARGE_VALUE_THRESHOLD, ZENGIN_NET_ACCOUNT
from .events import EventLog
from .fees import FeeLedger
from .models import Bank, ParticipantType
from .risk import CollateralItem, RiskManager
from .settlement import NettingEngine, SettlementService

OKU = 100_000_000  # 1億円

D, A = ParticipantType.DIRECT, ParticipantType.AGENCY

# (コード, 名称, カナ, 区分, 代行先, モアタイム, 業態, 日銀当預, 担保(額面), 限度額, 流動性供給枠)
DEFAULT_BANKS = [
    ("9001", "あおば銀行", "ｱｵﾊﾞｷﾞﾝｺｳ", D, None, True, "銀行", 300 * OKU, 260 * OKU, 250 * OKU, 120 * OKU),
    ("9002", "つばさ銀行", "ﾂﾊﾞｻｷﾞﾝｺｳ", D, None, True, "銀行", 200 * OKU, 180 * OKU, 170 * OKU, 80 * OKU),
    ("9003", "はるかぜ銀行", "ﾊﾙｶｾﾞｷﾞﾝｺｳ", D, None, True, "銀行", 40 * OKU, 35 * OKU, 30 * OKU, 0),
    ("9100", "みどり信用金庫連合会", "ﾐﾄﾞﾘｼﾝｷﾝﾚﾝｺﾞｳｶｲ", D, None, True, "系統中央機関", 80 * OKU, 60 * OKU, 55 * OKU, 0),
    ("9101", "ひだまり信用金庫", "ﾋﾀﾞﾏﾘｼﾝｷﾝ", A, "9100", True, "信用金庫", 0, 0, 0, 0),
    ("9102", "こもれび信用組合", "ｺﾓﾚﾋﾞｼﾝｸﾐ", A, "9100", False, "信用組合", 0, 0, 0, 0),
    ("9500", "ペイライト", "ﾍﾟｲﾗｲﾄ", A, "9002", True, "資金移動業者", 0, 0, 0, 0),
]

PERSON_NAMES = [
    "ヤマダ タロウ", "スズキ ハナコ", "サトウ イチロウ", "タナカ ミサキ", "イトウ ケンジ",
    "ワタナベ ユイ", "ナカムラ ショウ", "コバヤシ アヤ", "カトウ ダイスケ", "ヨシダ メグミ",
    "ヤマモト リョウ", "マツモト サクラ", "イノウエ ツバサ", "キムラ ヒナ", "シミズ ソウタ",
]
CORP_NAMES = [
    "カブシキガイシャ アオバショウジ", "カブシキガイシャ ミライデンキ", "ユウゲンガイシャ ハマベスイサン",
    "カブシキガイシャ ソラノウンユ", "ゴウドウガイシャ ホシゾラ", "カブシキガイシャ ツバメケンセツ",
]


class Simulation:
    def __init__(self, start: datetime | None = None, echo: bool = False, seed: int = 42,
                 populate: bool = True):
        self.clock = SimClock(start or datetime(2026, 10, 16, 8, 0))
        self.cal = BusinessCalendar()
        self.log = EventLog(self.clock, echo)
        self.boj = BOJNet(self.clock, self.log)
        self.risk = RiskManager(self.log)
        self.netting = NettingEngine()
        self.fees = FeeLedger()
        self.settlement = SettlementService(self.boj, self.risk, self.netting, self.log)
        self.center = ZenginCenter(self.clock, self.cal, self.boj, self.risk, self.netting,
                                   self.settlement, self.fees, self.log)
        self.nodes: dict[str, BankNode] = {}
        self.rng = random.Random(seed)
        self.boj.open(ZENGIN_NET_ACCOUNT, 0)
        if populate:
            self._populate()

    # ----------------------------------------------------------- 組み立て
    def add_bank(self, bank: Bank, boj_balance: int = 0, collateral: int = 0, cap: int = 0,
                 liquidity_line: int = 0) -> BankNode:
        key = hashlib.sha256(f"key-{bank.code}".encode()).digest()
        node = BankNode(bank, self.center, self.clock, self.cal, self.log, key)
        self.nodes[bank.code] = node
        self.center.register(bank, node, key)
        if bank.is_direct:
            self.boj.open(bank.code, boj_balance)
            if collateral:
                self.risk.pledge(bank.code, CollateralItem(f"{bank.name} 差入国債", collateral, 0.0))
            self.risk.set_cap(bank.code, cap)
            if liquidity_line:
                self.risk.set_liquidity_line(bank.code, liquidity_line)
        return node

    def _populate(self) -> None:
        for (code, name, kana, pt, agent, more, inst, bal, coll, cap, line) in DEFAULT_BANKS:
            self.add_bank(Bank(code, name, kana, pt, agent, more, inst), bal, coll, cap, line)
        for code, node in self.nodes.items():
            big = code in ("9001", "9002")
            for i, nm in enumerate(PERSON_NAMES):
                bal = self.rng.randint(50, 800) * 10_000
                node.open_account(f"{100 + i % 3:03d}", 1, f"{1000001 + i:07d}", nm, bal)
            for i, nm in enumerate(CORP_NAMES):
                bal = (self.rng.randint(5, 40) * OKU) if big else self.rng.randint(2, 30) * 10_000_000
                node.open_account("001", 2, f"{2000001 + i:07d}", nm, bal)

    # ----------------------------------------------------------- 時間
    def run_until(self, target: datetime, auto_settle: bool = True) -> None:
        """模擬時計を target まで進める。境界（コア開始/終了・16:15）で必要な処理を行う。"""
        for t, label in self.cal.boundaries_between(self.clock.now, target):
            self.clock.set(t)
            if label == "core_open":
                self.log.add("CLOCK", f"{t:%m/%d} コアタイム開始")
            elif label == "core_close":
                self.log.add("CLOCK", f"{t:%m/%d} コアタイム終了 → 以降はモアタイム（翌営業日決済）")
            self.center.tick()
            if label == "settlement" and auto_settle:
                self.settle(t.date())
        self.clock.set(target)
        self.center.tick()

    def advance(self, minutes: int) -> None:
        self.run_until(self.clock.now + timedelta(minutes=minutes))

    def at(self, hhmm: str, day: date | None = None) -> datetime:
        h, m = map(int, hhmm.split(":"))
        d = day or self.clock.now.date()
        return datetime(d.year, d.month, d.day, h, m)

    def settle(self, d: date | None = None):
        d = d or self.clock.now.date()
        if d in self.settlement.results:
            return self.settlement.results[d]
        self.log.add("CLOCK", f"{d} 16:15 資金決済")
        return self.center.end_of_day(d)

    # ----------------------------------------------------------- 操作
    def node(self, code: str) -> BankNode:
        return self.nodes[code]

    def accounts_of(self, code: str):
        return list(self.nodes[code].accounts.values())

    def random_transfers(self, n: int, max_amount: int = 5_000_000, large_ratio: float = 0.0,
                         corp_ratio: float = 0.3) -> int:
        """ランダムな他行宛振込を n 件発生させる。成功件数を返す。"""
        codes = list(self.nodes)
        ok = 0
        for _ in range(n):
            a, b = self.rng.sample(codes, 2)
            src_node, dst_node = self.nodes[a], self.nodes[b]
            corp = self.rng.random() < corp_ratio
            srcs = [x for x in src_node.accounts.values() if (x.acct_type == 2) == corp]
            src = self.rng.choice(srcs)
            dst = self.rng.choice(list(dst_node.accounts.values()))
            if self.rng.random() < large_ratio:
                amount = self.rng.randint(1, 5) * OKU + self.rng.randint(0, 99) * 1_000_000
            else:
                # 少額が多く高額が少ない分布（対数一様）
                amount = int(10 ** self.rng.uniform(3.5, 6.8))
                amount = min(amount, max_amount)
            amount = min(amount, src.balance)
            if amount < 1000:
                continue
            try:
                src_node.transfer(src.key, b, dst.branch, dst.acct_type, dst.number, dst.holder, amount)
                ok += 1
            except TransferError:
                pass
        return ok

    # ----------------------------------------------------------- 状態
    def current_settlement_date(self) -> date:
        return self.cal.settlement_date_for(self.clock.now)

    def snapshot(self, n_tx: int = 60, n_log: int = 120) -> dict:
        sd = self.current_settlement_date()
        pos = self.netting.net_positions(sd)
        parts = []
        for code, node in self.nodes.items():
            b = node.bank
            sp = self.center.sp(code)
            row = {
                "code": code, "name": b.name, "kana": b.kana, "ptype": b.ptype.value,
                "agent": b.settlement_agent, "moretime": b.moretime, "institution": b.institution,
                "rc_up": node.rc_up, "outbox": len(node.outbox), "deposits": node.total_deposits(),
                "suspense": node.suspense, "sent": node.stats.sent, "received": node.stats.received,
                "accounts": [
                    {"branch": a.branch, "type": a.acct_type, "no": a.number, "holder": a.holder,
                     "balance": a.balance} for a in node.accounts.values()
                ],
            }
            if b.is_direct:
                nd = max(0, -pos.get(code, 0))
                row.update({
                    "boj": self.boj.balance(code), "cap": self.risk.cap(code),
                    "net": pos.get(code, 0), "net_debit": nd,
                    "headroom": self.risk.headroom(code, nd),
                    "collateral": self.risk.collateral_value(code),
                    "liquidity_line": self.risk.liquidity_lines.get(code, 0),
                })
            else:
                row["settles_via"] = sp
            parts.append(row)
        recs = list(self.center.records.values())[-n_tx:][::-1]
        return {
            "now": self.clock.now.isoformat(sep=" ", timespec="minutes"),
            "weekday": "月火水木金土日"[self.clock.now.weekday()],
            "business_day": self.cal.is_business_day(self.clock.now.date()),
            "service": self.center.service(),
            "settlement_date": sd.isoformat(),
            "core_up": self.center.core_up, "more_up": self.center.more_up,
            "participants": parts,
            "queues": {"reserved": len(self.center.reserved), "held": len(self.center.held),
                       "rtgs": len(self.center.rtgs_queue), "undelivered": len(self.center.undelivered)},
            "stats": dict(self.center.stats),
            "netting": self.netting.report(sd),
            "settlements": [
                {"date": d.isoformat(), "summary": r.summary(), "defaults": r.defaults}
                for d, r in sorted(self.settlement.results.items())
            ],
            "fees": self.fees.summary(self.clock.now.strftime("%Y-%m")),
            "transactions": [r.to_dict() for r in recs],
            "events": self.log.tail(n_log)[::-1],
            "large_threshold": LARGE_VALUE_THRESHOLD,
            "core_close": CORE_CLOSE.strftime("%H:%M"),
        }
