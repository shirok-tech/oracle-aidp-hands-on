# ■ AIDPの設定手順

ブログv0.4で確認した構成を再現するための設定です。リソース名は検証時の例で、OCID・資格情報の指定は含みません。

## ● データ準備

**1) Spark Computeと保存先を確認する**

| 項目 | 検証時の値 |
|---|---|
| Workspace | `AIDP_OpenData_PoC` |
| Spark Compute | `Census_PoC_Cluster` |
| カタログ / スキーマ | `blog_catalog` / `opendata` |
| Volume | `census_work` |
| 比較Run ID | `compare61_20261020_01` |
| AI Run ID | `change_ml_20261020_01` |

Notebook・Compute・テーブルを利用する権限と、入力ファイルの読取権限を確認します。Notebookでは既存のカタログ・スキーマを使うため、未作成なら先に用意します。

**2) 入力ファイルを指定する**

通常は次のVolumeデータを使用します。

| 入力 | パス |
|---|---|
| CSV | `/Volumes/blog_catalog/opendata/census_work/comparisons/compare61_20261020_01/csv/tokyo_changes/part-*.csv` |
| 4つのJSON | `/Volumes/blog_catalog/opendata/census_work/ai_runs/change_ml_20261020_01/ml/` |

同梱データを使う場合は `inputs/` の全5ファイルをアップロードし、Notebookで `USE_BUNDLED_INPUTS=True` にします。`BUNDLED_INPUT_DIR` はPythonから読める実パスへ変更してください。JSONを別のRunのものに入れ替えないでください。

**3) Notebookを上から実行する**

[nb05_prepare_agent_tables.ipynb](../nb05_prepare_agent_tables.ipynb) をWorkspaceにアップロードし、Spark Computeをアタッチします。Pythonのデータ検証を通過してから、2つのDeltaテーブルを作成します。

同名テーブルがあると初期設定では停止します。内容を確認して再作成する場合だけ `ALLOW_REPLACE_PART3_TABLES=True` に変更します。元のVolumeには書き込みません。別名にする場合は `TABLE_SUFFIX` とツール側のSQLを揃えます。

## ● AI ComputeとAgent

**1) AI Computeを作成する**

対象Workspaceの [Create] → [AI Compute] で設定します。

| 項目 | 検証時の値 |
|---|---|
| Name | `Census_Agent_AI_Compute` |
| OCPUs per replica | 1 |
| Memory per replica | 16 GB |
| Auto-scaling | 無効 |
| Compute replicas | 1 |

Activeを確認してからAgentへ進みます。この構成は検証用で、利用人数に対する性能保証値ではありません。

**2) Visual BuilderでAgentを作成する**

| 項目 | 値 |
|---|---|
| Agent flow名 | `Tokyo_Census_Agent` |
| Authoring mode | Visual builder |
| 実行先 | `Census_Agent_AI_Compute` |
| 接続 | Chat Trigger → Executor Agent |
| Executor名 | `Tokyo_Census_SQL_Analyst` |
| Model configuration | OCI Generative AI service |
| Region | `ap-tokyo-1` |
| Model | `google.gemini-2.5-pro` |

モデルとリージョンはブログの成功時設定です。利用可能な選択肢・権限は実行環境で確認します。Executorの [Agent instructions] に [agent_instructions.txt](../prompts/agent_instructions.txt) を貼り付けます。

## ● SQLツールを登録する

[Tool templates] の [SQL] を追加してAgentへ接続し、5つのツールを作成します。Query dialectはSpark SQL、ClusterはActiveの `Census_PoC_Cluster`、Catalog / Schemaは `blog_catalog` / `opendata` です。

| ツール名 | Queryファイル | 変数 | Max rows |
|---|---|---|---:|
| `list_areas` | [01_list_areas.sql](../sql/01_list_areas.sql) | なし | 61 |
| `get_area_metrics` | [02_get_area_metrics.sql](../sql/02_get_area_metrics.sql) | `area_code` | 1 |
| `rank_population_growth` | [03_rank_population_growth.sql](../sql/03_rank_population_growth.sql) | なし | 5 |
| `find_similar_areas` | [04_find_similar_areas.sql](../sql/04_find_similar_areas.sql) | `area_code` | 5 |
| `get_cluster_summary` | [05_get_cluster_summary.sql](../sql/05_get_cluster_summary.sql) | なし | 2 |

Descriptionには [tool_descriptions.md](tool_descriptions.md) の内容を貼り付けます。`area_code` は整数型（検証画面ではInteger）、デフォルト値は未設定、説明は「list_areasで確認した市区町村コードの整数」とします。SQL内の `{{area_code}}` は残したまま登録します。

各ノードの [Test] で、変数のあるツールは13201を入力して [Submit]、変数のないツールは [Run test] をクリックします。結果を [expected_results.json](../expected_results.json) と照合します。

SQLツールは停止中のSpark Computeを自動起動しません。検証中にActiveを維持する必要がある場合は、変更前のRun durationを記録して [Forever] にします。AI ComputeとSpark Computeはそれぞれ必要です。

## ● Skillと会話履歴

**1) Skillを作成してAddする**

基本構成の動作確認後、Flow上のExecutorを選択し、下部の [Skills] → [Create new] → [Create from scratch] を開きます。

| 項目 | 値 |
|---|---|
| Name | `tokyo_census_interpretation` |
| Description | 東京都の年次比較を、単位・分母・年齢不詳率に注意して説明するときに使用する |
| Instructions | [census_analysis_skill_instructions.txt](../prompts/census_analysis_skill_instructions.txt) |

作成後、一覧から選択して [Add] をクリックします。[Added] とノードの `Skills: 1` を確認し、新しいPlaygroundセッションで試します。このテキストはAIDPのSkill設定用で、CodexへインストールするSkillではありません。

**2) Contextを設定する**

| 設定 | 値 |
|---|---|
| Enable Agent Memory | 有効 |
| Limit conversation history | 有効 |
| Truncation Configuration | Keep Last N messages |
| Maximum Message Limits | 20 |
| Limit tool output memory | 無効 |

同一セッションでの短い会話を確認した構成です。長期記憶・セッション間共有・20メッセージを超えた切り詰めは検証していません。

## ● 終了処理

停止前に必要なTraceとMetricsを記録します。MetricsのCPU・メモリ使用率は、請求額や総消費Unitsとは別の記録です。

AI Computeは [Compute] → [AI compute] → 対象の [...] → [Stop]、Spark Computeは対象詳細の [Actions] → [Stop] で停止し、状態を確認します。SparkのRun durationを変更した場合は [Edit] で元の方式・分数へ戻し、[Save] をクリックします。

ブログの検証ではAI Computeを最終的に削除しています。停止のみなら起動し直し、削除した場合はAI Computeを新たに用意してAgentへアタッチしてから再検証します。本セットのアップロードだけではComputeは作成・起動されません。

## ● 公式資料

- [AI Compute](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/ai-compute.html)
- [Agent Creation](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html)
- [About Agent Tools](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-flow-tools.html)
- [Monitor Agents](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/monitor-agent-flows.html)
- [Manage Compute](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/manage-compute.html)

参照日：2026年11月18日。
