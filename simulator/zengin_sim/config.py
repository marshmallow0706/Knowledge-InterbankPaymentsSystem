"""模擬システム全体の定数・パラメータ。

値は公開情報に基づく「概念上の」設定であり、実際の全銀システムの
内部パラメータ（非公開）を再現したものではない。
"""
from datetime import time

# 1件1億円以上は「大口内為取引」として日銀ネットで即時グロス決済（RTGS）
LARGE_VALUE_THRESHOLD = 100_000_000

# コアタイム（平日 8:30〜15:30）。それ以外はモアタイム。
CORE_OPEN = time(8, 30)
CORE_CLOSE = time(15, 30)

# 小口取引（1億円未満）の資金決済時刻（日本銀行当座預金上）
SETTLEMENT_TIME = time(16, 15)

# 内国為替制度運営費（1件あたり・仕向→被仕向）
INTERBANK_FEE_YEN = 62

# 日本銀行における全銀ネット名義の当座預金（CCP の決済口）
ZENGIN_NET_ACCOUNT = "ZNET"

# 仕向超過限度額に対して求める担保等のカバー率（模擬パラメータ）
COLLATERAL_COVERAGE_RATIO = 1.0

# 模擬電文に付与する MAC の長さ（バイト）。16進表記で2倍の桁数になる。
MAC_BYTES = 8
