# Oracle AIDP Hands-on

Oracle AI Data Platform（AIDP）のQiita記事で使用するNotebookと実行セットです。

## AIDP第2回：2020年・2025年の国勢調査を分析する

東京都の市区町村の変化を比較し、K-meansで分類して生成AIで説明します。入力は62市区町村、比較・機械学習は町田市の境域差を確認して除外した61市区町村です。

配布版は **v1.0** です。**[実行セットZIPをダウンロード](https://github.com/shirok-tech/oracle-aidp-hands-on/releases/download/v1.0/aidp-census-change-v1.0.zip)** して展開し、最初にREADMEを読んでください。自動生成の「Source code (zip)」とは別のファイルです。

[Releaseページ](https://github.com/shirok-tech/oracle-aidp-hands-on/releases/tag/v1.0) ／ [ZIPのSHA-256](https://github.com/shirok-tech/oracle-aidp-hands-on/releases/download/v1.0/aidp-census-change-v1.0.zip.sha256)

- [実行手順・前提環境・e-Stat入手先](aidp-census-change-v1.0/README.md)
- [Notebookとライブラリ定義](aidp-census-change-v1.0/)
- [配布ファイルのSHA-256](aidp-census-change-v1.0/SHA256SUMS.txt)

実行セットにはnb01〜nb04、確認用nb00、日本語README、requirements、年別読込定義、参照用ソース、ファイル一覧とSHA-256を含みます。原本Excelは同梱していません。READMEに記載したe-Statの表を別途入手してください。

先頭Widgetセルとnb04のCell A〜Cは組込み済みです。二重に追加せず、パス・run ID・OCIDを自分の値へ変更します。**nb04の初回はRun allを使わず、公開鍵の登録を挟んでCell単位で実行します。**

## 確認範囲

配布版のJSON構造・コード構文・依存参照・ZIP展開・ハッシュを確認し、境域差・根拠数値検査・再送防止などのローカルテスト26件が成功しています。SDK送信部分は偽SDKによる検査です。

この配布版をAIDPで再実行した確認、Library一括導入、実サービスへの生成AI送信は未実施です。記事に掲載された筆者の実行記録とは区別してください。数値照合がPASSでも文章確認は必要です。

認証情報、秘密鍵、個人用設定ファイル、Notebookの実行出力は含めていません。

## データの出典

総務省統計局「令和2年国勢調査」「令和7年国勢調査」（e-Stat）の人口等基本集計・原数値を加工して分析します。各表へのリンクと取扱いは実行セットのREADMEを参照してください。クラスタ分類と生成AIの説明案は、公式統計機関の分類・見解ではありません。
