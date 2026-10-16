"""参加金融機関（勘定系 + 中継コンピュータ RC）の模擬。

- 勘定系: 顧客口座の入出金、振込受付、名義照合、入金不能・組戻の判断
- RC    : 電文への変換、通番採番、MAC 付与、センター不通時の滞留（ストア＆フォワード）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .config import LARGE_VALUE_THRESHOLD
from .kana import name_key, normalize_name
from .models import Account, Bank, TxStatus
from .telegram import MsgType, Reason, Telegram, verify_mac


class TransferError(Exception):
    pass


@dataclass
class SentTransfer:
    seq: int
    src: tuple[str, int, str]
    to_bank: str
    to_branch: str
    acct_type: int
    acct_no: str
    beneficiary: str
    amount: int
    value_date: date
    status: TxStatus = TxStatus.ACCEPTED
    note: str = ""
    refunded: bool = False


@dataclass
class ReceivedTransfer:
    from_bank: str
    seq: int
    acct_key: tuple[str, int, str]
    amount: int
    recalled: bool = False


@dataclass
class BankStats:
    sent: int = 0
    received: int = 0
    returned: int = 0
    intra: int = 0


class BankNode:
    def __init__(self, bank: Bank, center, clock, cal, log, key: bytes):
        self.bank = bank
        self.center = center
        self.clock = clock
        self.cal = cal
        self.log = log
        self.key = key
        self.accounts: dict[tuple[str, int, str], Account] = {}
        self.rc_up = True
        self.outbox: list[Telegram] = []
        self.pending_out: list[Telegram] = []
        self.sent: dict[int, SentTransfer] = {}
        self.received: dict[tuple[str, int], ReceivedTransfer] = {}
        self.suspense = 0                # 別段預金（入金不能資金の一時保管）
        self.recall_consent = True       # 組戻依頼に受取人が同意するか（模擬）
        self.stats = BankStats()
        self._seq = 0

    @property
    def code(self) -> str:
        return self.bank.code

    # ---------------------------------------------------------------- 口座
    def open_account(self, branch: str, acct_type: int, number: str, holder: str, balance: int = 0) -> Account:
        acct = Account(self.code, branch, acct_type, number, normalize_name(holder), balance)
        self.accounts[acct.key] = acct
        return acct

    def find(self, branch: str, acct_type: int, number: str) -> Account | None:
        return self.accounts.get((branch, acct_type, number))

    def total_deposits(self) -> int:
        return sum(a.balance for a in self.accounts.values())

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    # ---------------------------------------------------------------- 仕向
    def transfer(self, src: tuple[str, int, str], to_bank: str, to_branch: str, to_type: int,
                 to_no: str, beneficiary: str, amount: int, edi: str = "",
                 value_date: date | None = None) -> SentTransfer:
        """顧客の振込依頼を受け付け、電文を作成して全銀センターへ送る。"""
        acct = self.accounts.get(src)
        if acct is None:
            raise TransferError(f"依頼人口座が存在しません: {src}")
        if acct.frozen or acct.closed:
            raise TransferError("依頼人口座が利用できません")
        if amount <= 0:
            raise TransferError("振込金額が不正です")
        if acct.balance < amount:
            raise TransferError(f"残高不足（残高 {acct.balance:,}円 / 依頼 {amount:,}円）")
        bene = normalize_name(beneficiary)
        vd = value_date or self.clock.now.date()

        if to_bank == self.code:   # 自行内振替（全銀システムを経由しない）
            dst = self.find(to_branch, to_type, to_no)
            if dst is None:
                raise TransferError("振込先口座が存在しません（自行内）")
            acct.balance -= amount
            dst.balance += amount
            self.stats.intra += 1
            self.log.add("BANK", f"{self.code} 自行内振替 {amount:,}円 → {dst.holder}")
            st = SentTransfer(0, src, to_bank, to_branch, to_type, to_no, bene, amount, vd, TxStatus.CREDITED)
            return st

        seq = self._next_seq()
        acct.balance -= amount       # 依頼人口座から引落し（仕向為替の未決済勘定へ）
        tg = Telegram(
            msg_type=MsgType.TRANSFER_EDI if edi else MsgType.TRANSFER, seq=seq,
            send_at=self.clock.now, value_date=vd, from_bank=self.code, from_branch=src[0],
            to_bank=to_bank, to_branch=to_branch, acct_type=to_type, acct_no=to_no,
            beneficiary=bene, remitter=acct.holder, amount=amount, edi=edi,
        )
        st = SentTransfer(seq, src, to_bank, to_branch, to_type, to_no, bene, amount, vd)
        self.sent[seq] = st
        self.stats.sent += 1
        kind = "大口" if amount >= LARGE_VALUE_THRESHOLD else "小口"
        self.log.add("BANK", f"{self.code} 振込受付 通番{seq} {kind} {amount:,}円 → {to_bank}-{to_branch} {bene}")
        self._send_or_queue(tg)
        return st

    def request_recall(self, seq: int) -> None:
        """組戻依頼（誤振込など）を被仕向行へ送る。"""
        st = self.sent.get(seq)
        if st is None:
            raise TransferError(f"通番 {seq} の振込はありません")
        tg = Telegram(
            msg_type=MsgType.RECALL_REQ, seq=self._next_seq(), send_at=self.clock.now,
            value_date=self.clock.now.date(), from_bank=self.code, from_branch=st.src[0],
            to_bank=st.to_bank, to_branch=st.to_branch, acct_type=st.acct_type, acct_no=st.acct_no,
            beneficiary=st.beneficiary, remitter=self.accounts[st.src].holder, amount=st.amount,
            ref_seq=seq,
        )
        self.log.add("BANK", f"{self.code} 組戻依頼 元通番{seq} {st.amount:,}円")
        self._send_or_queue(tg)

    def _send_or_queue(self, tg: Telegram) -> None:
        if not self.rc_up:
            self.outbox.append(tg)
            if tg.msg_type in (MsgType.TRANSFER, MsgType.TRANSFER_EDI):
                self.sent[tg.seq].status = TxStatus.QUEUED_AT_BANK
            self.log.add("RC", f"{self.code} RC 停止中 → 通番{tg.seq} を滞留（滞留 {len(self.outbox)}件）")
            return
        raw = tg.to_bytes(self.key)
        ack = self.center.submit(raw, self.code)
        st = self.sent.get(tg.seq) if tg.msg_type in (MsgType.TRANSFER, MsgType.TRANSFER_EDI) else None
        if st is None:
            return
        if not ack.ok:
            st.status = TxStatus.REJECTED
            st.note = f"{ack.code} {ack.message}"
            self._refund(st, "センター不受理")
        elif ack.status is not None and st.status not in (TxStatus.RETURNED, TxStatus.RECALLED):
            # 着信時点で入金済になる場合、center 側の記録で CREDITED になっている
            rec = self.center.records.get(self.center.tx_id(self.code, tg.seq))
            st.status = rec.status if rec else ack.status
            st.note = ack.message

    def set_rc(self, up: bool) -> None:
        self.rc_up = up
        self.log.add("RC", f"{self.code} RC {'復旧' if up else '停止'}")
        if up:
            self.flush_outbox()

    def flush_outbox(self) -> int:
        n = 0
        while self.outbox and self.rc_up:
            tg = self.outbox.pop(0)
            tg.send_at = self.clock.now
            self._send_or_queue(tg)
            n += 1
        if n:
            self.log.add("RC", f"{self.code} 滞留電文 {n}件 を送信")
        return n

    def _refund(self, st: SentTransfer, why: str) -> None:
        if st.refunded:
            return
        acct = self.accounts.get(st.src)
        if acct:
            acct.balance += st.amount
        st.refunded = True
        self.log.add("BANK", f"{self.code} 依頼人へ返金 通番{st.seq} {st.amount:,}円（{why}）")

    def on_rejected(self, seq: int, why: str) -> None:
        st = self.sent.get(seq)
        if st:
            st.status = TxStatus.REJECTED
            st.note = why
            self._refund(st, why)

    # ---------------------------------------------------------------- 被仕向
    def receive(self, raw: bytes) -> str:
        """全銀センターから中継された電文を処理し、応答コードを返す。"""
        if not verify_mac(raw, self.key):
            self.log.add("ERROR", f"{self.code} 受信電文の MAC 不一致")
            return "E03"
        tg = Telegram.from_bytes(raw)
        if tg.msg_type in (MsgType.TRANSFER, MsgType.TRANSFER_EDI):
            return self._receive_transfer(tg)
        if tg.msg_type == MsgType.RECALL_REQ:
            return self._receive_recall_req(tg)
        if tg.msg_type == MsgType.RECALL_RESP:
            return self._receive_recall_resp(tg)
        if tg.msg_type == MsgType.RETURN:
            return self._receive_return(tg)
        return "E99"

    def after_receive(self) -> None:
        """受信処理中に生成した応答電文（返却・組戻応答）を送信する。"""
        while self.pending_out:
            self._send_or_queue(self.pending_out.pop(0))

    def _receive_transfer(self, tg: Telegram) -> str:
        self.stats.received += 1
        acct = self.find(tg.to_branch, tg.acct_type, tg.acct_no)
        reason = Reason.OK
        if acct is None:
            reason = Reason.NO_ACCOUNT
        elif acct.closed:
            reason = Reason.CLOSED
        elif acct.frozen:
            reason = Reason.FROZEN
        elif name_key(acct.holder) != name_key(tg.beneficiary):
            reason = Reason.NAME_MISMATCH
        if reason != Reason.OK:
            self.suspense += tg.amount
            self.log.add("BANK", f"{self.code} 入金不能 {tg.from_bank}通番{tg.seq} {tg.amount:,}円"
                                 f"（{Reason.NAMES[reason]}）→ 別段預金に留保し返却")
            self.pending_out.append(self._reply(tg, MsgType.RETURN, tg.amount, reason))
            return f"{reason:02d}"
        acct.balance += tg.amount
        self.received[(tg.from_bank, tg.seq)] = ReceivedTransfer(tg.from_bank, tg.seq, acct.key, tg.amount)
        self.log.add("BANK", f"{self.code} 入金 {acct.holder} +{tg.amount:,}円（{tg.from_bank}通番{tg.seq}）")
        return "00"

    def _receive_recall_req(self, tg: Telegram) -> str:
        rt = self.received.get((tg.from_bank, tg.ref_seq))
        if rt is None or rt.recalled:
            self.pending_out.append(self._reply(tg, MsgType.RECALL_RESP, 0, Reason.NOT_FOUND))
            return "00"
        acct = self.accounts[rt.acct_key]
        if self.recall_consent and acct.balance >= rt.amount:
            acct.balance -= rt.amount
            rt.recalled = True
            self.log.add("BANK", f"{self.code} 組戻に受取人同意 {rt.amount:,}円 を返還")
            self.pending_out.append(self._reply(tg, MsgType.RECALL_RESP, rt.amount, Reason.RECALL_AGREED))
        else:
            self.log.add("BANK", f"{self.code} 組戻不成立（受取人不同意または残高不足）")
            self.pending_out.append(self._reply(tg, MsgType.RECALL_RESP, 0, Reason.RECALL_REFUSED))
        return "00"

    def _receive_recall_resp(self, tg: Telegram) -> str:
        st = self.sent.get(tg.ref_seq)
        if st is None:
            return "23"
        if tg.amount > 0:
            st.status = TxStatus.RECALLED
            self._refund(st, "組戻成立")
            self.center.notify_result(self.code, tg.ref_seq, TxStatus.RECALLED)
        else:
            st.status = TxStatus.RECALL_REFUSED
            st.note = Reason.NAMES.get(tg.reason, "")
            self.center.notify_result(self.code, tg.ref_seq, TxStatus.RECALL_REFUSED, st.note)
        return "00"

    def _receive_return(self, tg: Telegram) -> str:
        st = self.sent.get(tg.ref_seq)
        if st is None:
            return "23"
        self.stats.returned += 1
        st.status = TxStatus.RETURNED
        st.note = Reason.NAMES.get(tg.reason, "")
        self._refund(st, f"入金不能返却: {st.note}")
        self.center.notify_result(self.code, tg.ref_seq, TxStatus.RETURNED, st.note)
        return "00"

    def _reply(self, orig: Telegram, msg_type: int, amount: int, reason: int) -> Telegram:
        if msg_type == MsgType.RETURN:
            self.suspense -= amount
        return Telegram(
            msg_type=msg_type, seq=self._next_seq(), send_at=self.clock.now,
            value_date=self.clock.now.date(), from_bank=self.code, from_branch=orig.to_branch,
            to_bank=orig.from_bank, to_branch=orig.from_branch, acct_type=0, acct_no="0000000",
            beneficiary=orig.remitter[:30], remitter=self.bank.kana, amount=amount,
            ref_seq=orig.seq if msg_type == MsgType.RETURN else orig.ref_seq, reason=reason,
        )
