"""学習用シナリオ集。`python -m zengin_sim run <name>` で実行する。"""
from __future__ import annotations

from datetime import datetime

from . import zengin_format as zf
from .report import netting_table, section, sub, table, yen
from .telegram import MsgType, Telegram, hexdump
from .world import OKU, Simulation


def _names(sim: Simulation) -> dict[str, str]:
    return {c: n.bank.name for c, n in sim.nodes.items()}


def _corp(sim: Simulation, code: str, i: int = 0):
    return [a for a in sim.accounts_of(code) if a.acct_type == 2][i]


def _person(sim: Simulation, code: str, i: int = 0):
    return [a for a in sim.accounts_of(code) if a.acct_type == 1][i]


def _send(sim, frm, src, to, dst, amount, **kw):
    return sim.node(frm).transfer(src.key, to, dst.branch, dst.acct_type, dst.number, dst.holder, amount, **kw)


def _status(sim: Simulation, frm: str, st) -> str:
    rec = sim.center.records.get(sim.center.tx_id(frm, st.seq))
    return rec.status.value if rec else st.status.value


# ---------------------------------------------------------------------------
def normal_day(echo: bool = False) -> Simulation:
    section("シナリオ1: 平常日の為替処理と多角的ネッティング")
    sim = Simulation(datetime(2026, 10, 16, 8, 0), echo=echo)
    print("2026/10/16(金) 8:00 開始。8:30 コアタイム開始、9:00〜15:00 にランダムな振込を発生させます。")
    sim.run_until(sim.at("09:00"))
    total = 0
    for h in range(9, 15):
        sim.run_until(sim.at(f"{h:02d}:00"))
        total += sim.random_transfers(150)
    print(f"→ 振込 {total:,} 件を受付")
    sim.run_until(sim.at("16:00"))
    sub("16:00 時点のネッティング結果（決済日 2026-10-16）")
    print(netting_table(sim.netting.report(sim.clock.now.date()), _names(sim)))
    print("\n※ 代行決済委託先（信金・信組・資金移動業者）の受払は、委託先の清算参加者に合算されます。")
    sub("16:15 日銀当座預金での資金決済")
    before = {c: sim.boj.balance(c) for c in sim.boj.balances}
    sim.run_until(sim.at("16:20"))
    rows = [[c, _names(sim).get(c, "全銀ネット"), yen(before[c]), yen(sim.boj.balance(c)),
             yen(sim.boj.balance(c) - before[c])] for c in sim.boj.balances]
    print(table(["口座", "名義", "決済前", "決済後", "増減"], rows, {2, 3, 4}))
    print("\n全銀ネット口（ZNET）は CCP として一時的に資金を受けて払い出すため、決済後は 0 に戻ります。")
    sub("内国為替制度運営費（当月累計）")
    fees = sim.fees.summary("2026-10")
    print(table(["コード", "支払", "受取", "差引"],
                [[f["code"], yen(f["payable"]), yen(f["receivable"]), yen(f["net"])] for f in fees], {1, 2, 3}))
    return sim


def large_value(echo: bool = False) -> Simulation:
    section("シナリオ2: 大口内為取引（1億円以上）の RTGS 処理")
    sim = Simulation(datetime(2026, 10, 16, 9, 0), echo=echo)
    a, b = _corp(sim, "9001"), _corp(sim, "9003")
    print(f"9001 → 9003 に 3億円を振込。9001 の日銀当預 {yen(sim.boj.balance('9001'))}")
    st = _send(sim, "9001", a, "9003", b, 3 * OKU)
    print(f"→ 状態: {_status(sim, '9001', st)}（日銀ネットで即時決済後に為替通知）")
    sub("日銀当預が不足する場合（9003 から 9002 へ 50億円）")
    big = _corp(sim, "9003", 1)
    big.balance = 60 * OKU   # 顧客側の残高は十分にあると仮定
    print(f"9003 の日銀当預 {yen(sim.boj.balance('9003'))}")
    st2 = _send(sim, "9003", big, "9002", _corp(sim, "9002"), 50 * OKU)
    print(f"→ 状態: {_status(sim, '9003', st2)}（RTGS 待ち行列で資金を待つ）")
    sim.advance(30)
    print("10:00 9003 がコール市場等で 20億円 を調達したと仮定して入金")
    sim.boj.inject("9003", 20 * OKU, "コール資金調達(模擬)")
    sim.advance(1)
    print(f"→ 状態: {_status(sim, '9003', st2)}")
    sub("モアタイムに大口を依頼した場合")
    sim.run_until(sim.at("18:00"))
    st3 = _send(sim, "9001", a, "9002", _corp(sim, "9002"), 2 * OKU)
    print(f"18:00 に 2億円 → 状態: {_status(sim, '9001', st3)}")
    sim.run_until(datetime(2026, 10, 19, 8, 31))
    print(f"翌営業日 10/19(月) 8:31 → 状態: {_status(sim, '9001', st3)}")
    return sim


