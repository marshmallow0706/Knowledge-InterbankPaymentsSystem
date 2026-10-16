"""参加金融機関・口座・取引記録のデータモデル。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class ParticipantType(str, Enum):
    DIRECT = "清算参加者"           # 全銀ネットと直接資金決済を行う
    AGENCY = "代行決済委託"         # 清算参加者に資金決済を委託する


@dataclass
class Bank:
    code: str                      # 金融機関コード（4桁）
    name: str
    kana: str
    ptype: ParticipantType = ParticipantType.DIRECT
    settlement_agent: str | None = None   # 代行決済委託先（清算参加者のコード）
    moretime: bool = True          # モアタイム参加の有無
    institution: str = "銀行"      # 業態（銀行/信用金庫/信用組合/資金移動業者 等）

    @property
    def is_direct(self) -> bool:
        return self.ptype == ParticipantType.DIRECT


@dataclass
class Account:
    bank_code: str
    branch: str                    # 支店番号（3桁）
    acct_type: int                 # 1=普通 2=当座 4=貯蓄
    number: str                    # 口座番号（7桁）
    holder: str                    # 名義（半角カナ）
    balance: int = 0
    frozen: bool = False
    closed: bool = False

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.branch, self.acct_type, self.number)

    def label(self) -> str:
        t = {1: "普通", 2: "当座", 4: "貯蓄"}.get(self.acct_type, "?")
        return f"{self.bank_code}-{self.branch} {t} {self.number} {self.holder}"


class TxStatus(str, Enum):
    QUEUED_AT_BANK = "仕向行RC滞留"
    ACCEPTED = "受付"
    RESERVED = "予約(取扱日待ち)"
    HELD = "限度額超過で保留"
    PENDING_RTGS = "RTGS決済待ち"
    UNDELIVERED = "被仕向行へ未着"
    DELIVERED = "被仕向行へ着信"
    CREDITED = "入金済"
    RETURNED = "入金不能返却"
    RECALLED = "組戻済"
    RECALL_REFUSED = "組戻不成立"
    REJECTED = "センター不受理"


@dataclass
class TxRecord:
    """全銀センター側で管理する取引記録。"""
    tx_id: str
    msg_type: int
    from_bank: str
    to_bank: str
    amount: int
    seq: int
    accepted_at: datetime
    value_date: date
    channel: str = ""             # core / more / rtgs
    status: TxStatus = TxStatus.ACCEPTED
    settlement_date: date | None = None
    payer_sp: str = ""
    payee_sp: str = ""
    beneficiary: str = ""
    remitter: str = ""
    note: str = ""
    history: list[tuple[str, str]] = field(default_factory=list)

    def set(self, status: TxStatus, ts: datetime, note: str = "") -> None:
        self.status = status
        self.history.append((ts.isoformat(sep=" ", timespec="seconds"), status.value + (f"（{note}）" if note else "")))
        if note:
            self.note = note

    def to_dict(self) -> dict:
        return {
            "tx_id": self.tx_id, "type": self.msg_type, "from": self.from_bank, "to": self.to_bank,
            "amount": self.amount, "seq": self.seq,
            "accepted_at": self.accepted_at.isoformat(sep=" ", timespec="seconds"),
            "value_date": self.value_date.isoformat(), "channel": self.channel,
            "status": self.status.value,
            "settlement_date": self.settlement_date.isoformat() if self.settlement_date else None,
            "beneficiary": self.beneficiary, "remitter": self.remitter, "note": self.note,
            "history": self.history,
        }
