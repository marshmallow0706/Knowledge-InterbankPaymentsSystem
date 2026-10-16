"""全銀協規定フォーマット（総合振込・120バイト固定長）の生成とパース。

企業が取引銀行へ振込データを渡す際に広く使われている公開フォーマット。
構成: ヘッダー(1) → データ(2)×n → トレーラー(8) → エンド(9)

※ 本実装は学習用。各銀行のサービス固有の取扱い（任意項目の扱い、
  1ファイルあたり件数上限など）は再現していない。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .fixed import Layout, RecordError
from .kana import is_valid_zengin

RECORD_LEN = 120

HEADER = Layout("ヘッダーレコード", [
    ("data_kubun", 1, "N"),       # 1
    ("shubetsu", 2, "N"),         # 21=総合振込, 11=給与, 12=賞与
    ("code_kubun", 1, "N"),       # 0=JIS(SJIS), 1=EBCDIC
    ("irai_code", 10, "N"),       # 依頼人コード（銀行が付与）
    ("irai_name", 40, "X"),       # 依頼人名（半角カナ）
    ("torikumi_date", 4, "N"),    # 取組日 MMDD
    ("bank_code", 4, "N"),        # 仕向銀行番号
    ("bank_name", 15, "X"),
    ("branch_code", 3, "N"),      # 仕向支店番号
    ("branch_name", 15, "X"),
    ("acct_type", 1, "N"),        # 1=普通 2=当座 9=その他
    ("acct_no", 7, "N"),          # 依頼人口座番号
    ("dummy", 17, "X"),
])

DATA = Layout("データレコード", [
    ("data_kubun", 1, "N"),       # 2
    ("bank_code", 4, "N"),        # 被仕向銀行番号
    ("bank_name", 15, "X"),
    ("branch_code", 3, "N"),      # 被仕向支店番号
    ("branch_name", 15, "X"),
    ("clearing_house", 4, "N"),   # 手形交換所番号（現在は未使用・任意）
    ("acct_type", 1, "N"),        # 1=普通 2=当座 4=貯蓄 9=その他
    ("acct_no", 7, "N"),
    ("payee_name", 30, "X"),      # 受取人名（半角カナ）
    ("amount", 10, "N"),          # 振込金額
    ("new_code", 1, "N"),         # 0=その他 1=第1回 2=変更分
    ("customer_code1", 10, "X"),  # 顧客コード1 （EDI時は EDI情報前半）
    ("customer_code2", 10, "X"),  # 顧客コード2 （EDI時は EDI情報後半）
    ("transfer_type", 1, "N"),    # 振込指定区分 7=テレ振込 8=文書振込
    ("edi_flag", 1, "X"),         # 識別表示 'Y'=EDI情報 / ' '
    ("dummy", 7, "X"),
])

TRAILER = Layout("トレーラーレコード", [
    ("data_kubun", 1, "N"),       # 8
    ("total_count", 6, "N"),
    ("total_amount", 12, "N"),
    ("dummy", 101, "X"),
])

END = Layout("エンドレコード", [
    ("data_kubun", 1, "N"),       # 9
    ("dummy", 119, "X"),
])

for _l in (HEADER, DATA, TRAILER, END):
    assert _l.length == RECORD_LEN, (_l.name, _l.length)

ACCT_TYPES = {1: "普通", 2: "当座", 4: "貯蓄", 9: "その他"}
SHUBETSU = {21: "総合振込", 11: "給与振込", 12: "賞与振込"}


@dataclass
class FurikomiRecord:
    bank_code: str
    branch_code: str
    acct_type: int
    acct_no: str
    payee_name: str
    amount: int
    bank_name: str = ""
    branch_name: str = ""
    edi_info: str = ""
    customer_code1: str = ""
    customer_code2: str = ""
    new_code: int = 0
    transfer_type: int = 7


@dataclass
class SogoFurikomiFile:
    irai_code: str
    irai_name: str
    torikumi_date: str          # MMDD
    bank_code: str
    branch_code: str
    acct_type: int
    acct_no: str
    bank_name: str = ""
    branch_name: str = ""
    shubetsu: int = 21
    records: list[FurikomiRecord] = field(default_factory=list)

    @property
    def total_amount(self) -> int:
        return sum(r.amount for r in self.records)


def build(f: SogoFurikomiFile, newline: bool = True) -> bytes:
    """SogoFurikomiFile を全銀協フォーマットのバイト列にする。"""
    recs: list[bytes] = [HEADER.pack({
        "data_kubun": 1, "shubetsu": f.shubetsu, "code_kubun": 0,
        "irai_code": f.irai_code, "irai_name": f.irai_name,
        "torikumi_date": f.torikumi_date, "bank_code": f.bank_code,
        "bank_name": f.bank_name, "branch_code": f.branch_code,
        "branch_name": f.branch_name, "acct_type": f.acct_type, "acct_no": f.acct_no,
    })]
    for r in f.records:
        if r.edi_info:
            edi = r.edi_info.ljust(20)[:20]
            c1, c2, flag = edi[:10], edi[10:], "Y"
        else:
            c1, c2, flag = r.customer_code1, r.customer_code2, " "
        recs.append(DATA.pack({
            "data_kubun": 2, "bank_code": r.bank_code, "bank_name": r.bank_name,
            "branch_code": r.branch_code, "branch_name": r.branch_name,
            "clearing_house": "", "acct_type": r.acct_type, "acct_no": r.acct_no,
            "payee_name": r.payee_name, "amount": r.amount, "new_code": r.new_code,
            "customer_code1": c1, "customer_code2": c2,
            "transfer_type": r.transfer_type, "edi_flag": flag,
        }))
    recs.append(TRAILER.pack({"data_kubun": 8, "total_count": len(f.records),
                              "total_amount": f.total_amount}))
    recs.append(END.pack({"data_kubun": 9}))
    sep = b"\r\n" if newline else b""
    return sep.join(recs) + sep


@dataclass
class ParseResult:
    file: SogoFurikomiFile | None
    errors: list[str]

    @property
    def ok(self) -> bool:
        return self.file is not None and not self.errors


def _split_records(raw: bytes) -> list[bytes]:
    data = raw.rstrip(b"\x1a")
    data = data.replace(b"\r\n", b"").replace(b"\n", b"").replace(b"\r", b"")
    if len(data) % RECORD_LEN:
        raise RecordError(f"ファイル長 {len(data)} が {RECORD_LEN} の倍数ではありません")
    return [data[i:i + RECORD_LEN] for i in range(0, len(data), RECORD_LEN)]


def parse(raw: bytes) -> ParseResult:
    """全銀協フォーマットのバイト列を検証しながらパースする。"""
    errors: list[str] = []
    try:
        recs = _split_records(raw)
    except RecordError as e:
        return ParseResult(None, [str(e)])
    if len(recs) < 3:
        return ParseResult(None, ["レコード数が不足しています（ヘッダー/トレーラー/エンドが必要）"])

    kinds = [r[:1] for r in recs]
    if kinds[0] != b"1":
        errors.append("1レコード目がヘッダー(1)ではありません")
    if kinds[-1] != b"9":
        errors.append("最終レコードがエンド(9)ではありません")
    if kinds[-2] != b"8":
        errors.append("最終の直前がトレーラー(8)ではありません")
    for i, k in enumerate(kinds[1:-2], start=2):
        if k != b"2":
            errors.append(f"{i}レコード目: データ区分 {k!r} は不正（2を期待）")
    if errors:
        return ParseResult(None, errors)

    try:
        h = HEADER.unpack(recs[0])
    except RecordError as e:
        return ParseResult(None, [f"ヘッダー: {e}"])
    if h["shubetsu"] not in SHUBETSU:
        errors.append(f"ヘッダー: 種別コード {h['shubetsu']} は未対応")
    if h["code_kubun"] != 0:
        errors.append("ヘッダー: コード区分は 0(JIS) のみ対応")
    if not is_valid_zengin(h["irai_name"]):
        errors.append("ヘッダー: 依頼人名に使用できない文字があります")
    mmdd = f"{h['torikumi_date']:04d}"
    if not (1 <= int(mmdd[:2]) <= 12 and 1 <= int(mmdd[2:]) <= 31):
        errors.append(f"ヘッダー: 取組日 {mmdd} が不正")

    f = SogoFurikomiFile(
        irai_code=f"{h['irai_code']:010d}", irai_name=h["irai_name"], torikumi_date=mmdd,
        bank_code=f"{h['bank_code']:04d}", bank_name=h["bank_name"],
        branch_code=f"{h['branch_code']:03d}", branch_name=h["branch_name"],
        acct_type=h["acct_type"], acct_no=f"{h['acct_no']:07d}", shubetsu=h["shubetsu"],
    )
    for i, raw_rec in enumerate(recs[1:-2], start=2):
        try:
            d = DATA.unpack(raw_rec)
        except RecordError as e:
            errors.append(f"{i}レコード目: {e}")
            continue
        if d["acct_type"] not in ACCT_TYPES:
            errors.append(f"{i}レコード目: 預金種目 {d['acct_type']} が不正")
        if d["amount"] <= 0:
            errors.append(f"{i}レコード目: 振込金額が0以下")
        if not d["payee_name"].strip():
            errors.append(f"{i}レコード目: 受取人名が空")
        elif not is_valid_zengin(d["payee_name"]):
            errors.append(f"{i}レコード目: 受取人名に使用できない文字があります")
        if d["transfer_type"] not in (7, 8):
            errors.append(f"{i}レコード目: 振込指定区分 {d['transfer_type']} が不正")
        edi = ""
        if d["edi_flag"] == "Y":
            edi = (d["customer_code1"].ljust(10) + d["customer_code2"]).rstrip()
        f.records.append(FurikomiRecord(
            bank_code=f"{d['bank_code']:04d}", bank_name=d["bank_name"],
            branch_code=f"{d['branch_code']:03d}", branch_name=d["branch_name"],
            acct_type=d["acct_type"], acct_no=f"{d['acct_no']:07d}",
            payee_name=d["payee_name"], amount=d["amount"], new_code=d["new_code"],
            edi_info=edi,
            customer_code1="" if edi else d["customer_code1"],
            customer_code2="" if edi else d["customer_code2"],
            transfer_type=d["transfer_type"],
        ))

    try:
        t = TRAILER.unpack(recs[-2])
    except RecordError as e:
        return ParseResult(None, errors + [f"トレーラー: {e}"])
    if t["total_count"] != len(recs) - 3:
        errors.append(f"トレーラー: 合計件数 {t['total_count']} != 実件数 {len(recs) - 3}")
    actual = sum(r.amount for r in f.records)
    if t["total_amount"] != actual:
        errors.append(f"トレーラー: 合計金額 {t['total_amount']:,} != 実合計 {actual:,}")
    return ParseResult(f, errors)
