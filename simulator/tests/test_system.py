import unittest
from datetime import date, datetime

from zengin_sim.config import ZENGIN_NET_ACCOUNT
from zengin_sim.models import TxStatus
from zengin_sim.settlement import NettingEngine
from zengin_sim.telegram import MsgType, Telegram
from zengin_sim.world import OKU, Simulation


def corp(sim, code, i=0):
    return [a for a in sim.accounts_of(code) if a.acct_type == 2][i]


def person(sim, code, i=0):
    return [a for a in sim.accounts_of(code) if a.acct_type == 1][i]


def send(sim, frm, src, to, dst, amount, **kw):
    return sim.node(frm).transfer(src.key, to, dst.branch, dst.acct_type, dst.number, dst.holder, amount, **kw)


def status(sim, frm, st):
    return sim.center.records[sim.center.tx_id(frm, st.seq)].status


class CalendarTest(unittest.TestCase):
    def setUp(self):
        self.cal = Simulation(populate=False).cal

    def test_business_days(self):
        self.assertTrue(self.cal.is_business_day(date(2026, 10, 16)))    # 金
        self.assertFalse(self.cal.is_business_day(date(2026, 10, 17)))   # 土
        self.assertFalse(self.cal.is_business_day(date(2026, 11, 3)))    # 文化の日
        self.assertFalse(self.cal.is_business_day(date(2026, 12, 31)))   # 銀行休業日
        self.assertEqual(self.cal.next_business_day(date(2026, 10, 16)), date(2026, 10, 19))

    def test_settlement_date(self):
        f = self.cal.settlement_date_for
        self.assertEqual(f(datetime(2026, 10, 16, 7, 0)), date(2026, 10, 16))
        self.assertEqual(f(datetime(2026, 10, 16, 15, 29)), date(2026, 10, 16))
        self.assertEqual(f(datetime(2026, 10, 16, 15, 30)), date(2026, 10, 19))
        self.assertEqual(f(datetime(2026, 10, 18, 12, 0)), date(2026, 10, 19))


class NettingTest(unittest.TestCase):
    def test_net_sum_zero(self):
        n = NettingEngine()
        d = date(2026, 10, 16)
        n.record(d, "A", "B", 100)
        n.record(d, "B", "C", 70)
        n.record(d, "C", "A", 50)
        pos = n.net_positions(d)
        self.assertEqual(pos, {"A": -50, "B": 30, "C": 20})
        self.assertEqual(sum(pos.values()), 0)
        r = n.report(d)
        self.assertEqual(r["total_gross"], 220)
        self.assertEqual(r["total_net"], 50)

    def test_closed_date(self):
        n = NettingEngine()
        d = date(2026, 10, 16)
        n.close(d)
        with self.assertRaises(Exception):
            n.record(d, "A", "B", 1)


