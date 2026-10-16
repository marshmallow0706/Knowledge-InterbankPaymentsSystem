"""銀行間の為替通知電文（模擬）。

実際の全銀システムの電文仕様（全銀センターと RC の間のプロトコル）は非公開。
本モジュールは「固定長・項目定義・メッセージ認証」という考え方を学ぶための
独自フォーマットであり、実在の仕様とは一致しない。

1電文 = 本体 178 バイト + MAC 16 バイト（HMAC-SHA256 の先頭8バイトを16進表記）
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from .config import MAC_BYTES
from .fixed import Layout, RecordError


class MsgType:
    TRANSFER = 1001          # 振込（為替通知）
    TRANSFER_EDI = 1002      # 振込（EDI情報付き）
    RECALL_REQ = 2001        # 組戻依頼
    RECALL_RESP = 2002       # 組戻応答（金額>0 なら資金返還を伴う）
    RETURN = 3001            # 返却（入金不能による資金返還）

    NAMES = {1001: "振込", 1002: "振込(EDI)", 2001: "組戻依頼", 2002: "組戻応答", 3001: "入金不能返却"}
    FUNDS = {1001, 1002, 2002, 3001}


class Reason:
    OK = 0
    NO_ACCOUNT = 11          # 該当口座なし
    CLOSED = 12              # 口座解約済
    NAME_MISMATCH = 13       # 受取人名相違
    FROZEN = 14              # 支払停止・凍結
    RECALL_AGREED = 21       # 組戻同意
    RECALL_REFUSED = 22      # 組戻不同意（受取人不同意・残高不足）
    NOT_FOUND = 23           # 該当取引なし

    NAMES = {0: "正常", 11: "該当口座なし", 12: "口座解約済", 13: "受取人名相違",
             14: "支払停止口座", 21: "組戻同意", 22: "組戻不同意", 23: "該当取引なし"}


BODY = Layout("為替通知電文(模擬)", [
    ("msg_type", 4, "N"),
    ("seq", 8, "N"),            # 仕向銀行が採番する電文通番
    ("send_date", 8, "N"),      # YYYYMMDD
    ("send_time", 6, "N"),      # HHMMSS
    ("value_date", 8, "N"),     # 取扱日 YYYYMMDD
    ("from_bank", 4, "N"),
    ("from_branch", 3, "N"),
    ("to_bank", 4, "N"),
    ("to_branch", 3, "N"),
    ("acct_type", 1, "N"),
    ("acct_no", 7, "N"),
    ("beneficiary", 30, "X"),   # 受取人名（半角カナ）
    ("remitter", 40, "X"),      # 依頼人名（半角カナ）
    ("amount", 12, "N"),
    ("edi", 20, "X"),
    ("ref_seq", 8, "N"),        # 組戻・返却時の元電文通番
    ("reason", 2, "N"),
    ("reserve", 10, "X"),
])
MAC_HEX_LEN = MAC_BYTES * 2
TOTAL_LEN = BODY.length + MAC_HEX_LEN


@dataclass
class Telegram:
    msg_type: int
    seq: int
    send_at: datetime
    value_date: date
    from_bank: str
    from_branch: str
    to_bank: str
    to_branch: str
    acct_type: int
    acct_no: str
    beneficiary: str
    remitter: str
    amount: int
    edi: str = ""
    ref_seq: int = 0
    reason: int = 0
    meta: dict = field(default_factory=dict, compare=False)  # 電文には載らない模擬用の付帯情報

    @property
    def name(self) -> str:
        return MsgType.NAMES.get(self.msg_type, str(self.msg_type))

    @property
    def moves_funds(self) -> bool:
        return self.msg_type in MsgType.FUNDS and self.amount > 0

    def body_bytes(self) -> bytes:
        return BODY.pack({
            "msg_type": self.msg_type, "seq": self.seq,
            "send_date": self.send_at.strftime("%Y%m%d"),
            "send_time": self.send_at.strftime("%H%M%S"),
            "value_date": self.value_date.strftime("%Y%m%d"),
            "from_bank": self.from_bank, "from_branch": self.from_branch,
            "to_bank": self.to_bank, "to_branch": self.to_branch,
            "acct_type": self.acct_type, "acct_no": self.acct_no,
            "beneficiary": self.beneficiary, "remitter": self.remitter,
            "amount": self.amount, "edi": self.edi,
            "ref_seq": self.ref_seq, "reason": self.reason, "reserve": "",
        })

    def to_bytes(self, key: bytes) -> bytes:
        body = self.body_bytes()
        return body + compute_mac(body, key).encode("ascii")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Telegram":
        if len(raw) != TOTAL_LEN:
            raise RecordError(f"電文長 {len(raw)} != {TOTAL_LEN}")
        d = BODY.unpack(raw[: BODY.length])
        try:
            send_at = datetime.strptime(f"{d['send_date']:08d}{d['send_time']:06d}", "%Y%m%d%H%M%S")
            value_date = datetime.strptime(f"{d['value_date']:08d}", "%Y%m%d").date()
        except ValueError as e:
            raise RecordError(f"日付項目が不正: {e}") from e
        return cls(
            msg_type=d["msg_type"], seq=d["seq"], send_at=send_at, value_date=value_date,
            from_bank=f"{d['from_bank']:04d}", from_branch=f"{d['from_branch']:03d}",
            to_bank=f"{d['to_bank']:04d}", to_branch=f"{d['to_branch']:03d}",
            acct_type=d["acct_type"], acct_no=f"{d['acct_no']:07d}",
            beneficiary=d["beneficiary"], remitter=d["remitter"], amount=d["amount"],
            edi=d["edi"], ref_seq=d["ref_seq"], reason=d["reason"],
        )

    def copy(self, **kw) -> "Telegram":
        return replace(self, meta=dict(self.meta), **kw)


def compute_mac(body: bytes, key: bytes) -> str:
    return hmac.new(key, body, hashlib.sha256).digest()[:MAC_BYTES].hex().upper()


def verify_mac(raw: bytes, key: bytes) -> bool:
    if len(raw) != TOTAL_LEN:
        return False
    body, mac = raw[: BODY.length], raw[BODY.length:]
    return hmac.compare_digest(compute_mac(body, key).encode("ascii"), mac)


def hexdump(raw: bytes, width: int = 32) -> str:
    """電文のダンプ表示（デバッグ・学習用）。"""
    lines = []
    for i in range(0, len(raw), width):
        chunk = raw[i:i + width]
        hx = " ".join(f"{b:02X}" for b in chunk)
        txt = chunk.decode("cp932", errors="replace").replace("\n", ".")
        lines.append(f"{i:04X}  {hx:<{width * 3}} {txt}")
    return "\n".join(lines)
