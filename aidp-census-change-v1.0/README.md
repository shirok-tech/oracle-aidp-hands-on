# AIDP第2回 実行セット v1.0

2020年・2025年の国勢調査から、東京都の市区町村の変化を比較・分類し、生成AIで説明するための実行セットです。記事「AIDP第2回」と、元の実行セットに含まれる4本のNotebookをもとに作成しています。

**まずこのREADMEを読み、Notebookの入力欄を自分の環境へ変更してください。** 原本Excel、認証情報、秘密鍵、個人用設定ファイル、Notebookの実行出力は同梱していません。

## 1. 第1回で準備しておく環境

[第1回の記事](https://qiita.com/shirok/items/399e0042896dcc4c0b4c)のWorkspace、Compute、Catalog / Schema、原本用・成果物用External Volumeを利用します。

| 必要なもの | 記事の例・確認事項 |
|---|---|
| AIDP | 東京 `ap-tokyo-1`。Notebook編集・実行権限があること |
| Workspace | nb01〜03は `AIDP_OpenData_PoC`、nb04は `AIDP_OpenData_Workspace` が筆者の例 |
| Compute | `Census_PoC_Cluster` が筆者の例。Python 3.11系、Spark、`aidputils` が使えること |
| Catalog / Schema | `blog_catalog.opendata` が筆者の例 |
| 原本Volume | `/Volumes/blog_catalog/opendata/census_raw` が筆者の例。読み取り可能なこと |
| 成果物Volume | `/Volumes/blog_catalog/opendata/census_work` が筆者の例。読み書き可能なこと |
| Object Storage | 記事では原本Volumeが `tokyo-census/raw/`、成果物Volumeが `tokyo-census/work/` に対応 |
| nb04の通信・権限 | 大阪の推論エンドポイントへ接続可能なこと。API署名鍵のIAMユーザーが、対象コンパートメントで生成AIのチャットAPIを利用できること |

Notebookへ指定するのは `/Volumes/...` のパスです。バケットURLやPC上のZIP展開先は指定しません。nb04を別Workspaceで使う場合も、同じ成果物Volumeを読める必要があります。記事のネットワーク構成は筆者の実行例なので、自分の組織のネットワーク要件と利用権限を確認してください。

## 2. ZIP展開後に取り込むファイル

`aidp-census-change-v1.0/` フォルダを開きます。

| ファイル | 用途・AIDPへの配置 |
|---|---|
| `nb01_ingest_year.ipynb` | 2020年・2025年の原本取込み。Workspaceへインポート |
| `nb02_compare_years.ipynb` | 境域検査と年度比較。Workspaceへインポート |
| `nb03_cluster_changes.ipynb` | K-meansの分類・評価・可視化。Workspaceへインポート |
| `nb04_explain_changes.ipynb` | 生成AIの説明・保存・検査。生成AI用Workspaceへインポート |
| `nb00_check_and_capture.ipynb` | 環境確認・保存結果の表示。必要なWorkspaceへインポート |
| `requirements.txt` | ComputeのLibraryへ登録 |
| `config/source_registry.json` | 年別の原本URL・ハッシュ・読込定義。参照用 |
| `ingest_core.py`、`comparison_core.py`、`ml_change_core.py` | Notebookへ埋め込んだ共通処理の参照用ソース |
| `FILELIST.txt`、`SHA256SUMS.txt` | 配布ファイル一覧とハッシュ |

4本のNotebookには必要な共通処理が埋め込まれており、別Pythonファイルをimportしません。参照用の `.py` とJSONをAIDPへ追加配置する必要はありません。旧版の `.py` Notebookやローカル実行スクリプトは、この配布版には含めていません。

第1回のNotebookを上書きせず、`OpenData_AI_2020_2025` などのフォルダへインポートします。各Notebookの **Actions → Attach an existing cluster** から、使用するComputeを接続します。

**先頭Widgetセルと、nb04のCell A〜Cは組込み済みです。記事から同じセルを追加しないでください。** Cell番号はMarkdownセルも含む位置です。左側の実行回数とは異なります。

## 3. ライブラリの導入とComputeの接続

Computeの **Library → Install Library → Upload file to workspace** で `requirements.txt` を指定します。既存のLibrary設定と競合していないかを確認し、導入完了後にComputeをRestartして、Notebookを接続します。API署名鍵は再起動後に作ります。

指定は NumPy 1.26.4、pandas 2.2.3、openpyxl 3.1.5、matplotlib 3.10.1、SciPy 1.13.1、scikit-learn 1.5.2、joblib 1.4.2、threadpoolctl 3.5.0、OCI SDK 2.185.2、cryptography 50.0.2です。PySpark、`aidputils`、IPythonはAIDPランタイムを使用し、requirementsから上書きしません。

`nb00` のCell 4と24でバージョンを確認します。OCI SDKとcryptographyは記事の記録値を採用し、[OCI SDK 2.185.2の依存指定](https://github.com/oracle/oci-python-sdk/blob/v2.185.2/setup.py)との範囲の整合も確認しています。ただし、このrequirementsを一括導入した配布版のAIDP動作確認は未実施です。パッケージ全体の依存関係解決・導入成功は、実際のComputeで確認してください。

## 4. 原本Excelをe-Statから別途入手する

出典は総務省統計局「令和2年国勢調査」「令和7年国勢調査」の人口等基本集計・原数値です。人口速報、不詳補完値、参考表とは区別します。

| 年度 | 表番号・内容 | 入手先 | 保存名 |
|---|---|---|---|
| 2020 | 1-1：人口・世帯数 | [e-Stat 表1-1](https://www.e-stat.go.jp/stat-search/files?stat_infid=000032142402) | `population_1_1.xlsx` |
| 2020 | 9-1：世帯の家族類型 | [e-Stat 表9-1](https://www.e-stat.go.jp/stat-search/files?stat_infid=000032142495) | `households_9_1.xlsx` |
| 2020 | 2-7：年齢別人口 | [e-Stat 表2-7](https://www.e-stat.go.jp/stat-search/files?stat_infid=000032142410) | `age_2_7.xlsx` |
| 2025 | 1-1：人口・世帯数 | [e-Stat 表1-1](https://www.e-stat.go.jp/stat-search/files?stat_infid=000040506423) | `population_1_1.xlsx` |
| 2025 | 9-1：世帯の家族類型 | [e-Stat 表9-1](https://www.e-stat.go.jp/stat-search/files?stat_infid=000040506456) | `households_9_1.xlsx` |
| 2025 | 2-7：年齢別人口 | [e-Stat 表2-7](https://www.e-stat.go.jp/stat-search/files?stat_infid=000040506431) | `age_2_7.xlsx` |

各ページで調査年・表番号・原数値であることを確認してEXCELを取得します。年別フォルダへ保存し、表の保存名に変更します。ExcelやNumbersで編集・再保存しないでください。原本のSHA-256が変わるとnb01が停止します。出典URLと原本ハッシュは、元セットの `config/source_registry.json` とNotebook内の定義を保持しています。本配布作業では6原本を再取得しての照合はしていません。

原本Volumeの見え方を次に揃えます。

```text
原本Volume（raw_root）/
├── 2020/
│   ├── population_1_1.xlsx
│   ├── households_9_1.xlsx
│   └── age_2_7.xlsx
└── 2025/
    ├── population_1_1.xlsx
    ├── households_9_1.xlsx
    └── age_2_7.xlsx
```

記事の例なら、バケットルートから `tokyo-census/raw/2020/` と `tokyo-census/raw/2025/` の接頭辞でそれぞれ3冊をアップロードします。`raw_root` の末尾に年度は付けません。nb00のCell 6で6冊の存在、Cell 8で成果物Volumeの読書きを確認します。

原本ハッシュが不一致なら、選んだ表・年度、編集や再保存、公式の訂正情報を確認してください。検査を無効にしたり列番号を推測して変更したりせず、訂正後の原本を検証してから読込定義を更新します。

## 5. パス・Widget・run IDを設定する

各Notebookで最初は **Cell 1だけ** を実行します。入力欄に表示された `REPLACE_WITH_...` と `SET_...` を自分の値へ変更してください。既存Widgetの値は保持するため、コードの初期値を書き換えるだけでは画面の現在値が変わらないことがあります。入力欄と `get()` の表示で確認します。

| 設定 | 変更する内容 |
|---|---|
| `raw_root` | 自分の原本Volume。nb01で設定。年度の親ディレクトリ |
| `work_root` | 自分の成果物Volume。nb01〜04で共通 |
| `census_year` | 2020、次に2025 |
| `source_run_id` | 各年度の取込みに付ける未使用ID |
| `source_run_id_2020` / `_2025` | nb01の各年度でPASSになった実際のID |
| `comparison_run_id` | nb02では未使用ID。nb03では61件の比較でPASSになったID |
| `boundary_policy` | 初回 `strict`。根拠を確認した後 `exclude_documented_machida` |
| `ai_run_id` | nb03では未使用ID。nb04ではnb03でPASSになったID |
| `target_area_code` / `top_n` | nb03の類似検索対象・表示件数。既定は新宿区 `13104`・5件 |
| `report_run_id` | 新規生成時は未使用ID。保存応答の再検査時だけ同じID |
| `model_name` | この配布版は `default.oci_ai_models.google.gemini-2.5-pro` を指定 |

run IDには英数字・ハイフン・アンダースコアを使い、先頭は英数字にしてください。`SET_` から始まる値は未設定として停止します。nb01・nb02は100文字以内、nb04は128文字以内です。短いIDを推奨します。

記事の `explain_20261020_03` の `_03` は筆者の実行例です。読者は自分の出力先で未使用のIDを選びます。**初回の未使用IDが `explain_20261020_01` でも拒否しません。** 新規生成時に筆者の値をそのまま使う必要はありません。

## 6. nb01 → nb02 → nb03を実行する

1. **nb01：2020年を取り込む。** `census_year=2020`、新しい `source_run_id` を設定し、Run all。62件・PASSと保存先を確認します。
2. **nb01：2025年を取り込む。** 年を2025へ変更し、別の未使用 `source_run_id` でRun all。最後のセルだけを再実行しないでください。
3. **nb02：strictで差を確認する。** 両年度のPASS済みID、未使用の `comparison_run_id`、`boundary_policy=strict` を設定してRun all。掲載データでは町田市（13209）の人口431,079人と組替人口431,083人の4人差を検知し、Cell 6で停止します。`boundary_comparison.json` と `validation.json` に記録を残し、比較テーブルを作りません。想定した停止は `BOUNDARY_MISMATCH` です。別のエラーなら原因を確認します。
4. **根拠を読み、61市区町村へ対象を変更する。** [相模原市の境界変更資料](https://www.city.sagamihara.kanagawa.jp/shisei/1026766/seido/1026777/1004437.html)と記事を確認します。人口だけを組み替えても世帯・年齢の比較条件は揃いません。失敗記録を残したまま、nb02の `boundary_policy=exclude_documented_machida` と **別の未使用comparison_run_id** に変更し、Run all。61件・PASS・除外コード13209を確認します。町田市以外や確認済み4人差以外の差は、この設定でも停止します。
5. **nb03：変化を分類する。** 61件の比較でPASSになったIDと新しい `ai_run_id` を設定し、Run all。評価・件数・グラフ・類似地域を確認します。strictで停止した比較IDは入力に使いません。

nb01〜03の出力を作り直す場合は未使用IDにし、後段の入力IDも合わせます。既存フォルダを消したり上書きしたりして進めません。結果を見直すだけならnb00を使います。

## 7. nb04：鍵登録を挟み、Cell単位で実行する

**初回のnb04はRun allで完了しません。Run allを使わず、以下の順に実行します。** AIDP本体は東京のまま、OCI SDKの推論先に大阪 `ap-osaka-1` を指定します。本セットはGemini 2.5 Pro用です。Widgetだけを別モデルに変えると停止します。

| 順序 | 操作 | API送信 |
|---|---|---|
| 1 | ライブラリ導入・ComputeのRestartと接続を完了。nb00のCell 24・26・28でライブラリ、DNS/TCP、nb03の保存結果を確認 | 生成AI送信なし。TCP確認のみ通信あり |
| 2 | nb04のCell 1だけ実行。自分のwork_root、PASS済みai_run_id、未使用report_run_id、モデル名をWidgetに設定 | なし |
| 3 | nb04のCell 3・5・7を順に実行して関数を定義。MarkdownのCell 2・4・6・8も読む | なし |
| 4 | **Cell 9＝Cell A** を実行。RSA鍵ペアをメモリ内で作り、公開鍵とFingerprintだけを表示 | なし |
| 5 | **ここで止め、OCIコンソールで公開鍵を登録**。My Profile → API keys → Add API key → Paste a public key。公開鍵のBEGIN〜ENDを貼り、Fingerprintを照合 | Notebookからの送信なし |
| 6 | **Cell 10＝Cell B** の3つのプレースホルダーを自分のOCIDに置換して実行 | クライアント準備のみ |
| 7 | **Cell 11＝Cell C** を実行。上流・設定を検査し、必要な場合だけ送信、保存、応答の検査を実施 | 新規応答が必要な場合に送信 |
| 8 | nb00のCell 30で保存結果を表示し、数値と文章を確認 | なし |

Cell Bの入力は、公開鍵を登録したIAMユーザーの `USER_OCID`、所属テナンシの `TENANCY_OCID`、生成AIを利用するコンパートメントの `GENAI_COMPARTMENT_OCID` です。WorkspaceやAIDPインスタンスのOCIDは指定しません。[API署名鍵の登録](https://docs.oracle.com/en-us/iaas/Content/Identity/access/to_upload_an_API_signing_key.htm)と[チャットAPI権限](https://docs.oracle.com/en-us/iaas/Content/generative-ai/chat-permissions.htm)は別の準備です。

Cell A〜Cは同じnb04・同じPythonセッションで実行します。秘密鍵を出力・保存する操作はありません。同じセッションでCell Aを再実行しても既存の鍵を使います。ComputeやPythonを再起動すると鍵を失うため、Cell Aで新しい鍵を作り、対応する公開鍵を登録してからCell Bへ進みます。検証後に不要になった鍵は、Fingerprintを照合して今回分だけをOCIから削除します。保存結果の閲覧にAPI署名鍵は不要です。

## 8. 保存先と再送防止

以下は `work_root` からの相対パスです。`{...}` はWidgetで指定したIDです。

| 出力 | 相対パス |
|---|---|
| 各年のParquet・検査 | `runs/{source_run_id}/curated/tokyo_year/`、`runs/{source_run_id}/validation.json` |
| 境域差・比較検査 | `comparisons/{comparison_run_id}/boundary_comparison.json`、同フォルダの `validation.json` |
| 比較Parquet・CSV | 同フォルダの `curated/tokyo_changes/`、`csv/tokyo_changes/` |
| 比較値の記録 | 同フォルダの `comparison_snapshot.json` |
| 分類・評価のParquet | `ai_runs/{ai_run_id}/ml/` 内の `input_snapshot/`、`assignments/`、`profiles/`、`evaluations/`、`k_summary/`、`nearest_neighbors/` |
| 学習設定・入力・検査JSON | 同 `ml/` 内の `model_parameters.json`、`k_evaluation.json`、`comparison_validation_snapshot.json`、`profile_payload.json`、`run_metadata.json`、`validation.json` |
| PNG | 同 `ml/charts/` 内の `feature_changes.png`、`share_movements.png`、`k_selection.png` |
| 生成AIの結果フォルダ | `ai_runs/{ai_run_id}/genai/{report_run_id}/` |

生成AIの結果フォルダには、送信前の `request.json`、応答取得時の `sdk_response_{attempt_id}.json`、抽出本文の `raw_response.json`、検査成功時の `validated_answer.json`・`validation.json`・`report_draft.md` を保存します。失敗内容に応じて `sdk_service_error_{attempt_id}.json`、`validation_failure_{hash}.json` が残ります。失敗段階によってすべてのファイルが揃うとは限りません。

- **同じreport_run_id・同じ入力・モデル・接続設定で応答保存済み**：保存応答を再利用します。
- **既存記録と設定が異なる**：停止します。リージョン、モデル、コンパートメント、推論設定も照合対象です。
- **request.jsonのみ残る／本文抽出前に失敗**：送信・課金状態が不明なため自動再送しません。SDK応答やエラー、サービス側の結果を確認し、再送すると決めた場合にだけ新しいIDを使います。
- **JSONや数値検査が失敗**：保存済み応答を残します。同じIDで再実行しても新しい応答にはなりません。意図して再生成する場合のみ新しいIDにします。

SDKの自動再試行は無効にしていますが、サービス全体での厳密な一回限りの実行を保証するものではありません。同じIDを複数Notebookから同時に実行しないでください。

CSVは単一の `tokyo_changes.csv` ではなくフォルダ内の `part-...csv` です。`_SUCCESS` は本文ではありません。Object Storageから取得する際は、実際のVolumeとバケット接頭辞の対応を確認します。

## 9. 保存結果だけを表示する

`nb00_check_and_capture.ipynb` のCell 2で、自分のパスと各段階の実際のIDを設定します。その後、必要なコードCellだけを選んで実行します。先行段階が未完了なら該当結果の表示セルはまだ実行しません。**nb00もRun allは使いません。**

| コードCell | 内容 |
|---|---|
| 4 / 24 | Python・Spark・分析ライブラリ / OCI SDK・cryptographyのバージョン |
| 6 / 8 | 原本6冊の存在 / 出力Volumeの専用ファイルで読書き確認 |
| 10 | 両年の検査と年別Parquet |
| 12 | strictで停止した境域差の記録 |
| 14 | 61市区町村の比較テーブル |
| 16 | 機械学習の検査・k評価・所属 |
| 18 | 各クラスタの所属と、渋谷区・八王子市の人数・割合 |
| 20 / 22 | 保存グラフ / 新宿区に近い市区町村 |
| 26 / 28 | DNS・TCP確認 / nb03の検査JSON |
| 30 | 生成AIの保存ファイル・検査JSON・説明案 |

結果の表示は再取込み・再学習・生成AI送信を行いません。書込み確認だけは専用プローブを作って削除し、通信確認はDNS/TCP接続を行います。表中の検索条件・2地域は記事の確認例です。

**生成AIの構造・根拠数値がPASSでも、文章確認は必要です。** `validation_scope=schema_and_evidence_only`、`human_review=REQUIRED` は、因果関係や文章の意味の正しさを保証するものではありません。「数」と「割合」、市区町村単純平均と東京都全体、増減方向、年齢不詳率と分母、根拠のない原因・将来予測を確認します。原文は保存したまま、記事用の表現を別途整えます。

## 10. ファイルの完全性を確認する

`FILELIST.txt` はZIP内の全ファイル名を列挙します。`SHA256SUMS.txt` は、**SHA256SUMS.txt自身を除く全ファイル**（FILELIST.txtとREADMEを含む）のSHA-256を記録します。自己ハッシュは循環するため含めません。ZIP自体のSHA-256はZIPと並ぶ `.zip.sha256` ファイルで確認します。

Mac / Linuxでは展開したフォルダで `shasum -a 256 -c SHA256SUMS.txt`（Linuxでは `sha256sum -c SHA256SUMS.txt` も可）を実行できます。内容を編集する前に確認してください。ファイルを編集すると、そのファイルのハッシュは配布時の値から変わります。

## 11. 動作確認の範囲

| 範囲 | 状態 |
|---|---|
| 筆者の記事に掲載された元実行 | 記事にはAIDPでの2026年10月20〜21日の処理と11月9日の追加確認、生成AIの成功ログを掲載。この配布作業での再実行ではありません |
| 配布版のNotebook JSON・構文・空の出力・依存参照・展開構成・ハッシュ | 配布時のローカル検査対象。詳細はZIPと併せて提示する確認結果を参照 |
| 境域比較、構造・数値検査、SDK送信記録・再送防止 | 同梱元データや合成データ・偽SDKによるローカル検査。実サービス成功を示しません |
| 配布版のAIDPへのインポート、Widget操作、Spark・Volume入出力、Library一括導入 | 未実行。既存Widgetの保持と未設定値の停止を含む配布時の変更は実機未確認 |
| 本配布作業での生成AI呼出し・新規認証鍵のOCI登録 | 未実施。有料APIリクエストは送っていません |
| 配布先 | [shirok-tech/oracle-aidp-hands-on](https://github.com/shirok-tech/oracle-aidp-hands-on) のGitHub Releases。Assetsにある実行セットZIPを取得してください |

年別読込定義、比較・学習の中核処理、Cell A〜Cの送信・検査処理は元資料から引き継いでいます。Widget用セルを先頭へ組み込み、パス・IDを説明付きプレースホルダーにし、既存Widgetを保持するようにしました。nb04は旧実行セルを取り除いてCell A〜Cを収録し、nb00は記事の確認コードをパラメータ化しています。記事の画像や実行結果は配布ZIPへ同梱せず、記事側で保持しています。

## 12. 出典

統計表は本READMEのe-Stat各表リンクと `config/source_registry.json` を参照してください。人口・世帯・年齢データを加工して比較表・図・分類を作成します。入力は東京都62市区町村、比較・機械学習は町田市を除く61市区町村です。生成AIの名称・文章は提案であり、公式統計機関の分類・見解ではありません。

- [国勢調査 結果利用上の注意](https://www.stat.go.jp/data/kokusei/2025/kekka/chuui-riyou.html)
- [AIDP Manage Libraries](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/manage-libraries.html)
- [AIDP Notebooks](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/notebooks.html)
- [OCI モデル別・リージョン別の提供状況](https://docs.oracle.com/en-us/iaas/Content/generative-ai/model-endpoint-regions.htm)

このセットの実行方式は対話Notebookです。Workflow・スケジュール実行、Agentへの組込み、別モデル・別ランタイムは確認範囲に含みません。
