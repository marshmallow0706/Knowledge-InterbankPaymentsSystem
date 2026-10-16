"""全銀センター（模擬）。

役割:
  1. 電文の受信・形式検証・MAC 検証・二重受付チェック
  2. 時間帯判定（コアタイム / モアタイム）と予約（取扱日待ち）管理
  3. 大口（1億円以上）→ 日銀ネット RTGS、小口 → ネッティング計上
  4. 仕向超過限度額チェックと保留キュー
  5. 被仕向銀行への為替通知の中継（不達時はストア＆フォワード）
  6. 16:15 の資金決済の起動
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from .config import LARGE_VALUE_THRESHOLD
from .fixed import RecordError
from .models import Bank, TxRecord, TxStatus
from .telegram import MsgType, Telegram, verify_mac


@dataclass
class Ack:
    ok: bool
    status: TxStatus | None
    code: str = "00"
    message: str = ""
    tx_id: str | None = None


class ZenginCenter:
    def __init__(self, clock, cal, boj, risk, netting, settlement, fees, log):
        self.clock, self.cal, self.boj, self.risk = clock, cal, boj, risk
        self.netting, self.settlement, self.fees, self.log = netting, settlement, fees, log
        self.banks: dict[str, Bank] = {}
        self.nodes: dict = {}
        self.keys: dict[str, bytes] = {}
        self.records: dict[str, TxRecord] = {}
        self.seen: set[tuple[str, int]] = set()
        self.reserved: list[Telegram] = []
        self.held: list[Telegram] = []
        self.rtgs_queue: list[Telegram] = []
        self.undelivered: list[Telegram] = []
        self.core_up = True
        self.more_up = True
        self.stats: Counter = Counter()
        self._in_reeval = False

    # ------------------------------------------------------------------ 登録
    def register(self, bank: Bank, node, key: bytes) -> None:
        self.banks[bank.code] = bank
        self.nodes[bank.code] = node
        self.keys[bank.code] = key

    def sp(self, code: str) -> str:
        """資金決済を行う清算参加者のコード（代行決済委託先を解決）。"""
        b = self.banks[code]
        return code if b.is_direct else b.settlement_agent  # type: ignore[return-value]

    def service(self) -> str:
        return self.cal.service_window(self.clock.now)

    @staticmethod
    def tx_id(from_bank: str, seq: int) -> str:
        return f"{from_bank}-{seq:08d}"

    def _reject(self, code: str, msg: str) -> Ack:
        self.stats["rejected"] += 1
        self.log.add("CENTER", f"✗ 不受理 [{code}] {msg}")
        return Ack(False, TxStatus.REJECTED, code, msg)

    # ------------------------------------------------------------------ 受信
    def submit(self, raw: bytes, sender: str) -> Ack:
        self.stats["received"] += 1
        if sender not in self.keys:
            return self._reject("E02", f"未登録の送信元 {sender}")
        try:
            tg = Telegram.from_bytes(raw)
        except RecordError as e:
            return self._reject("E01", f"電文形式エラー: {e}")
        if not verify_mac(raw, self.keys[sender]):
            return self._reject("E03", f"MAC 検証エラー（{sender} 通番 {tg.seq}）")
        if tg.from_bank != sender:
            return self._reject("E04", f"仕向銀行コード {tg.from_bank} が送信元 {sender} と不一致")
        if (sender, tg.seq) in self.seen:
            return self._reject("E05", f"二重受付（{sender} 通番 {tg.seq}）")
        if tg.to_bank not in self.banks:
            return self._reject("E06", f"被仕向金融機関コード {tg.to_bank} は未登録")
        svc = self.service()
        if (svc == "core" and not self.core_up) or (svc == "more" and not self.more_up):
            return self._reject("E09", f"{'コアタイム' if svc == 'core' else 'モアタイム'}システム停止中")
        if tg.msg_type in MsgType.FUNDS and tg.amount <= 0 and tg.msg_type != MsgType.RECALL_RESP:
            return self._reject("E11", "金額が0以下")
        if tg.value_date < self.clock.now.date() and tg.msg_type in (MsgType.TRANSFER, MsgType.TRANSFER_EDI):
            return self._reject("E12", f"取扱日 {tg.value_date} が過去日")
        self.seen.add((sender, tg.seq))

        rec = TxRecord(
            tx_id=self.tx_id(tg.from_bank, tg.seq), msg_type=tg.msg_type,
            from_bank=tg.from_bank, to_bank=tg.to_bank, amount=tg.amount, seq=tg.seq,
            accepted_at=self.clock.now, value_date=tg.value_date,
            payer_sp=self.sp(tg.from_bank), payee_sp=self.sp(tg.to_bank),
            beneficiary=tg.beneficiary, remitter=tg.remitter,
        )
        self.records[rec.tx_id] = rec
        rec.set(TxStatus.ACCEPTED, self.clock.now)
        self.log.add("CENTER", f"受付 {rec.tx_id} {tg.name} {tg.from_bank}→{tg.to_bank} {tg.amount:,}円")

        if not tg.moves_funds:
            # 組戻依頼・金額0の組戻応答は資金移動を伴わない通知のみ
            rec.channel = svc
            self._deliver(tg, rec)
            return Ack(True, rec.status, tx_id=rec.tx_id)
        return self._route_funds(tg, rec)

    # ------------------------------------------------------------ ルーティング
    def _can_process_now(self, tg: Telegram) -> tuple[bool, str]:
        svc = self.service()
        large = tg.amount >= LARGE_VALUE_THRESHOLD
        if svc == "core":
            return (True, "") if self.core_up else (False, "コアタイム停止")
        if large:
            return False, "大口取引はコアタイムのみ取扱い"
        if not self.more_up:
            return False, "モアタイム停止"
        if not self.banks[tg.from_bank].moretime:
            return False, "仕向行がモアタイム非参加"
        if not self.banks[tg.to_bank].moretime:
            return False, "被仕向行がモアタイム非参加"
        return True, ""

    def _route_funds(self, tg: Telegram, rec: TxRecord) -> Ack:
        today = self.clock.now.date()
        if tg.value_date > today:
            return self._reserve(tg, rec, f"先日付 {tg.value_date}")
        ok, why = self._can_process_now(tg)
        if not ok:
            return self._reserve(tg, rec, why)
        return self._execute(tg, rec)

    def _reserve(self, tg: Telegram, rec: TxRecord, why: str) -> Ack:
        self.reserved.append(tg)
        rec.set(TxStatus.RESERVED, self.clock.now, why)
        self.log.add("CENTER", f"予約 {rec.tx_id}（{why}）")
        return Ack(True, rec.status, message=why, tx_id=rec.tx_id)

    def _execute(self, tg: Telegram, rec: TxRecord) -> Ack:
        if tg.amount >= LARGE_VALUE_THRESHOLD:
            return self._execute_large(tg, rec)
        return self._execute_small(tg, rec, check_limit=tg.msg_type in (MsgType.TRANSFER, MsgType.TRANSFER_EDI))

    def _execute_large(self, tg: Telegram, rec: TxRecord) -> Ack:
        rec.channel = "rtgs"
        payer, payee = rec.payer_sp, rec.payee_sp
        if payer == payee:
            rec.settlement_date = self.clock.now.date()
            self.log.add("RTGS", f"{rec.tx_id} 同一清算参加者内のため日銀ネット決済不要")
            self._deliver(tg, rec)
            return Ack(True, rec.status, tx_id=rec.tx_id)
        if self.boj.transfer(payer, payee, tg.amount, f"大口内為 {rec.tx_id}"):
            rec.settlement_date = self.clock.now.date()
            self.stats["rtgs"] += 1
            self.log.add("RTGS", f"{rec.tx_id} 日銀ネットで即時決済完了 → 為替通知を送信")
            self._fee(tg)
            self._deliver(tg, rec)
        else:
            self.rtgs_queue.append(tg)
            rec.set(TxStatus.PENDING_RTGS, self.clock.now, "仕向側の日銀当座預金残高不足")
            self.log.add("RTGS", f"{rec.tx_id} 残高不足のため RTGS 待ち行列へ")
        return Ack(True, rec.status, tx_id=rec.tx_id)

    def _execute_small(self, tg: Telegram, rec: TxRecord, check_limit: bool) -> Ack:
        payer, payee = rec.payer_sp, rec.payee_sp
        sd = self.cal.settlement_date_for(self.clock.now)
        if check_limit and payer != payee:
            if not self._in_reeval and any(
                    self.sp(h.from_bank) == payer and h.meta.get("hold_sd") == sd for h in self.held):
                # 同一清算参加者の保留取引がある場合は順序維持のため後ろに並ぶ（FIFO）
                return self._hold(tg, rec, "先行する保留取引あり", sd)
            nd = self.netting.net_debit(payer, sd)
            if not self.risk.fits(payer, nd, tg.amount):
                return self._hold(tg, rec, f"仕向超過額 {nd:,}円 + {tg.amount:,}円 > 限度額 {self.risk.cap(payer):,}円", sd)
        self._commit_small(tg, rec, sd)
        return Ack(True, rec.status, tx_id=rec.tx_id)

    def _hold(self, tg: Telegram, rec: TxRecord, why: str, sd: date) -> Ack:
        tg.meta["hold_sd"] = sd     # 保留は受付時点の決済日に紐づく（翌日分へは繰り越さない）
        self.held.append(tg)
        rec.set(TxStatus.HELD, self.clock.now, why)
        self.stats["held"] += 1
        self.log.add("RISK", f"保留 {rec.tx_id}: {why}")
        return Ack(True, rec.status, "W31", why, rec.tx_id)

    def _commit_small(self, tg: Telegram, rec: TxRecord, sd: date) -> None:
        rec.channel = self.service()
        rec.settlement_date = sd
        self.netting.record(sd, rec.payer_sp, rec.payee_sp, tg.amount)
        self.stats["small"] += 1
        self.log.add("NETTING", f"{rec.tx_id} を {sd} 決済分に計上 {rec.payer_sp}→{rec.payee_sp} {tg.amount:,}円")
        self._fee(tg)
        self._deliver(tg, rec)
        self._reevaluate_held()

    def _fee(self, tg: Telegram) -> None:
        if tg.msg_type in (MsgType.TRANSFER, MsgType.TRANSFER_EDI) and tg.from_bank != tg.to_bank:
            self.fees.add(tg.from_bank, tg.to_bank, self.clock.now)

    # ------------------------------------------------------------------ 中継
    def _deliver(self, tg: Telegram, rec: TxRecord) -> None:
        node = self.nodes[tg.to_bank]
        if not node.rc_up:
            if tg not in self.undelivered:
                self.undelivered.append(tg)
            rec.set(TxStatus.UNDELIVERED, self.clock.now, "被仕向行 RC 応答なし")
            self.log.add("CENTER", f"{rec.tx_id} 被仕向行 {tg.to_bank} の RC が応答しないため再送待ち")
            return
        raw = tg.to_bytes(self.keys[tg.to_bank])  # 被仕向行の鍵で再署名して中継
        code = node.receive(raw)
        rec.set(TxStatus.DELIVERED, self.clock.now, "" if code == "00" else f"応答 {code}")
        self.stats["delivered"] += 1
        if tg.msg_type in (MsgType.TRANSFER, MsgType.TRANSFER_EDI) and code == "00":
            rec.set(TxStatus.CREDITED, self.clock.now)
        node.after_receive()

    def notify_result(self, from_bank: str, seq: int, status: TxStatus, note: str = "") -> None:
        """被仕向行の処理結果（返却・組戻）を元取引の記録に反映する。"""
        rec = self.records.get(self.tx_id(from_bank, seq))
        if rec:
            rec.set(status, self.clock.now, note)

    # --------------------------------------------------------------- 定期処理
    def tick(self) -> None:
        self._release_reserved()
        self._retry_rtgs()
        self._retry_undelivered()
        self._reevaluate_held()

    def _release_reserved(self) -> None:
        today = self.clock.now.date()
        for tg in list(self.reserved):
            if tg.value_date > today:
                continue
            ok, _ = self._can_process_now(tg)
            if not ok:
                continue
            self.reserved.remove(tg)
            rec = self.records[self.tx_id(tg.from_bank, tg.seq)]
            self.log.add("CENTER", f"予約解放 {rec.tx_id}")
            self._execute(tg, rec)

    def _retry_rtgs(self) -> None:
        for tg in list(self.rtgs_queue):
            rec = self.records[self.tx_id(tg.from_bank, tg.seq)]
            if self.boj.transfer(rec.payer_sp, rec.payee_sp, tg.amount, f"大口内為 {rec.tx_id}（待ち行列から）"):
                self.rtgs_queue.remove(tg)
                rec.settlement_date = self.clock.now.date()
                self.stats["rtgs"] += 1
                self.log.add("RTGS", f"{rec.tx_id} 待ち行列から決済完了")
                self._fee(tg)
                self._deliver(tg, rec)

    def _retry_undelivered(self) -> None:
        for tg in list(self.undelivered):
            if self.nodes[tg.to_bank].rc_up:
                self.undelivered.remove(tg)
                rec = self.records[self.tx_id(tg.from_bank, tg.seq)]
                self.log.add("CENTER", f"{rec.tx_id} を再送")
                self._deliver(tg, rec)

    def _reevaluate_held(self) -> None:
        if self._in_reeval or not self.held:
            return
        self._in_reeval = True
        try:
            progressed = True
            while progressed:
                progressed = False
                blocked: set[str] = set()
                for tg in list(self.held):
                    payer = self.sp(tg.from_bank)
                    if payer in blocked:
                        continue
                    sd = self.cal.settlement_date_for(self.clock.now)
                    if tg.meta.get("hold_sd") != sd:
                        continue   # 決済日が変わった保留は解除せず、当該決済日の16:15に不受理
                    if self.risk.fits(payer, self.netting.net_debit(payer, sd), tg.amount):
                        self.held.remove(tg)
                        rec = self.records[self.tx_id(tg.from_bank, tg.seq)]
                        self.log.add("RISK", f"保留解除 {rec.tx_id}（限度額に余裕が生じた）")
                        self._commit_small(tg, rec, sd)
                        progressed = True
                    else:
                        blocked.add(payer)  # 先頭が通らない参加者の後続は待つ
        finally:
            self._in_reeval = False

    # --------------------------------------------------------------- 日次決済
    def end_of_day(self, d: date):
        """16:15 の処理。残存する保留・RTGS待ちを不受理として返し、資金決済を行う。"""
        for tg in list(self.held):
            if tg.meta.get("hold_sd", d) <= d:
                self.held.remove(tg)
                self._expire(tg, "決済時刻までに限度額内に収まらず不受理")
        for tg in list(self.rtgs_queue):
            self.rtgs_queue.remove(tg)
            self._expire(tg, "当日中に RTGS 決済できず不受理")
        return self.settlement.settle(d)

    def _expire(self, tg: Telegram, why: str) -> None:
        rec = self.records[self.tx_id(tg.from_bank, tg.seq)]
        rec.set(TxStatus.REJECTED, self.clock.now, why)
        self.log.add("CENTER", f"{rec.tx_id} {why} → 仕向行へ通知")
        self.nodes[tg.from_bank].on_rejected(tg.seq, why)
