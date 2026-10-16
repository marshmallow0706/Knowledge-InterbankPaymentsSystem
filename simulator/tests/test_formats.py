import unittest
from datetime import date, datetime

from zengin_sim import zengin_format as zf
from zengin_sim.kana import KanaError, normalize_name, to_zengin_kana
from zengin_sim.telegram import TOTAL_LEN, MsgType, Telegram, verify_mac


class KanaTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(to_zengin_kana("ヤマダ タロウ"), "ﾔﾏﾀﾞ ﾀﾛｳ")
        self.assertEqual(to_zengin_kana("やまだ"), "ﾔﾏﾀﾞ")
        self.assertEqual(to_zengin_kana("パン"), "ﾊﾟﾝ")

    def test_small_and_long_vowel(self):
        self.assertEqual(to_zengin_kana("キャッシュ"), "ｷﾔﾂｼﾕ")
        self.assertEqual(to_zengin_kana("コーヒー"), "ｺ-ﾋ-")

    def test_ascii(self):
        self.assertEqual(to_zengin_kana("abc１２３"), "ABC123")

    def test_halfwidth_passthrough(self):
        self.assertEqual(to_zengin_kana("ｶﾞｲｼﾔ"), "ｶﾞｲｼﾔ")

    def test_kanji_rejected(self):
        with self.assertRaises(KanaError):
            to_zengin_kana("山田")

    def test_corporate_abbrev(self):
        self.assertEqual(normalize_name("カブシキガイシャ アオバ"), "ｶ)ｱｵﾊﾞ")
        self.assertEqual(normalize_name("アオバ カブシキガイシャ"), "ｱｵﾊﾞ(ｶ")
        self.assertEqual(normalize_name("ユウゲンガイシャ ハマベ"), "ﾕ)ﾊﾏﾍﾞ")


class ZenginFormatTest(unittest.TestCase):
    def sample(self):
        f = zf.SogoFurikomiFile("1234567890", "ｶ)ｱｵﾊﾞｼﾖｳｼﾞ", "1016", "9001", "001", 2, "2000001",
                                bank_name="ｱｵﾊﾞ", branch_name="ﾎﾝﾃﾝ")
        f.records.append(zf.FurikomiRecord("9002", "100", 1, "1000001", "ﾔﾏﾀﾞ ﾀﾛｳ", 12345))
        f.records.append(zf.FurikomiRecord("9003", "101", 1, "1000002", "ｽｽﾞｷ ﾊﾅｺ", 9800, edi_info="INV-0001"))
        return f

    def test_roundtrip(self):
        raw = zf.build(self.sample())
        lines = raw.split(b"\r\n")[:-1]
        self.assertEqual(len(lines), 5)
        self.assertTrue(all(len(x) == 120 for x in lines))
        res = zf.parse(raw)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.file.total_amount, 22145)
        self.assertEqual(res.file.records[1].edi_info, "INV-0001")
        self.assertEqual(res.file.records[0].payee_name, "ﾔﾏﾀﾞ ﾀﾛｳ")

    def test_no_newline(self):
        raw = zf.build(self.sample(), newline=False)
        self.assertEqual(len(raw), 600)
        self.assertTrue(zf.parse(raw).ok)

    def test_trailer_mismatch(self):
        raw = bytearray(zf.build(self.sample(), newline=False))
        raw[360 + 7:360 + 19] = b"%012d" % 1   # トレーラーの合計金額を改ざん
        res = zf.parse(bytes(raw))
        self.assertFalse(res.ok)
        self.assertTrue(any("合計金額" in e for e in res.errors))

    def test_bad_length(self):
        self.assertFalse(zf.parse(b"1" * 119).ok)

    def test_bad_order(self):
        raw = zf.build(self.sample(), newline=False)
        res = zf.parse(raw[120:])   # ヘッダー欠落
        self.assertFalse(res.ok)


class TelegramTest(unittest.TestCase):
    def tg(self):
        return Telegram(MsgType.TRANSFER, 42, datetime(2026, 10, 16, 9, 30, 15), date(2026, 10, 16),
                        "9001", "001", "9002", "100", 1, "1000001", "ﾔﾏﾀﾞ ﾀﾛｳ", "ｽｽﾞｷ ﾊﾅｺ", 10000)

    def test_roundtrip(self):
        raw = self.tg().to_bytes(b"k")
        self.assertEqual(len(raw), TOTAL_LEN)
        back = Telegram.from_bytes(raw)
        self.assertEqual(back, self.tg())

    def test_mac(self):
        raw = bytearray(self.tg().to_bytes(b"k"))
        self.assertTrue(verify_mac(bytes(raw), b"k"))
        self.assertFalse(verify_mac(bytes(raw), b"other"))
        raw[100] ^= 0x01   # 1ビット改ざん
        self.assertFalse(verify_mac(bytes(raw), b"k"))


if __name__ == "__main__":
    unittest.main()
