"""コマンドラインインターフェース。

  python -m zengin_sim list                      シナリオ一覧
  python -m zengin_sim run normal [-v]           シナリオ実行（-v でイベントログ表示）
  python -m zengin_sim run all                   全シナリオ実行
  python -m zengin_sim gen-file out.txt -n 50    全銀協フォーマットのサンプル生成
  python -m zengin_sim parse-file out.txt        全銀協フォーマットの検証・表示
  python -m zengin_sim serve --port 8000         Web ダッシュボード起動
"""
from __future__ import annotations

import argparse
import random
import sys

from . import zengin_format as zf
from .kana import normalize_name
from .report import table, yen
from .scenarios import SCENARIOS


def _gen_file(path: str, n: int, seed: int) -> None:
    rng = random.Random(seed)
    names = ["ヤマダ タロウ", "スズキ ハナコ", "カブシキガイシャ ミライデンキ", "サトウ イチロウ",
             "ユウゲンガイシャ ハマベスイサン", "タナカ ミサキ", "ゴウドウガイシャ ホシゾラ"]
    f = zf.SogoFurikomiFile(irai_code="1234567890", irai_name=normalize_name("カブシキガイシャ アオバショウジ"),
                            torikumi_date="1016", bank_code="9001", bank_name="ｱｵﾊﾞ",
                            branch_code="001", branch_name="ﾎﾝﾃﾝ", acct_type=2, acct_no="2000001")
    for i in range(n):
        f.records.append(zf.FurikomiRecord(
            bank_code=rng.choice(["9002", "9003", "9101", "9102"]), branch_code=f"{rng.randint(100, 102):03d}",
            acct_type=1, acct_no=f"{rng.randint(1000001, 1000015):07d}",
            payee_name=normalize_name(rng.choice(names)), amount=rng.randint(1, 300) * 1000,
            edi_info=f"INV{i:06d}" if rng.random() < 0.5 else "",
        ))
    with open(path, "wb") as fp:
        fp.write(zf.build(f))
    print(f"{path} に {n}件（合計 {yen(f.total_amount)}）を書き出しました")


def _parse_file(path: str) -> int:
    with open(path, "rb") as fp:
        res = zf.parse(fp.read())
    if res.file is None:
        print("パース失敗:", *res.errors, sep="\n  ")
        return 1
    f = res.file
    print(f"種別 {zf.SHUBETSU.get(f.shubetsu)} / 依頼人 {f.irai_name} / 取組日 {f.torikumi_date} / "
          f"仕向 {f.bank_code}-{f.branch_code} {zf.ACCT_TYPES.get(f.acct_type)} {f.acct_no}")
    rows = [[i + 1, r.bank_code, r.branch_code, zf.ACCT_TYPES.get(r.acct_type), r.acct_no, r.payee_name,
             yen(r.amount), r.edi_info] for i, r in enumerate(f.records)]
    print(table(["#", "銀行", "支店", "種目", "口座", "受取人", "金額", "EDI"], rows, {6}))
    print(f"合計 {len(f.records)}件 {yen(f.total_amount)}")
    if res.errors:
        print("検証エラー:", *res.errors, sep="\n  ")
        return 1
    print("検証OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="zengin_sim", description="全銀システム模擬シミュレータ")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list", help="シナリオ一覧")
    r = sp.add_parser("run", help="シナリオ実行")
    r.add_argument("name", help="シナリオ名 または all")
    r.add_argument("-v", "--verbose", action="store_true", help="イベントログを逐次表示")
    r.add_argument("--log", help="イベントログを JSON Lines で保存")
    g = sp.add_parser("gen-file", help="全銀協フォーマット（総合振込）のサンプル生成")
    g.add_argument("path")
    g.add_argument("-n", type=int, default=20)
    g.add_argument("--seed", type=int, default=1)
    pf = sp.add_parser("parse-file", help="全銀協フォーマットの検証・表示")
    pf.add_argument("path")
    s = sp.add_parser("serve", help="Web ダッシュボード起動")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    a = p.parse_args(argv)

    if a.cmd == "list":
        for k, (_, desc) in SCENARIOS.items():
            print(f"  {k:<10} {desc}")
        return 0
    if a.cmd == "run":
        names = list(SCENARIOS) if a.name == "all" else [a.name]
        for n in names:
            if n not in SCENARIOS:
                print(f"不明なシナリオ: {n}（list で一覧）", file=sys.stderr)
                return 2
            sim = SCENARIOS[n][0](echo=a.verbose)
            if a.log and sim is not None:
                sim.log.dump_jsonl(a.log if len(names) == 1 else f"{n}_{a.log}")
        return 0
    if a.cmd == "gen-file":
        _gen_file(a.path, a.n, a.seed)
        return 0
    if a.cmd == "parse-file":
        return _parse_file(a.path)
    if a.cmd == "serve":
        from .web import serve
        serve(a.host, a.port)
        return 0
    return 1
