"""第2回の保存データから第3回の参照用レコードを作る。外部通信・Spark書込はしない。"""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

FEATURES = ["population_growth_pct", "single_share_change_pp", "elderly_share_change_pp"]
FLOAT_COLUMNS = [
    "single_households_pct_2020", "age_65plus_share_known_pct_2020", "age_unknown_pct_2020",
    "single_households_pct_2025", "age_65plus_share_known_pct_2025", "age_unknown_pct_2025",
    *FEATURES, "age_unknown_change_pp",
]
INT_COLUMNS = ["area_code", "population_2020", "population_2025"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prepare_records(csv_paths, ml_root, expected_comparison="compare61_20261020_01",
                    expected_ai="change_ml_20261020_01"):
    ml_root = Path(ml_root)
    metadata = load_json(ml_root / "run_metadata.json")
    params = load_json(ml_root / "model_parameters.json")
    payload = load_json(ml_root / "profile_payload.json")
    validation = load_json(ml_root / "comparison_validation_snapshot.json")
    require(metadata["comparison_run_id"] == expected_comparison, "比較Run IDが一致しません")
    require(metadata["ai_run_id"] == expected_ai, "AI Run IDが一致しません")
    require(payload["ai_run_id"] == expected_ai, "profile_payloadのAI Run IDが不一致")
    require(payload["comparison_run_id"] == expected_comparison, "profile_payloadの比較Run IDが不一致")
    require(validation["comparison_run_id"] == expected_comparison, "validationの比較Run IDが不一致")
    require(validation["status"] == "PASS" and validation["accepted"] is True, "比較条件が未承認です")
    require(params["features"] == FEATURES, "特徴量の順序が異なります")
    require(params == metadata["model_parameters"], "モデルパラメータがmetadataと不一致です")
    require(validation["period"] == "2020-2025", "想定外の比較期間です")
    require(set(map(str, validation["excluded_area_codes"])) == {"13209"}, "対象地域の条件が異なります")
    require(payload["municipality_count"] == 61 and validation["rows"] == 61, "想定する件数は61です")
    scales = params["scaler_scale"]
    require(len(scales) == 3 and all(math.isfinite(s) and s > 0 for s in scales), "標準化のスケールが不正です")

    membership = {}
    for cluster in payload["clusters"]:
        require(cluster["member_count"] == len(cluster["members"]), "クラスタ内件数が不一致")
        for member in cluster["members"]:
            code = int(member["area_code"])
            require(code not in membership, "クラスタ所属に地域コードの重複があります")
            membership[code] = (member["area_name"], int(cluster["cluster_id"]))

    require(csv_paths, "CSVが見つかりません。csv/tokyo_changes内のpart-*.csvを確認してください")
    rows, file_checksums = [], {}
    for path in sorted(map(Path, csv_paths)):
        file_checksums[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            needed = set(INT_COLUMNS + FLOAT_COLUMNS + ["area_name"])
            require(needed <= set(reader.fieldnames or []), f"列が不足しています: {path}")
            for raw in reader:
                row = {k: int(raw[k]) for k in INT_COLUMNS}
                row["area_name"] = raw["area_name"]
                for key in FLOAT_COLUMNS:
                    value = raw[key].strip()
                    row[key] = None if value in ("", "NULL", "null") else float(value)
                    require(row[key] is None or math.isfinite(row[key]), f"非有限値: {key}")
                require(row["area_code"] in membership, "CSVとクラスタ所属の地域集合が異なります")
                name, cluster_id = membership[row["area_code"]]
                require(name == row["area_name"], "地域名が一致しません")
                row["cluster_id"] = cluster_id
                require(all(row[f] is not None for f in FEATURES), "特徴量にNULLがあります")
                require(row["population_2020"] > 0, "基準人口は正数である必要があります")
                expected = {
                    "population_growth_pct": (row["population_2025"] / row["population_2020"] - 1) * 100,
                    "single_share_change_pp": row["single_households_pct_2025"] - row["single_households_pct_2020"],
                    "elderly_share_change_pp": row["age_65plus_share_known_pct_2025"] - row["age_65plus_share_known_pct_2020"],
                }
                a, b = row["age_unknown_pct_2020"], row["age_unknown_pct_2025"]
                expected["age_unknown_change_pp"] = None if a is None or b is None else b - a
                for key, value in expected.items():
                    if value is None:
                        require(row[key] is None, "NULLがゼロ等に置き換わっています")
                    else:
                        require(row[key] is not None and math.isclose(row[key], value, abs_tol=1e-8), f"計算不一致: {key}")
                row.update(comparison_run_id=expected_comparison, ai_run_id=expected_ai)
                rows.append(row)
    rows.sort(key=lambda r: r["area_code"])
    require(len(rows) == 61, f"件数不一致: {len(rows)}")
    require(len({r["area_code"] for r in rows}) == 61, "地域コードが重複しています")
    require(set(r["area_code"] for r in rows) == set(membership), "CSVとクラスタ所属が不一致")
    require(13209 not in membership, "町田市が含まれています")
    counts = Counter(r["cluster_id"] for r in rows)
    require(dict(counts) == {0: 17, 1: 44}, f"クラスタ構成が異なります: {counts}")
    # 保存済みクラスタ中心とCSVの平均も照合。Run IDだけで数値一致とは判断しない。
    for cid in counts:
        subset = [r for r in rows if r["cluster_id"] == cid]
        for i, feature in enumerate(FEATURES):
            avg = sum(r[feature] for r in subset) / len(subset)
            require(math.isclose(avg, params["cluster_centers_original_units"][cid][i], abs_tol=1e-8),
                    f"CSVと保存済みクラスタ中心の不一致: cluster={cid}, feature={feature}")

    neighbors = []
    for src in rows:
        candidates = []
        for dst in rows:
            if src["area_code"] == dst["area_code"]:
                continue
            distance = math.sqrt(sum(((src[f] - dst[f]) / scale) ** 2 for f, scale in zip(FEATURES, scales)))
            candidates.append((distance, dst["area_code"], dst))
        for rank, (distance, _, dst) in enumerate(sorted(candidates)[:5], 1):
            neighbors.append({
                "source_area_code": src["area_code"], "source_area_name": src["area_name"],
                "neighbor_rank": rank, "neighbor_area_code": dst["area_code"], "neighbor_area_name": dst["area_name"],
                "distance_standardized": distance, "neighbor_cluster_id": dst["cluster_id"],
                "population_growth_pct": dst["population_growth_pct"],
                "single_share_change_pp": dst["single_share_change_pp"],
                "elderly_share_change_pp": dst["elderly_share_change_pp"],
                "age_unknown_pct_2020": dst["age_unknown_pct_2020"],
                "age_unknown_pct_2025": dst["age_unknown_pct_2025"],
                "age_unknown_change_pp": dst["age_unknown_change_pp"],
                "comparison_run_id": expected_comparison, "ai_run_id": expected_ai,
            })
    require(len(neighbors) == 305, "類似地域件数が不一致です")
    manifest = {
        "comparison_run_id": expected_comparison, "ai_run_id": expected_ai,
        "area_rows": len(rows), "neighbor_rows": len(neighbors), "cluster_counts": dict(counts),
        "source_csv_file_sha256": file_checksums,
        "similarity": "Euclidean distance on the three features using saved scaler_scale; all 60 other municipalities are candidates",
        "note": "CSV bytes hash is a new file hash, not the row-level/Parquet hash recorded in Part 2",
    }
    return rows, neighbors, manifest