def moretime(echo: bool = False) -> Simulation:
    section("シナリオ3: モアタイム（平日夜間・土日祝）と翌営業日決済")
    sim = Simulation(datetime(2026, 10, 16, 20, 0), echo=echo)
    p1, p2 = _person(sim, "9001"), _person(sim, "9002")
    st1 = _send(sim, "9001", p1, "9002", p2, 30_000)
    print(f"10/16(金) 20:00 9001→9002 3万円 → {_status(sim, '9001', st1)}、受取人残高 {yen(p2.balance)}")
    rec = sim.center.records[sim.center.tx_id("9001", st1.seq)]
    print(f"   資金決済日: {rec.settlement_date}（土日を挟むため翌営業日 10/19）")
    sim.run_until(datetime(2026, 10, 17, 11, 0))
    st2 = _send(sim, "9002", p2, "9101", _person(sim, "9101"), 12_000)
    print(f"10/17(土) 11:00 9002→9101(信金) 1.2万円 → {_status(sim, '9002', st2)}")
    sub("モアタイム非参加の金融機関宛て")
    kr = _person(sim, "9102")
    st3 = _send(sim, "9001", p1, "9102", kr, 50_000)
    print(f"10/17(土) 9001→9102(モアタイム非参加の信組) 5万円 → {_status(sim, '9001', st3)}")
    print(f"   受取人残高 {yen(kr.balance)}（翌営業日のコアタイム開始まで入金されない）")
    sim.run_until(datetime(2026, 10, 19, 8, 31))
    print(f"10/19(月) 8:31 → {_status(sim, '9001', st3)}、受取人残高 {yen(kr.balance)}")
    sub("10/19 決済分のネッティング（金曜夜〜月曜日中の取引をまとめて決済）")
    print(netting_table(sim.netting.report(sim.clock.now.date()), _names(sim)))
    return sim


def limit_breach(echo: bool = False) -> Simulation:
    section("シナリオ4: 仕向超過限度額による保留と解除")
    sim = Simulation(datetime(2026, 10, 16, 9, 0), echo=echo)
    sim.risk.caps["9003"] = 50_000_000   # 学習用に限度額を 5,000万円 に引き下げ
    print(f"9003 の仕向超過限度額を {yen(sim.risk.cap('9003'))} に設定")
    src = _corp(sim, "9003")
    src.balance = 10 * OKU
    dst = _corp(sim, "9001")
    sts = [_send(sim, "9003", src, "9001", dst, 20_000_000) for _ in range(4)]
    for i, st in enumerate(sts, 1):
        print(f"  {i}件目 2,000万円 → {_status(sim, '9003', st)}")
    print(f"仕向超過額 {yen(sim.netting.net_debit('9003', sim.clock.now.date()))}、保留 {len(sim.center.held)} 件")
    sub("10:00 9001 から 9003 宛てに 2,500万円 の入金（受取が増え仕向超過額が減少）")
    sim.advance(60)
    _send(sim, "9001", _corp(sim, "9001", 1), "9003", _corp(sim, "9003", 1), 25_000_000)
    print(f"仕向超過額 {yen(sim.netting.net_debit('9003', sim.clock.now.date()))}（4件目は限度額を超えるため保留のまま）")
    for i, st in enumerate(sts, 1):
        print(f"  {i}件目 → {_status(sim, '9003', st)}")
    sub("16:15 まで限度額内に収まらない取引は不受理となり依頼人へ返金")
    sim.run_until(sim.at("16:20"))
    for i, st in enumerate(sts, 1):
        extra = f"（{st.note}／依頼人へ返金済）" if st.refunded else ""
        print(f"  {i}件目 → {_status(sim, '9003', st)}{extra}")
    return sim