class FlowTest(unittest.TestCase):
    def test_small_transfer_and_settlement(self):
        sim = Simulation(datetime(2026, 10, 16, 9, 0))
        a, b = person(sim, "9001"), person(sim, "9002")
        a0, b0 = a.balance, b.balance
        st = send(sim, "9001", a, "9002", b, 12345)
        self.assertEqual(status(sim, "9001", st), TxStatus.CREDITED)
        self.assertEqual(a.balance, a0 - 12345)
        self.assertEqual(b.balance, b0 + 12345)       # 即時入金（資金決済前）
        boj1 = sim.boj.balance("9001")
        sim.run_until(sim.at("16:20"))
        self.assertEqual(sim.boj.balance("9001"), boj1 - 12345)
        self.assertEqual(sim.boj.balance(ZENGIN_NET_ACCOUNT), 0)

    def test_conservation_random_day(self):
        sim = Simulation(datetime(2026, 10, 16, 9, 0))
        deposits0 = sum(n.total_deposits() for n in sim.nodes.values())
        boj0 = sum(sim.boj.balances.values())
        sim.random_transfers(500)
        sim.run_until(sim.at("16:20"))
        self.assertEqual(sum(n.total_deposits() for n in sim.nodes.values()), deposits0)
        self.assertEqual(sum(sim.boj.balances.values()), boj0)

    def test_large_value_rtgs(self):
        sim = Simulation(datetime(2026, 10, 16, 9, 0))
        b0 = sim.boj.balance("9003")
        st = send(sim, "9001", corp(sim, "9001"), "9003", corp(sim, "9003"), 2 * OKU)
        rec = sim.center.records[sim.center.tx_id("9001", st.seq)]
        self.assertEqual(rec.channel, "rtgs")
        self.assertEqual(sim.boj.balance("9003"), b0 + 2 * OKU)   # 即時に日銀当預が動く
        self.assertEqual(sim.netting.net_positions(date(2026, 10, 16)), {})

    def test_large_value_queue_and_expire(self):
        sim = Simulation(datetime(2026, 10, 16, 9, 0))
        src = corp(sim, "9003")
        src.balance = 100 * OKU
        bal0 = src.balance
        st = send(sim, "9003", src, "9001", corp(sim, "9001"), 60 * OKU)
        self.assertEqual(status(sim, "9003", st), TxStatus.PENDING_RTGS)
        sim.run_until(sim.at("16:20"))
        self.assertEqual(status(sim, "9003", st), TxStatus.REJECTED)
        self.assertEqual(src.balance, bal0)            # 依頼人へ返金

    def test_moretime_next_day(self):
        sim = Simulation(datetime(2026, 10, 16, 21, 0))
        st = send(sim, "9001", person(sim, "9001"), "9002", person(sim, "9002"), 5000)
        rec = sim.center.records[sim.center.tx_id("9001", st.seq)]
        self.assertEqual(rec.status, TxStatus.CREDITED)
        self.assertEqual(rec.channel, "more")
        self.assertEqual(rec.settlement_date, date(2026, 10, 19))

    def test_moretime_non_participant_reserved(self):
        sim = Simulation(datetime(2026, 10, 17, 10, 0))
        dst = person(sim, "9102")
        b0 = dst.balance
        st = send(sim, "9001", person(sim, "9001"), "9102", dst, 5000)
        self.assertEqual(status(sim, "9001", st), TxStatus.RESERVED)
        self.assertEqual(dst.balance, b0)
        sim.run_until(datetime(2026, 10, 19, 8, 30))
        self.assertEqual(status(sim, "9001", st), TxStatus.CREDITED)
        self.assertEqual(dst.balance, b0 + 5000)

    def test_limit_hold_release(self):
        sim = Simulation(datetime(2026, 10, 16, 9, 0))
        sim.risk.caps["9003"] = 30_000_000
        src = corp(sim, "9003")
        src.balance = 10 * OKU
        s1 = send(sim, "9003", src, "9001", corp(sim, "9001"), 20_000_000)
        s2 = send(sim, "9003", src, "9001", corp(sim, "9001"), 20_000_000)
        self.assertEqual(status(sim, "9003", s1), TxStatus.CREDITED)
        self.assertEqual(status(sim, "9003", s2), TxStatus.HELD)
        send(sim, "9001", corp(sim, "9001", 1), "9003", corp(sim, "9003", 1), 15_000_000)
        self.assertEqual(status(sim, "9003", s2), TxStatus.CREDITED)

    def test_agency_rolls_up(self):
        sim = Simulation(datetime(2026, 10, 16, 9, 0))
        send(sim, "9101", person(sim, "9101"), "9002", person(sim, "9002"), 10000)
        pos = sim.netting.net_positions(date(2026, 10, 16))
        self.assertEqual(pos, {"9100": -10000, "9002": 10000})

    def test_default_completes_settlement(self):
        sim = Simulation(datetime(2026, 10, 16, 9, 0))
        src = corp(sim, "9003")
        src.balance = 100 * OKU
        for _ in range(20):
            send(sim, "9003", src, "9001", corp(sim, "9001"), OKU - 1)
        sim.boj.balances["9003"] = 1 * OKU
        b9001 = sim.boj.balance("9001")
        sim.run_until(sim.at("16:20"))
        res = sim.settlement.results[date(2026, 10, 16)]
        self.assertEqual(len(res.defaults), 1)
        self.assertEqual(sim.boj.balance(ZENGIN_NET_ACCOUNT), 0)
        # 9001 は受取 20×(1億−1) を受け、流動性供給分は担保処分代り金で返済済み
        self.assertEqual(sim.boj.balance("9001"), b9001 + 20 * (OKU - 1))

    def test_rc_failure_store_and_forward(self):
        sim = Simulation(datetime(2026, 10, 16, 9, 0))
        sim.node("9002").set_rc(False)
        st_out = send(sim, "9002", person(sim, "9002"), "9001", person(sim, "9001"), 1000)
        st_in = send(sim, "9001", person(sim, "9001"), "9002", person(sim, "9002"), 2000)
        self.assertEqual(st_out.status, TxStatus.QUEUED_AT_BANK)
        self.assertEqual(status(sim, "9001", st_in), TxStatus.UNDELIVERED)
        sim.node("9002").set_rc(True)
        sim.advance(1)
        self.assertEqual(status(sim, "9002", st_out), TxStatus.CREDITED)
        self.assertEqual(status(sim, "9001", st_in), TxStatus.CREDITED)

    def test_return_and_recall(self):
        sim = Simulation(datetime(2026, 10, 16, 10, 0))
        p = person(sim, "9001")
        p0 = p.balance
        st = sim.node("9001").transfer(p.key, "9002", "100", 1, "9999999", "ﾀﾞﾚﾓ", 5000)
        self.assertEqual(st.status, TxStatus.RETURNED)
        self.assertEqual(p.balance, p0)
        dst = person(sim, "9002")
        st = send(sim, "9001", p, "9002", dst, 7000)
        sim.node("9001").request_recall(st.seq)
        self.assertEqual(st.status, TxStatus.RECALLED)
        self.assertEqual(p.balance, p0)

    def test_security_checks(self):
        sim = Simulation(datetime(2026, 10, 16, 9, 0))
        tg = Telegram(MsgType.TRANSFER, 1, sim.clock.now, sim.clock.now.date(), "9001", "100", "9002",
                      "100", 1, "1000001", "ﾔﾏﾀﾞ ﾀﾛｳ", "X", 100)
        bad_mac = tg.to_bytes(b"wrong-key")
        self.assertEqual(sim.center.submit(bad_mac, "9001").code, "E03")
        good = tg.to_bytes(sim.center.keys["9001"])
        self.assertTrue(sim.center.submit(good, "9001").ok)
        self.assertEqual(sim.center.submit(good, "9001").code, "E05")      # 二重受付
        spoof = tg.copy(seq=2).to_bytes(sim.center.keys["9003"])
        self.assertEqual(sim.center.submit(spoof, "9003").code, "E04")     # なりすまし
        self.assertEqual(sim.center.submit(b"short", "9001").code, "E01")


if __name__ == "__main__":
    unittest.main()
