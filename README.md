# 全銀システム 体系ガイド ― 仕様・仕組み・模擬システム

日本の銀行振込を支える **全国銀行データ通信システム（全銀システム）** を、
**仕様（何を・どんなルールで）**・**仕組み（どう動き・なぜそう設計されているか）**・**模擬システム（動かして確かめる）** の3部構成で体系的にまとめた資料です。

> 全銀システムを運営しているのは **一般社団法人 全国銀行資金決済ネットワーク（全銀ネット）** です。
> 全銀ネットは全国銀行協会（全銀協）の傘下にある資金清算機関で、全銀システムはその全銀ネットが運営するシステム、という関係になります
> （→[仕様編 第1章](spec/01_overview.md#12-運営主体の関係)）。

---

## 構成

```
zengin-system/
├── README.md            ← このファイル（総目次）
├── GLOSSARY.md          用語集
├── spec/                第Ⅰ部 仕様編（10章）
├── mechanism/           第Ⅱ部 仕組み編（10章）
└── simulator/           第Ⅲ部 模擬システム（Python・標準ライブラリのみ）
```

## 第Ⅰ部　仕様編 — [spec/](spec/README.md)

| 章 | 内容 |
|---|---|
| 1 | [全銀システムの概要と運営主体](spec/01_overview.md) |
| 2 | [参加資格と参加形態](spec/02_participation.md) |
| 3 | [取扱業務と取引種別](spec/03_services.md) |
| 4 | [稼働時間とサービス区分（コアタイム／モアタイム）](spec/04_operating_hours.md) |
| 5 | [データ形式と文字コード（全銀協フォーマット・ZEDI）](spec/05_data_formats.md) |
| 6 | [資金決済の仕様（RTGS と 16:15 差額決済）](spec/06_settlement.md) |
| 7 | [リスク管理の仕様（仕向超過限度額・担保・流動性供給）](spec/07_risk_management.md) |
| 8 | [手数料・費用（内国為替制度運営費）](spec/08_fees.md) |
| 9 | [システム構成・可用性・セキュリティ](spec/09_system_architecture.md) |
| 10 | [法的枠組みと関連システム](spec/10_legal_and_related_systems.md) |

## 第Ⅱ部　仕組み編 — [mechanism/](mechanism/README.md)

| 章 | 内容 |
|---|---|
| 1 | [振込1件が着金するまで（全体の流れ）](mechanism/01_end_to_end_flow.md) |
| 2 | [中継コンピュータ（RC）とネットワーク](mechanism/02_relay_computer_and_network.md) |
| 3 | [即時入金と後決済 — 通知と資金の分離](mechanism/03_immediate_credit_deferred_settlement.md) |
| 4 | [多角的ネッティングと CCP](mechanism/04_multilateral_netting_ccp.md) |
| 5 | [大口取引の RTGS 処理](mechanism/05_large_value_rtgs.md) |
| 6 | [モアタイムの仕組み](mechanism/06_moretime.md) |
| 7 | [決済完了の確保と決済不能時の処理](mechanism/07_settlement_guarantee_and_default.md) |
| 8 | [入金不能・返却・組戻](mechanism/08_returns_and_recalls.md) |
| 9 | [障害と事業継続 — 2023年10月障害の分析](mechanism/09_incidents_and_bcp.md) |
| 10 | [歴史と将来像 — 新決済システム構想まで](mechanism/10_history_and_future.md) |

## 第Ⅲ部　模擬システム — [simulator/](simulator/README.md)

全銀センター・参加金融機関（勘定系＋RC）・日銀ネット・リスク管理を Python で模擬した学習用シミュレータです。

```bash
cd simulator
python -m zengin_sim run all      # 9本のシナリオを実行
python -m zengin_sim serve        # Web ダッシュボード http://127.0.0.1:8000/
python -m unittest discover -s tests -t .
```

| 再現している仕組み | シナリオ |
|---|---|
| 為替通知の中継・MAC 検証・二重受付防止 | `telegram`, `rc` |
| 即時入金と 16:15 の多角的ネッティング決済（CCP） | `normal` |
| 1億円以上の RTGS・残高不足時の待ち行列 | `large` |
| モアタイムと翌営業日決済・非参加行宛ての予約 | `moretime` |
| 仕向超過限度額による保留・解除・不受理 | `limit` |
| 決済不能時の流動性供給と担保処分 | `default` |
| 入金不能返却と組戻 | `recall` |
| 全銀協規定フォーマット（総合振込）の生成・検証・一括送信 | `file` |

詳しい使い方・モジュール構成・フォーマット定義は [simulator/README.md](simulator/README.md) を参照してください。

## 読み方のおすすめ

| 目的 | 順序 |
|---|---|
| まず全体像をつかみたい | [仕様1章](spec/01_overview.md) → [仕組み1章](mechanism/01_end_to_end_flow.md) → `run normal` |
| 決済・リスクの専門的な理解 | [仕様6・7章](spec/06_settlement.md) → [仕組み3〜7章](mechanism/03_immediate_credit_deferred_settlement.md) → `run default` |
| システム開発・データ連携 | [仕様5章](spec/05_data_formats.md) → [仕組み2章](mechanism/02_relay_computer_and_network.md) → [simulator](simulator/README.md) |
| 障害・BCP | [仕様9章](spec/09_system_architecture.md) → [仕組み9章](mechanism/09_incidents_and_bcp.md) → `run rc` |
| 最新動向 | [仕組み10章](mechanism/10_history_and_future.md) |

用語は [GLOSSARY.md](GLOSSARY.md) にまとめています。

---

## 注意事項

- 本資料は公開情報（全銀ネット・全銀協・日本銀行・金融庁の資料、報道）をもとに 2026年10月時点で作成した学習用資料です。全銀ネットの公式資料ではありません
- 全銀センターと RC の間の電文仕様、仕向超過限度額の算定方法などの内部仕様は公開されていないため、該当部分は概念的な説明と **独自の模擬** です
- 模擬システムに登場する金融機関名・金融機関コード・口座はすべて架空です
- 制度・料金・稼働時間などは変更されることがあります。業務で利用する場合は必ず全銀ネット・各金融機関の最新の公表資料を確認してください