def participant_default(echo: bool = False) -> Simulation:
    section("シナリオ5: 清算参加者の決済不能と流動性供給・担保処分")
    sim = Simulation(datetime(2026, 10, 16, 9, 0), echo=echo)
    src = _corp(sim, "9003")
    src.balance = 100 * OKU
    for i in range(25):   # 1件 9,999万9,999円（1億円未満＝小口）× 25件
        _send(sim, "9003", src, "9001", _corp(sim, "9001", i % 6), OKU - 1)
    nd = sim.netting.net_debit("9003", sim.clock.now.date())
    print(f"9003 の仕向超過額 {yen(nd)}（限度額 {yen(sim.risk.cap('9003'))} 以内なので受付）")
    sim.run_until(sim.at("15:00"))
    print(f"15:00 9003 が大口支払等で日銀当預を減らし、残高 {yen(sim.boj.balance('9003'))} → 5億円 に")
    sim.boj.balances["9003"] = 5 * OKU
    sub("16:15 資金決済")
    sim.run_until(sim.at("16:20"))
    res = sim.settlement.results[sim.clock.now.date()]
    print(res.summary())
    for d in res.defaults:
        print(f"  不履行参加者 {d['participant']} 不足額 {yen(d['shortfall'])}")
        for p, a in d["liquidity"]:
            print(f"    流動性供給 {p}: {yen(a)}")
        print(f"    担保処分代り金 {yen(d['collateral_raised'])} → 流動性供給銀行へ返済")
    print("→ 受取側の参加者には予定どおり資金が支払われ、決済は完了（決済完了性の確保）")
    print(f"9003 の残存担保 {yen(sim.risk.collateral_value('9003'))}、限度額 {yen(sim.risk.cap('9003'))}")
    return sim


def rc_failure(echo: bool = False) -> Simulation:
    section("シナリオ6: 中継コンピュータ（RC）障害 — 2023年10月障害を模した例")
    sim = Simulation(datetime(2026, 10, 16, 8, 0), echo=echo)
    print("8:00 RC を新機種へ切替えた 9001 の RC が、コアタイム開始時に停止したと仮定")
    sim.node("9001").set_rc(False)
    sim.run_until(sim.at("09:00"))
    out = [_send(sim, "9001", _person(sim, "9001", i), "9002", _person(sim, "9002", i), 100_000 + i)
           for i in range(5)]
    inc = [_send(sim, "9002", _person(sim, "9002", i), "9001", _person(sim, "9001", i), 200_000 + i)
           for i in range(5)]
    print(f"9001 発の振込 5件 → {_status(sim, '9001', out[0])}（9001 の RC に滞留: {len(sim.node('9001').outbox)}件）")
    print(f"9001 宛の振込 5件 → {_status(sim, '9002', inc[0])}（センター側で再送待ち: {len(sim.center.undelivered)}件）")
    sub("影響")
    print("・仕向: 顧客口座は引き落とされたが他行へ届かない")
    print("・被仕向: センターは受付済（決済には計上）だが受取人に入金されない")
    sim.run_until(sim.at("13:00"))
    print("\n13:00 暫定対処で RC 復旧")
    sim.node("9001").set_rc(True)
    sim.advance(1)
    print(f"9001 発 → {_status(sim, '9001', out[0])} / 9001 宛 → {_status(sim, '9002', inc[0])}")
    print(f"残滞留: RC {len(sim.node('9001').outbox)}件 / センター {len(sim.center.undelivered)}件")
    return sim


def recall_and_return(echo: bool = False) -> Simulation:
    section("シナリオ7: 入金不能返却と組戻")
    sim = Simulation(datetime(2026, 10, 16, 10, 0), echo=echo)
    p = _person(sim, "9001")
    print(f"依頼人 {p.holder} 残高 {yen(p.balance)}")
    sub("(1) 存在しない口座宛て → 被仕向行が入金不能として返却")
    st = sim.node("9001").transfer(p.key, "9002", "100", 1, "9999999", "ﾀﾞﾚﾓ ｲﾅｲ", 50_000)
    print(f"→ {_status(sim, '9001', st)}（{st.note}）、依頼人残高 {yen(p.balance)}")
    sub("(2) 名義相違 → 返却")
    dst = _person(sim, "9002")
    st = sim.node("9001").transfer(p.key, "9002", dst.branch, 1, dst.number, "ﾍﾞﾂﾉ ﾋﾄ", 40_000)
    print(f"→ {_status(sim, '9001', st)}（{st.note}）")
    sub("(3) 誤振込 → 組戻依頼 → 受取人同意で資金返還")
    st = _send(sim, "9001", p, "9002", dst, 70_000)
    print(f"振込 → {_status(sim, '9001', st)}、受取人残高 {yen(dst.balance)}")
    sim.node("9001").request_recall(st.seq)
    print(f"組戻後 → {_status(sim, '9001', st)}、受取人残高 {yen(dst.balance)}、依頼人残高 {yen(p.balance)}")
    sub("(4) 受取人が不同意の場合")
    sim.node("9002").recall_consent = False
    st = _send(sim, "9001", p, "9002", dst, 30_000)
    sim.node("9001").request_recall(st.seq)
    print(f"→ {_status(sim, '9001', st)}（{st.note}）")
    return sim


