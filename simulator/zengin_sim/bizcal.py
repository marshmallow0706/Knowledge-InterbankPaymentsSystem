"""営業日カレンダーと模擬時計。

祝日は 2026〜2027 年の日本の祝日（振替休日・国民の休日を含む）を収録。
銀行休業日として 12/31〜1/3 も休業扱いとする。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import CORE_CLOSE, CORE_OPEN, SETTLEMENT_TIME

JP_HOLIDAYS = [
    # 2026
    "2026-01-01", "2026-01-12", "2026-02-11", "2026-02-23", "2026-03-20",
    "2026-04-29", "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06",
    "2026-07-20", "2026-08-11", "2026-09-21", "2026-09-22", "2026-09-23",
    "2026-10-12", "2026-11-03", "2026-11-23",
    # 2027
    "2027-01-01", "2027-01-11", "2027-02-11", "2027-02-23", "2027-03-21",
    "2027-03-22", "2027-04-29", "2027-05-03", "2027-05-04", "2027-05-05",
    "2027-07-19", "2027-08-11", "2027-09-20", "2027-09-23", "2027-10-11",
    "2027-11-03", "2027-11-23",
]

BANK_HOLIDAYS_MD = {(12, 31), (1, 1), (1, 2), (1, 3)}


class BusinessCalendar:
    """銀行営業日の判定とサービス時間帯の判定を行う。"""

    def __init__(self, extra_holidays: tuple[date, ...] = ()):
        self.holidays = {date.fromisoformat(x) for x in JP_HOLIDAYS} | set(extra_holidays)

    def is_business_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        if d in self.holidays:
            return False
        if (d.month, d.day) in BANK_HOLIDAYS_MD:
            return False
        return True

    def next_business_day(self, d: date, include_today: bool = False) -> date:
        x = d if include_today else d + timedelta(days=1)
        while not self.is_business_day(x):
            x += timedelta(days=1)
        return x

    def is_core_time(self, dt: datetime) -> bool:
        return self.is_business_day(dt.date()) and CORE_OPEN <= dt.time() < CORE_CLOSE

    def service_window(self, dt: datetime) -> str:
        """'core'（コアタイム）または 'more'（モアタイム）を返す。"""
        return "core" if self.is_core_time(dt) else "more"

    def settlement_date_for(self, dt: datetime) -> date:
        """小口取引の資金決済日。

        前営業日 15:30 〜 当営業日 15:30 に受け付けた取引は当営業日の
        16:15 に決済される。休日・夜間（モアタイム）分は翌営業日決済。
        """
        d = dt.date()
        if self.is_business_day(d) and dt.time() < CORE_CLOSE:
            return d
        return self.next_business_day(d)

    def boundaries_between(self, start: datetime, end: datetime) -> list[tuple[datetime, str]]:
        """start < t <= end の範囲にある時間帯境界（コア開始/終了、決済時刻）を列挙。"""
        out: list[tuple[datetime, str]] = []
        d = start.date()
        while d <= end.date():
            if self.is_business_day(d):
                for t, label in ((CORE_OPEN, "core_open"), (CORE_CLOSE, "core_close"),
                                 (SETTLEMENT_TIME, "settlement")):
                    x = datetime.combine(d, t)
                    if start < x <= end:
                        out.append((x, label))
            d += timedelta(days=1)
        return sorted(out)


class SimClock:
    """模擬時計。実時間とは独立して進む。"""

    def __init__(self, start: datetime):
        self.now = start

    def advance(self, minutes: int = 0, seconds: int = 0) -> datetime:
        self.now += timedelta(minutes=minutes, seconds=seconds)
        return self.now

    def set(self, dt: datetime) -> None:
        if dt < self.now:
            raise ValueError("模擬時計を過去に戻すことはできません")
        self.now = dt
