"""監査ログ（イベントログ）。全コンポーネントが共有する。"""
from __future__ import annotations

import json
from pathlib import Path


class EventLog:
    CATEGORIES = ("CLOCK", "BANK", "RC", "CENTER", "RTGS", "NETTING", "SETTLE", "RISK", "BOJ", "ERROR")

    def __init__(self, clock, echo: bool = False):
        self.clock = clock
        self.echo = echo
        self.events: list[dict] = []

    def add(self, cat: str, msg: str, **data) -> dict:
        e = {"ts": self.clock.now.isoformat(sep=" ", timespec="seconds"), "cat": cat, "msg": msg, "data": data}
        self.events.append(e)
        if self.echo:
            print(f"  [{e['ts'][11:]}] {cat:<8} {msg}")
        return e

    def tail(self, n: int = 50, cat: str | None = None) -> list[dict]:
        ev = self.events if cat is None else [e for e in self.events if e["cat"] == cat]
        return ev[-n:]

    def count(self, cat: str) -> int:
        return sum(1 for e in self.events if e["cat"] == cat)

    def dump_jsonl(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for e in self.events:
                f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