def bulk_file(echo: bool = False, path: str | None = None) -> Simulation:
    section("シナリオ8: 全銀協フォーマット（総合振込）ファイルの一括処理")
    sim = Simulation(datetime(2026, 10, 16, 9, 0), echo=echo)
    payer = _corp(sim, "9001")
    f = zf.SogoFurikomiFile(irai_code="1234567890", irai_name=payer.holder, torikumi_date="1016",
                            bank_code="9001", bank_name="ｱｵﾊﾞ", branch_code=payer.branch,
                            branch_name="ﾎﾝﾃﾝ", acct_type=2, acct_no=payer.number)
    for code in ("9002", "9003", "9101", "9102", "9500"):
        for a in sim.accounts_of(code)[:4]:
            f.records.append(zf.FurikomiRecord(code, a.branch, a.acct_type, a.number, a.holder,
                                               sim.rng.randint(1, 50) * 10_000,
                                               edi_info="INV2026-10-%04d" % len(f.records)))
    raw = zf.build(f)
    if path:
        with open(path, "wb") as fp:
            fp.write(raw)
        print(f"ファイルを書き出しました: {path}")
    print(f"生成: {len(f.records)}件 合計 {yen(f.total_amount)} / {len(raw)}バイト")
    print("先頭2レコード:")
    for line in raw.split(b"\r\n")[:2]:
        print("  " + line.decode("cp932"))
    res = zf.parse(raw)
    print(f"パース結果: {'OK' if res.ok else res.errors}")
    ok = ng = 0
    for r in res.file.records:
        try:
            sim.node("9001").transfer(payer.key, r.bank_code, r.branch_code, r.acct_type, r.acct_no,
                                      r.payee_name, r.amount, edi=r.edi_info)
            ok += 1
        except Exception as e:  # noqa: BLE001
            ng += 1
            print("  エラー:", e)
    print(f"送信 {ok}件 / エラー {ng}件")
    by = {}
    for rec in sim.center.records.values():
        by[rec.status.value] = by.get(rec.status.value, 0) + 1
    print("センター側の状態:", by)
    return sim


def telegram_demo(echo: bool = False) -> None:
    section("付録: 模擬為替通知電文のダンプ")
    tg = Telegram(MsgType.TRANSFER_EDI, 1, datetime(2026, 10, 16, 9, 30), datetime(2026, 10, 16).date(),
                  "9001", "001", "9002", "100", 1, "1000001", "ﾔﾏﾀﾞ ﾀﾛｳ", "ｶ)ｱｵﾊﾞｼﾖｳｼﾞ",
                  123_456, edi="INV-2026-0001")
    raw = tg.to_bytes(b"demo-key")
    print(f"電文長 {len(raw)} バイト（本体 178 + MAC 16）")
    print(hexdump(raw))
    back = Telegram.from_bytes(raw)
    print("\nデコード:", {k: v for k, v in back.__dict__.items() if k != "meta"})


SCENARIOS = {
    "normal": (normal_day, "平常日の為替処理と多角的ネッティング・16:15決済"),
    "large": (large_value, "大口内為取引（1億円以上）のRTGS処理と待ち行列"),
    "moretime": (moretime, "モアタイム（夜間・休日）と翌営業日決済、非参加行宛て"),
    "limit": (limit_breach, "仕向超過限度額による保留・解除・不受理"),
    "default": (participant_default, "決済不能時の流動性供給と担保処分"),
    "rc": (rc_failure, "RC障害時の滞留とストア＆フォワード（2023年障害の模擬）"),
    "recall": (recall_and_return, "入金不能返却と組戻"),
    "file": (bulk_file, "全銀協フォーマット（総合振込）ファイルの一括処理"),
    "telegram": (telegram_demo, "模擬電文のバイナリダンプ"),
}
