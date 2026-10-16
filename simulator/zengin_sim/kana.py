"""全銀で使用可能な文字（半角カナ・英大文字・数字・一部記号）への変換と検証。

全銀協規定フォーマットの名義欄は半角カナを基本とし、小書き文字（ｧ ｯ ｬ 等）は
大文字に、長音は '-' に置き換える慣行がある。法人名は略語（ｶ) 等）を用いる。
"""
from __future__ import annotations

import unicodedata

_FULL = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
_HALF = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜｦﾝ"
_DAKU = "ガギグゲゴザジズゼゾダヂヅデドバビブベボ"
_DAKU_BASE = "カキクケコサシスセソタチツテトハヒフヘホ"
_HANDAKU = "パピプペポ"
_HANDAKU_BASE = "ハヒフヘホ"
_SMALL = {"ァ": "ア", "ィ": "イ", "ゥ": "ウ", "ェ": "エ", "ォ": "オ", "ッ": "ツ",
          "ャ": "ヤ", "ュ": "ユ", "ョ": "ヨ", "ヮ": "ワ", "ヵ": "カ", "ヶ": "ケ"}

_TABLE: dict[str, str] = dict(zip(_FULL, _HALF))
for _f, _b in zip(_DAKU, _DAKU_BASE):
    _TABLE[_f] = _TABLE[_b] + "ﾞ"
for _f, _b in zip(_HANDAKU, _HANDAKU_BASE):
    _TABLE[_f] = _TABLE[_b] + "ﾟ"
_TABLE["ヴ"] = "ｳﾞ"

_SYMBOLS = {"ー": "-", "－": "-", "‐": "-", "−": "-", "―": "-", "・": ".", "　": " ",
            "「": "｢", "」": "｣", "，": ",", "、": ",", "。": ".", "¥": "\\", "￥": "\\"}

ALLOWED = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" + _HALF + "ﾞﾟ" + " ()-./\\,｢｣")

# 法人略語（前置: ｶ) …、後置: … (ｶ ）
_CORP_ABBREV = [
    ("ｶﾌﾞｼｷｶﾞｲｼﾔ", "ｶ"), ("ﾕｳｹﾞﾝｶﾞｲｼﾔ", "ﾕ"), ("ｺﾞｳﾄﾞｳｶﾞｲｼﾔ", "ﾄﾞ"),
    ("ｺﾞｳﾒｲｶﾞｲｼﾔ", "ﾒ"), ("ｺﾞｳｼｶﾞｲｼﾔ", "ｼ"), ("ｲﾘﾖｳﾎｳｼﾞﾝ", "ｲ"),
    ("ｲﾂﾊﾟﾝｼﾔﾀﾞﾝﾎｳｼﾞﾝ", "ｼﾔ"), ("ﾄｸﾃｲﾋｴｲﾘｶﾂﾄﾞｳﾎｳｼﾞﾝ", "ﾄｸﾋ"),
]


class KanaError(ValueError):
    pass


def to_zengin_kana(text: str, strict: bool = True) -> str:
    """任意の文字列を全銀で使える半角文字列に変換する。

    strict=True の場合、変換できない文字（漢字など）があれば KanaError。
    strict=False の場合は該当文字を除去する。
    """
    s = unicodedata.normalize("NFKC", text)
    out: list[str] = []
    for ch in s:
        if "ぁ" <= ch <= "ゖ":
            ch = chr(ord(ch) + 0x60)
        ch = _SMALL.get(ch, ch)
        if ch in _SYMBOLS:
            out.append(_SYMBOLS[ch])
            continue
        if ch in _TABLE:
            out.append(_TABLE[ch])
            continue
        if ch in "゙゚":  # 単独の濁点・半濁点（結合文字）
            out.append("ﾞ" if ch == "゙" else "ﾟ")
            continue
        up = ch.upper()
        if up in ALLOWED:
            out.append(up)
            continue
        if strict:
            raise KanaError(f"全銀で使用できない文字が含まれています: {ch!r}（{text}）")
    return "".join(out)


def abbreviate_corporate(kana: str) -> str:
    """法人格の読みを全銀の略語に置き換える（例: ｶﾌﾞｼｷｶﾞｲｼﾔ ｱｵﾊﾞ → ｶ)ｱｵﾊﾞ）。"""
    s = kana.strip()
    for full, abbr in _CORP_ABBREV:
        if s.startswith(full):
            return f"{abbr})" + s[len(full):].lstrip()
        if s.endswith(full):
            return s[: -len(full)].rstrip() + f"({abbr}"
    return s


def normalize_name(text: str) -> str:
    """受取人名の変換（カナ化 → 法人略語化）。"""
    return abbreviate_corporate(to_zengin_kana(text))


def is_valid_zengin(s: str) -> bool:
    return all(c in ALLOWED for c in s)


def name_key(s: str) -> str:
    """名義照合用キー（空白と区切り記号を除去）。"""
    return "".join(c for c in s if c not in " .,-")
