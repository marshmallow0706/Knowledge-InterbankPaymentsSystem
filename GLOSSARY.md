# 用語集

[← トップへ戻る](README.md)

| 用語 | 読み・略称 | 説明 | 参照 |
|---|---|---|---|
| 全銀システム | 全国銀行データ通信システム | 内国為替取引の為替通知の送受信と決済額計算を行うシステム | [仕様1章](spec/01_overview.md) |
| 全銀ネット | 全国銀行資金決済ネットワーク | 全銀システムを運営する一般社団法人。資金清算機関 | [仕様1章](spec/01_overview.md) |
| 全銀協 | 全国銀行協会 | 銀行界の業界団体。全銀ネットは傘下 | [仕様1章](spec/01_overview.md) |
| 内国為替 | ないこくかわせ | 国内の円建ての資金移動（振込・送金・代金取立など） | [仕様3章](spec/03_services.md) |
| 為替通知 | | 仕向銀行から被仕向銀行への「入金してください」という通知 | [仕組み1章](mechanism/01_end_to_end_flow.md) |
| 仕向銀行 | しむけ | 振込を依頼された（送る側の）金融機関 | |
| 被仕向銀行 | ひしむけ | 振込を受ける側の金融機関 | |
| 加盟銀行 | | 全銀システムに参加する金融機関（信金・信組・農協等を含む） | [仕様2章](spec/02_participation.md) |
| 清算参加者 | | 全銀ネットと直接、日銀当座預金で資金決済を行う参加者 | [仕様2章](spec/02_participation.md) |
| 代行決済委託金融機関 | | 資金決済を清算参加者に委託する参加者 | [仕様2章](spec/02_participation.md) |
| 資金清算機関 | | 資金決済法に基づき免許を受け、資金清算業を行う機関 | [仕様10章](spec/10_legal_and_related_systems.md) |
| 資金移動業者 | | 銀行以外で為替取引を行う事業者（第一種〜第三種） | [仕様2章](spec/02_participation.md) |
| コアタイム | | 平日 8:30〜15:30。コアタイムシステムが処理 | [仕様4章](spec/04_operating_hours.md) |
| モアタイム | | コアタイム以外の時間帯。2018年10月〜。1億円未満を即時処理 | [仕組み6章](mechanism/06_moretime.md) |
| 取扱日 | | 受取人口座に入金される日 | [仕様4章](spec/04_operating_hours.md) |
| 決済日 | | 銀行間の資金決済が行われる日 | [仕様4章](spec/04_operating_hours.md) |
| 大口内為取引 | | 1件1億円以上の取引。日銀ネットで RTGS | [仕組み5章](mechanism/05_large_value_rtgs.md) |
| 小口内為取引 | | 1件1億円未満の取引。16:15 に差額決済 | [仕組み4章](mechanism/04_multilateral_netting_ccp.md) |
| RTGS | Real-Time Gross Settlement | 即時グロス決済。1件ずつ即時に最終決済 | [仕組み5章](mechanism/05_large_value_rtgs.md) |
| 時点ネット決済 | DNS | 一定時点で差額をまとめて決済する方式 | [仕組み4章](mechanism/04_multilateral_netting_ccp.md) |
| 多角的ネッティング | | 全参加者の受払を相殺し参加者ごとの差額にまとめること | [仕組み4章](mechanism/04_multilateral_netting_ccp.md) |
| CCP | Central Counterparty | 決済の相手方として全取引の間に入る主体。全銀システムでは全銀ネット | [仕組み4章](mechanism/04_multilateral_netting_ccp.md) |
| 受払差額 | 決済尻 | 清算参加者ごとの受取額 − 支払額 | [仕様6章](spec/06_settlement.md) |
| 仕向超過額 | | 支払額が受取額を上回る額 | [仕様7章](spec/07_risk_management.md) |
| 仕向超過限度額 | | 仕向超過額の上限。超える取引は処理されない | [仕組み7章](mechanism/07_settlement_guarantee_and_default.md) |
| 流動性供給銀行 | | 決済不能時に不足資金を即時に供給する銀行 | [仕組み7章](mechanism/07_settlement_guarantee_and_default.md) |
| 決済完了性 | ファイナリティ | 決済が取り消されず最終的に確定すること | [仕組み7章](mechanism/07_settlement_guarantee_and_default.md) |
| 日銀ネット | 日本銀行金融ネットワークシステム | 日銀当座預金・国債の決済システム | [仕様10章](spec/10_legal_and_related_systems.md) |
| 日銀当座預金 | 日銀当預 | 金融機関が日本銀行に保有する当座預金。銀行間決済の最終手段 | [仕様6章](spec/06_settlement.md) |
| RC | Relay Computer、中継コンピュータ | 各金融機関側に置かれ、勘定系と全銀センターをつなぐ | [仕組み2章](mechanism/02_relay_computer_and_network.md) |
| 全銀センター | | 全銀システムの中核。東京・大阪の2拠点 | [仕様9章](spec/09_system_architecture.md) |
| 勘定系 | | 金融機関の預金元帳を管理する基幹システム | |
| 電文 | | システム間でやり取りされる定型のデータ | [仕組み2章](mechanism/02_relay_computer_and_network.md) |
| MAC | Message Authentication Code | 電文の改ざん・なりすましを検知する認証コード | [仕組み2章](mechanism/02_relay_computer_and_network.md) |
| 全銀協規定フォーマット | | 企業⇔銀行の振込データの標準形式（120バイト固定長） | [仕様5章](spec/05_data_formats.md) |
| 総合振込 | | 企業が複数の取引先へまとめて振り込む方式（種別コード21） | [仕様5章](spec/05_data_formats.md) |
| EDI情報 | | 振込に付加する商流情報（支払通知番号等） | [仕様5章](spec/05_data_formats.md) |
| ZEDI | 全銀EDIシステム | 大容量の EDI 情報を XML で添付できるシステム（2018年〜） | [仕様5章](spec/05_data_formats.md) |
| 半角カナ | | 全銀の名義欄で使う文字。小書き不可、長音は `-` | [仕様5章](spec/05_data_formats.md) |
| 返却 | | 入金不能時に被仕向銀行から資金を返すこと | [仕組み8章](mechanism/08_returns_and_recalls.md) |
| 組戻 | くみもどし | 依頼人の取消依頼に基づき、受取人の同意を得て資金を返すこと | [仕組み8章](mechanism/08_returns_and_recalls.md) |
| 別段預金 | | 入金不能資金などを一時的に預かる預金科目 | [仕組み8章](mechanism/08_returns_and_recalls.md) |
| 内国為替制度運営費 | | 仕向銀行が被仕向銀行に払う1件62円（2021年10月〜） | [仕様8章](spec/08_fees.md) |
| 銀行間手数料 | | 2021年9月まで存在した銀行間の手数料（117円/162円） | [仕様8章](spec/08_fees.md) |
| レベルアップ | | 概ね8年ごとのシステム全面更改 | [仕様9章](spec/09_system_architecture.md) |
| ことら | | 10万円以下の個人間送金サービス（2022年〜） | [仕様10章](spec/10_legal_and_related_systems.md) |
| 電子交換所 | | 手形・小切手の電子交換（2022年11月〜） | [仕様10章](spec/10_legal_and_related_systems.md) |
| 事前口座確認 | | 送金前に受取口座・名義を確認する仕組み。新システムで検討 | [仕組み10章](mechanism/10_history_and_future.md) |
| PFMI | 金融市場インフラのための原則 | 決済システム等に関する国際基準（2012年） | [仕様7章](spec/07_risk_management.md) |
