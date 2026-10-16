# 第Ⅱ部　仕組み編

[← トップへ戻る](../README.md)　｜　[← 第Ⅰ部 仕様編](../spec/README.md)　｜　[第Ⅲ部 模擬システム →](../simulator/README.md)

仕様編で整理した「決まりごと」が、内部で **どう動き、なぜそう設計されているのか** を解説します。
各章の末尾に、その仕組みを体験できる **模擬システムのシナリオ** を示しています。

| 章 | タイトル | 体験できるシナリオ |
|---|---|---|
| 1 | [振込1件が着金するまで（全体の流れ）](01_end_to_end_flow.md) | `normal` |
| 2 | [中継コンピュータ（RC）とネットワーク](02_relay_computer_and_network.md) | `telegram`, `rc` |
| 3 | [即時入金と後決済 — 通知と資金の分離](03_immediate_credit_deferred_settlement.md) | `normal` |
| 4 | [多角的ネッティングと CCP](04_multilateral_netting_ccp.md) | `normal` |
| 5 | [大口取引の RTGS 処理](05_large_value_rtgs.md) | `large` |
| 6 | [モアタイムの仕組み](06_moretime.md) | `moretime` |
| 7 | [決済完了の確保と決済不能時の処理](07_settlement_guarantee_and_default.md) | `limit`, `default` |
| 8 | [入金不能・返却・組戻](08_returns_and_recalls.md) | `recall` |
| 9 | [障害と事業継続 — 2023年10月障害の分析](09_incidents_and_bcp.md) | `rc` |
| 10 | [歴史と将来像 — 1973年から新決済システム構想まで](10_history_and_future.md) | — |
