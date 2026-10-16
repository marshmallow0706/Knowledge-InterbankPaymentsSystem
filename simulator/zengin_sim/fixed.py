"""固定長レコードのエンコード／デコード。

N: 数字項目（右詰め・前ゼロ）、X: 文字項目（左詰め・後スペース）。
文字コードは Shift_JIS（cp932）。半角カナは1バイトなので、バイト位置で切り出せる。
"""
from __future__ import annotations

from dataclasses import dataclass

ENCODING = "cp932"


class RecordError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    name: str
    length: int
    kind: str  # "N" or "X"


class Layout:
    def __init__(self, name: str, fields: list[tuple[str, int, str]]):
        self.name = name
        self.fields = [Field(*f) for f in fields]
        self.length = sum(f.length for f in self.fields)

    def offsets(self) -> list[tuple[Field, int]]:
        pos, out = 0, []
        for f in self.fields:
            out.append((f, pos))
            pos += f.length
        return out

    def pack(self, values: dict, truncate: bool = True) -> bytes:
        buf = bytearray()
        for f in self.fields:
            v = values.get(f.name)
            buf += encode_field(f, v, truncate)
        if len(buf) != self.length:
            raise RecordError(f"{self.name}: レコード長 {len(buf)} != {self.length}")
        return bytes(buf)

    def unpack(self, raw: bytes) -> dict:
        if len(raw) != self.length:
            raise RecordError(f"{self.name}: レコード長 {len(raw)} != {self.length}")
        out = {}
        for f, pos in self.offsets():
            out[f.name] = decode_field(f, raw[pos:pos + f.length])
        return out

    def describe(self) -> list[tuple[str, int, int, str]]:
        """(項目名, 開始位置(1起点), 桁数, 属性) の一覧。ドキュメント生成用。"""
        return [(f.name, pos + 1, f.length, f.kind) for f, pos in self.offsets()]


def encode_field(f: Field, v, truncate: bool = True) -> bytes:
    if f.kind == "N":
        s = "" if v is None or v == "" else str(v)
        if s and not s.isdigit():
            raise RecordError(f"{f.name}: 数字項目に数字以外 {s!r}")
        if len(s) > f.length:
            raise RecordError(f"{f.name}: 桁あふれ {s!r} (最大{f.length}桁)")
        return s.rjust(f.length, "0").encode("ascii")
    s = "" if v is None else str(v)
    try:
        b = s.encode(ENCODING)
    except UnicodeEncodeError as e:
        raise RecordError(f"{f.name}: エンコード不可 {s!r}") from e
    if len(b) > f.length:
        if not truncate:
            raise RecordError(f"{f.name}: 桁あふれ {s!r} (最大{f.length}バイト)")
        b = b[: f.length]
    return b.ljust(f.length, b" ")


def decode_field(f: Field, b: bytes):
    try:
        s = b.decode(ENCODING)
    except UnicodeDecodeError as e:
        raise RecordError(f"{f.name}: デコード不可") from e
    if f.kind == "N":
        t = s.strip()
        if t == "":
            return 0
        if not t.isdigit():
            raise RecordError(f"{f.name}: 数字項目に数字以外 {s!r}")
        return int(t)
    return s.rstrip(" ")
