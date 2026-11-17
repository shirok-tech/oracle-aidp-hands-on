# ■ Oracle AIDP Tokyo Census Agent

Oracle AI Data Platform（AIDP）のAI Computeで、東京都61市区町村の2020年・2025年の比較結果を説明するAIエージェントを作成する実行セットです。

対応記事：**Oracle AI Data Platform（AIDP）のAI Computeで東京都の地域分析AIエージェントを作成してみた【第3回】**（ブログv0.4対応）

実行セットのバージョンは **v0.2.0** です。ブログの版番号とは別に管理しています。

Agentが5つの事前定義SQLツールから必要なものを選び、Spark Computeで取得した数値をLLMで説明します。SQL文の自動生成、クラスタの再学習、将来人口の予測は行いません。

## ● できること

| 質問・確認 | 使用するもの |
|---|---|
| 八王子市の人口・世帯・年齢構成の変化 | `list_areas`、`get_area_metrics` |
| 人口増減率の上位5地域 | `rank_population_growth` |
| 八王子市に似た変化を示す地域 | `find_similar_areas` |
| 2つのクラスタの特徴 | `get_cluster_summary` |
| 数値の読み方の再利用 | AIDPのSkill `tokyo_census_interpretation` |
| 回答の根拠と会話履歴の扱い | PlaygroundのTest details / Trace |

## ● ファイル構成

| ファイル | 用途 |
|---|---|
| [nb05_prepare_agent_tables.ipynb](nb05_prepare_agent_tables.ipynb) | AIDPで参照テーブルを作成・検証するNotebook |
| [prepare_agent_data.py](prepare_agent_data.py) | Notebookに埋め込んだものと同じデータ準備関数 |
| [inputs/](inputs/) | 第2回から引き継いだ比較CSVと4つのJSON |
| [sql/](sql/) | Agentへ登録する5つのSQL |
| [prompts/agent_instructions.txt](prompts/agent_instructions.txt) | Agent Instructions |
| [prompts/census_analysis_skill_instructions.txt](prompts/census_analysis_skill_instructions.txt) | AIDPのSkillのInstructions |
| [docs/setup.md](docs/setup.md) | Compute・Agent・SQLツール・Skillの設定手順 |
| [docs/tool_descriptions.md](docs/tool_descriptions.md) | 各SQLツールのDescription |
| [docs/playground_checks.md](docs/playground_checks.md) | 質問例、Traceの確認方法、確認結果 |
| [docs/data_provenance.md](docs/data_provenance.md) | 同梱データの由来・比較条件・注意点 |
| [expected_results.json](expected_results.json) | 5つのSQLに対する数値照合用の結果 |
| [scripts/validate_package.py](scripts/validate_package.py) | Python標準ライブラリだけで行うローカル検証 |
| [validation_manifest.json](validation_manifest.json) | この公開セットのローカル検証記録 |
| [SHA256SUMS](SHA256SUMS) | 配布ファイルのSHA-256 |

## ● 最初に行うこと

**1) ローカルで実行セットを確認する（任意）**

Python 3.11以上を使用し、このREADMEがあるフォルダーで実行します。追加のpipインストールは不要です。

```bash
python3 scripts/validate_package.py
```

地域61件、類似地域305件、クラスタ17件・44件、5つのSQLの期待値、NotebookとPython/SQLファイルの一致を検証します。ローカルSQLの確認にはSQLiteを使い、AIDPへの接続や書き込みは行いません。

**2) AIDPでデータを準備する**

既存Spark Computeと同じWorkspaceへNotebookをアップロードし、そのComputeをアタッチします。セルを上から実行すると次のテーブルが作成されます。

| テーブル | 件数 |
|---|---:|
| `blog_catalog.opendata.census_agent_areas_v1` | 61 |
| `blog_catalog.opendata.census_agent_neighbors_v1` | 305 |

標準では第2回のVolumeを読み込みます。第2回の環境がない場合は、同梱の `inputs/` をAIDP側へアップロードし、Notebookの `USE_BUNDLED_INPUTS=True` と `BUNDLED_INPUT_DIR` を設定します。アップロード後の実パスは利用環境で確認してください。

`blog_catalog.opendata` を作成・参照できる権限が必要です。別のカタログ・スキーマ・テーブル名を使う場合はNotebookの設定と、Agentに登録する5つのSQLの完全修飾名を揃えます。

**3) Agentを設定する**

[設定手順](docs/setup.md) に従い、AI Compute、Executor Agent、5つのSQLツールを作成します。Agent FlowはAIDPのVisual Builderで構成します。このセットに一括インポート用のAgent Flow定義は含めていません。

**4) 質問・Trace・終了処理を確認する**

[Playgroundの確認手順](docs/playground_checks.md) に従って質問し、回答を `expected_results.json` と照合します。検証終了後は、AI ComputeとSpark Computeを停止します。

## ● 確認した範囲

| 区分 | 状況 |
|---|---|
| ブログのAIDP環境 | Deltaテーブル作成、Spark SQL、5ツールの単体実行、Playgroundの主要質問、Skill読み込み、同一セッションの文脈引継ぎを確認 |
| この配布セット | データの再計算、SQLiteによるSQL照合、コードの構文、Notebookとの一致をローカルで確認 |
| Skill単独の品質改善 | 条件を揃えた比較は未実施 |
| 対象外の質問 | Agentの応答は未検証。SQL単体では町田市が0件になることを確認 |
| デプロイとAPI | 未実施 |

ブログの検証では、続きの比較質問で過去のツール結果を利用したと考えられる回答があり、SQLの再実行は記録されませんでした。回答末尾の「使用ツール」だけで判断せず、該当質問のTraceを確認します。

`expected_results.json` は照合用データで、Agentの実行ログではありません。ブログでの成功と、別環境での動作確認は区別してください。元データの扱いは [データの由来](docs/data_provenance.md) を参照してください。
