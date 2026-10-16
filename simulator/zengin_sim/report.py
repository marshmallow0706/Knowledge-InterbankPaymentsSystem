"""コンソール出力用の整形ユーティリティ（全角文字の表示幅を考慮）。"""
from __future__ import annotations

import unicodedata


def width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s: str, w: int, right: bool = False) -> str:
    gap = max(0, w - width(s))
    return (" " * gap + s) if right else (s + " " * gap)


def yen(n: int) -> str:
    return f"{n:,}円"


def table(headers: list[str], rows: list[list], right: set[int] | None = None) -> str:
    right = right or set()
    cells = [[str(c) for c in r] for r in rows]
    ws = [max([width(h)] + [width(r[i]) for r in cells]) for i, h in enumerate(headers)]
    line = "+" + "+".join("-" * (w + 2) for w in ws) + "+"
    out = [line, "| " + " | ".join(pad(h, ws[i]) for i, h in enumerate(headers)) + " |", line]
    for r in cells:
        out.append("| " + " | ".join(pad(c, ws[i], i in right) for i, c in enumerate(r)) + " |")
    out.append(line)
    return "\n".join(out)


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(f" {title}")
    print("=" * 78)


def sub(title: str) -> None:
    print(f"\n--- {title} " + "-" * max(0, 70 - width(title)))


def netting_table(report: dict, names: dict[str, str]) -> str:
    rows = [[r["code"], names.get(r["code"], ""), yen(r["sent"]), yen(r["recv"]),
             ("+" if r["net"] > 0 else "") + yen(r["net"])] for r in report["rows"]]
    t = table(["コード", "清算参加者", "支払(グロス)", "受取(グロス)", "受払差額"], rows, {2, 3, 4})
    tail = (f"\n件数 {report['count']:,} / グロス総額 {yen(report['total_gross'])} / "
            f"ネット決済額 {yen(report['total_net'])} / 圧縮率 {report['reduction'] * 100:.1f}%")
    return t + tail
