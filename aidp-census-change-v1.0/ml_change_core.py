"""Pure driver-side KMeans logic shared verbatim with nb03_cluster_changes.

Inputs are already validated Spark comparison rows; the checks below independently
protect the ML boundary. No Oracle connection or Spark session is needed to test it.
"""
import hashlib
import itertools
import json
import math
from collections import Counter

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

FEATURES = (
    "population_growth_pct",
    "single_share_change_pp",
    "elderly_share_change_pp",
)
SOURCE_COLUMNS = (
    "area_code", "area_name", "population_2020", "population_2025",
    "population_growth_pct", "single_households_pct_2020",
    "single_households_pct_2025", "single_share_change_pp",
    "age_65plus_share_known_pct_2020", "age_65plus_share_known_pct_2025",
    "elderly_share_change_pp", "age_unknown_pct_2020", "age_unknown_pct_2025",
    "age_unknown_change_pp",
)
FEATURE_DEFINITIONS = [
    {"metric": FEATURES[0], "unit": "percent", "period": "2020-2025",
     "definition": "100 * (population_2025 / population_2020 - 1); five-year growth, not annual growth"},
    {"metric": FEATURES[1], "unit": "percentage_points", "period": "2020-2025",
     "definition": "single-household share in 2025 minus 2020; each share denominator is general households"},
    {"metric": FEATURES[2], "unit": "percentage_points", "period": "2020-2025",
     "definition": "65-plus share in 2025 minus 2020; each share denominator is population with known age"},
]


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def comparison_input_hash(records):
    """Match comparison_core.canonical_hash exactly, before projecting columns."""
    data = json.dumps(sorted(records, key=lambda row: row["area_code"]),
                      ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def verify_comparison_input(metadata, raw_records, comparison_run_id, input_path):
    required = {"status": "PASS", "comparison_run_id": comparison_run_id,
                "target": input_path, "period": "2020-2025", "series": "original",
                "unknown_policy": "preserve_dash_as_null"}
    for key, expected in required.items():
        if metadata.get(key) != expected:
            raise ValueError(f"Comparison validation missing or mismatched {key}: expected {expected!r}")
    expected_rows = metadata.get("rows")
    if isinstance(expected_rows, bool) or expected_rows not in (61, 62) or len(raw_records) != expected_rows:
        raise ValueError("Comparison validation row count mismatch")
    # Hash the complete raw Spark row dictionaries. Dropping an extra source
    # column or coercing types before hashing would weaken the manifest check.
    observed_hash = comparison_input_hash(raw_records)
    if metadata.get("comparison_sha256") != observed_hash:
        raise ValueError("Comparison input hash mismatch or missing comparison_sha256")
    return observed_hash


def report_round(value):
    rounded = round(float(value), 2)
    return 0.0 if rounded == 0.0 else rounded


def finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: finite numeric value required")
    return float(value)


def validate_records(records, expected_rows=62):
    if len(records) != expected_rows:
        raise ValueError(f"Expected {expected_rows} municipalities, received {len(records)}")
    clean = []
    codes = set()
    for record in records:
        row = {column: record[column] for column in SOURCE_COLUMNS}
        code = row["area_code"]
        if not isinstance(code, str) or len(code) != 5 or not code.isdigit() or code in codes:
            raise ValueError(f"Invalid or duplicate area_code: {code!r}")
        codes.add(code)
        if not isinstance(row["area_name"], str) or not row["area_name"].strip():
            raise ValueError(f"{code}: nonempty area_name required")
        for column in ("population_2020", "population_2025"):
            value = row[column]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{code}.{column}: positive integer required")
        for column in SOURCE_COLUMNS[4:]:
            value = row[column]
            if value is None and column.startswith("age_unknown_"):
                continue
            row[column] = finite_number(value, f"{code}.{column}")
            if column.endswith(("_2020", "_2025")) and not 0 <= row[column] <= 100:
                raise ValueError(f"{code}.{column}: share outside 0..100")
        expected = {
            "population_growth_pct": (row["population_2025"] / row["population_2020"] - 1) * 100,
            "single_share_change_pp": row["single_households_pct_2025"] - row["single_households_pct_2020"],
            "elderly_share_change_pp": row["age_65plus_share_known_pct_2025"] - row["age_65plus_share_known_pct_2020"],
        }
        for column, value in expected.items():
            if not math.isclose(row[column], value, rel_tol=1e-9, abs_tol=1e-8):
                raise ValueError(f"{code}.{column}: delta disagrees with source values")
        unknowns = row["age_unknown_pct_2020"], row["age_unknown_pct_2025"]
        if any(value is None for value in unknowns):
            if row["age_unknown_change_pp"] is not None:
                raise ValueError(f"{code}: unknown-age delta must be NULL when either input is NULL")
        elif row["age_unknown_change_pp"] is None or not math.isclose(
                row["age_unknown_change_pp"], unknowns[1] - unknowns[0], abs_tol=1e-8):
            raise ValueError(f"{code}: unknown-age delta disagrees with source values")
        clean.append(row)
    return sorted(clean, key=lambda row: row["area_code"])


def evaluate_clusters(matrix, seeds=(42, 7, 21), k_values=range(2, 7)):
    """Return candidates and final model; all three seeds must avoid singleton clusters."""
    unique_count = len(np.unique(matrix, axis=0))
    if unique_count < 2:
        raise ValueError("All change vectors are identical; clustering is not meaningful")
    evaluations, summaries, models = [], [], {}
    for k in k_values:
        if k >= len(matrix) or k > unique_count:
            summaries.append({"k": int(k), "eligible": False,
                              "reason": "insufficient distinct vectors",
                              "mean_silhouette": None, "min_cluster_size_all_seeds": None,
                              "min_pairwise_ari": None, "mean_pairwise_ari": None})
            continue
        labels_by_seed = {}
        scores, min_sizes = [], []
        for seed in seeds:
            model = KMeans(n_clusters=k, random_state=seed, n_init=20,
                           max_iter=300, tol=1e-4, algorithm="lloyd").fit(matrix)
            labels = model.labels_
            labels_by_seed[seed] = labels
            models[(k, seed)] = model
            sizes = np.bincount(labels, minlength=k)
            score = float(silhouette_score(matrix, labels))
            scores.append(score)
            min_sizes.append(int(sizes.min()))
            evaluations.append({"k": int(k), "seed": int(seed), "silhouette": score,
                                "inertia": float(model.inertia_), "min_cluster_size": int(sizes.min()),
                                "singleton_count": int(np.sum(sizes == 1)),
                                "cluster_sizes": [int(value) for value in sizes]})
        pairwise = [{"seed_a": int(a), "seed_b": int(b),
                     "ari": float(adjusted_rand_score(labels_by_seed[a], labels_by_seed[b]))}
                    for a, b in itertools.combinations(seeds, 2)]
        for row in evaluations:
            if row["k"] == k:
                row["ari_to_seed42"] = float(adjusted_rand_score(labels_by_seed[42], labels_by_seed[row["seed"]]))
        summaries.append({"k": int(k), "eligible": min(min_sizes) >= 2,
                          "reason": "eligible" if min(min_sizes) >= 2 else "singleton cluster in at least one seed",
                          "mean_silhouette": float(np.mean(scores)),
                          "min_cluster_size_all_seeds": min(min_sizes),
                          "min_pairwise_ari": min(item["ari"] for item in pairwise),
                          "mean_pairwise_ari": float(np.mean([item["ari"] for item in pairwise])),
                          "pairwise_ari": pairwise})
    eligible = [row for row in summaries if row["eligible"]]
    if not eligible:
        raise ValueError("No k from 2..6 avoids singleton clusters for every seed. Review data/features; do not force a result")
    selected = min(eligible, key=lambda row: (-round(row["mean_silhouette"], 12), row["k"]))
    return evaluations, summaries, models[(selected["k"], 42)]


def unknown_context(members):
    output = {}
    for year in (2020, 2025):
        values = [row[f"age_unknown_pct_{year}"] for row in members
                  if row[f"age_unknown_pct_{year}"] is not None]
        output[f"year_{year}"] = {
            "available_count": len(values), "null_count": len(members) - len(values),
            "mean_pct": report_round(np.mean(values)) if values else None,
            "max_pct": report_round(max(values)) if values else None,
        }
    values = [row["age_unknown_change_pp"] for row in members if row["age_unknown_change_pp"] is not None]
    output["change"] = {
        "available_count": len(values), "null_count": len(members) - len(values),
        "mean_pp": report_round(np.mean(values)) if values else None,
        "max_abs_pp": report_round(max(abs(value) for value in values)) if values else None,
    }
    return output


def run_analysis(records, comparison_run_id, ai_run_id, target_area_code="13104", top_n=5,
                 expected_rows=62, coverage=None):
    coverage = coverage or {"input_municipality_count": 62, "excluded_area_codes": [], "excluded_reasons": {}}
    excluded = coverage.get("excluded_area_codes", [])
    if (expected_rows not in (61, 62) or coverage.get("input_municipality_count") != 62
            or len(set(excluded)) != len(excluded) or len(excluded) != 62 - expected_rows):
        raise ValueError("Coverage must account explicitly for all 62 input municipalities")
    if excluded and (excluded != ["13209"] or not coverage.get("excluded_reasons")):
        raise ValueError("This analysis only supports the documented Machida boundary exclusion")
    records = validate_records(records, expected_rows=expected_rows)
    if any(row["area_code"] in excluded for row in records):
        raise ValueError("An excluded municipality remains in the ML input")
    matrix = np.array([[row[feature] for feature in FEATURES] for row in records], dtype=np.float64)
    if np.any(np.var(matrix, axis=0) == 0):
        raise ValueError("A selected feature has zero variance. Review feature design before clustering")
    scaler = StandardScaler().fit(matrix)
    standardized = scaler.transform(matrix)
    evaluations, summaries, model = evaluate_clusters(standardized)
    assignments = []
    for index, row in enumerate(records):
        assignments.append({**row, "cluster_id": int(model.labels_[index]),
                            **{f"z_{feature}": float(standardized[index, column])
                               for column, feature in enumerate(FEATURES)}})
    profiles, payload_clusters = [], []
    for cluster_id in range(model.n_clusters):
        members = [row for row in assignments if row["cluster_id"] == cluster_id]
        profile = {"cluster_id": cluster_id, "member_count": len(members)}
        metrics = {}
        for definition in FEATURE_DEFINITIONS:
            feature = definition["metric"]
            values = [row[feature] for row in members]
            for aggregate, value in (("mean", np.mean(values)), ("min", min(values)), ("max", max(values))):
                profile[f"{feature}_{aggregate}"] = float(value)
            metrics[feature] = {"mean": report_round(profile[f"{feature}_mean"]),
                                "unit": definition["unit"], "period": definition["period"]}
        context = unknown_context(members)
        profile["age_unknown_context_json"] = json.dumps(context, ensure_ascii=False, allow_nan=False, sort_keys=True)
        profiles.append(profile)
        payload_clusters.append({"cluster_id": cluster_id, "member_count": len(members),
                                 "members": [{"area_code": row["area_code"], "area_name": row["area_name"]} for row in members],
                                 "metrics": metrics, "age_unknown": context})
    indices = {row["area_code"]: index for index, row in enumerate(records)}
    if target_area_code not in indices:
        raise ValueError(f"Unknown nearest-neighbor target: {target_area_code}")
    if isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n < len(records):
        raise ValueError("top_n must be an integer between 1 and municipality_count-1")
    target_index = indices[target_area_code]
    distances = np.linalg.norm(standardized - standardized[target_index], axis=1)
    order = sorted((index for index in range(len(records)) if index != target_index),
                   key=lambda index: (float(distances[index]), records[index]["area_code"]))[:top_n]
    neighbors = [{"target_area_code": target_area_code, "target_area_name": records[target_index]["area_name"],
                  "rank": rank + 1, "area_code": records[index]["area_code"], "area_name": records[index]["area_name"],
                  "cluster_id": int(model.labels_[index]), "standardized_distance": float(distances[index]),
                  **{feature: records[index][feature] for feature in FEATURES}}
                 for rank, index in enumerate(order)]
    payload = {"schema_version": "1.0", "comparison_run_id": comparison_run_id, "ai_run_id": ai_run_id,
               "period": {"from": 2020, "to": 2025}, "municipality_count": len(records),
               "selected_k": int(model.n_clusters), "aggregation": "unweighted municipality mean",
               "coverage": coverage,
               "rounding": "Cluster metric means and unknown-age context are rounded to 2 decimals. Parquet metrics retain full precision.",
               "age_unknown_context_definition": "Year means use available values in each year; change means use paired available values only. NULL is not treated as zero. Different available subsets can make the paired mean change differ from the difference of year means.",
               "feature_definitions": FEATURE_DEFINITIONS, "clusters": payload_clusters,
               "interpretation_limits": [
                   "Exploratory grouping of observed change vectors, not future prediction or causal inference.",
                   "Cluster IDs are arbitrary labels, not rankings.",
                   "Known-age denominators exclude unknown age; compare unknown-age rates alongside elderly-share change.",
                   "Nearest means similar standardized change pattern, not geographical proximity.",
                   "Each municipality has equal weight; cluster means are not pooled population or household rates.",
               ]}
    model_parameters = {"features": list(FEATURES), "scaler_mean": scaler.mean_.tolist(),
                        "scaler_scale": scaler.scale_.tolist(), "cluster_centers_standardized": model.cluster_centers_.tolist(),
                        "cluster_centers_original_units": scaler.inverse_transform(model.cluster_centers_).tolist(),
                        "selected_k": int(model.n_clusters), "final_seed": 42, "candidate_seeds": [42, 7, 21],
                        "n_init": 20, "max_iter": 300, "tol": 1e-4, "algorithm": "lloyd",
                        "selection": "Maximum mean silhouette among candidates where all seeds have minimum cluster size >=2; tie at 12 decimals chooses lower k"}
    return {"input_records": records, "source_sha256": digest(records), "assignments": assignments,
            "profiles": profiles, "evaluations": evaluations, "k_summary": summaries,
            "nearest_neighbors": neighbors, "profile_payload": payload, "model_parameters": model_parameters}


def create_plots(result, output_directory):
    """English axes and area codes avoid requiring Japanese fonts in the cluster."""
    from pathlib import Path
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    rows = result["assignments"]
    k = result["model_parameters"]["selected_k"]
    colors = plt.get_cmap("tab10")
    # Label the reference municipality only; the neighbor table supplies the five
    # names without overlapping labels in a dense scatter plot.
    targets = {result["nearest_neighbors"][0]["target_area_code"]}
    label_map = {FEATURES[0]: "Population growth 2020-2025 (%)",
                 FEATURES[1]: "Single-household share change (pp)",
                 FEATURES[2]: "Known-age 65+ share change (pp)"}
    pairs = [(FEATURES[0], FEATURES[1]), (FEATURES[0], FEATURES[2]), (FEATURES[1], FEATURES[2])]
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5), constrained_layout=True)
    for axis, (x, y) in zip(axes, pairs):
        for cluster_id in range(k):
            members = [row for row in rows if row["cluster_id"] == cluster_id]
            axis.scatter([row[x] for row in members], [row[y] for row in members],
                         color=colors(cluster_id), label=f"Cluster {cluster_id}", alpha=0.8, s=35)
        for row in rows:
            if row["area_code"] in targets:
                axis.annotate(row["area_code"], (row[x], row[y]), xytext=(4, 4), textcoords="offset points", fontsize=7)
        axis.axhline(0, color="#888888", linewidth=0.6)
        axis.axvline(0, color="#888888", linewidth=0.6)
        axis.set_xlabel(label_map[x])
        axis.set_ylabel(label_map[y])
        axis.grid(alpha=0.15)
    axes[-1].legend(fontsize=8)
    fig.suptitle(f"Observed municipality changes | n={len(rows)}, k={k} | unweighted municipalities")
    first = output_directory / "feature_changes.png"
    fig.savefig(first, dpi=160)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(10, 8), constrained_layout=True)
    for row in rows:
        x0, x1 = row["age_65plus_share_known_pct_2020"], row["age_65plus_share_known_pct_2025"]
        y0, y1 = row["single_households_pct_2020"], row["single_households_pct_2025"]
        color = colors(row["cluster_id"])
        axis.annotate("", xy=(x1, y1), xytext=(x0, y0),
                      arrowprops={"arrowstyle": "->", "color": color, "alpha": 0.6, "lw": 1.2})
        axis.scatter([x0], [y0], facecolors="none", edgecolors=[color], s=18, alpha=0.7)
        axis.scatter([x1], [y1], color=[color], s=16, alpha=0.8)
        if row["area_code"] in targets:
            axis.annotate(row["area_code"], (x1, y1), xytext=(3, 3), textcoords="offset points", fontsize=8)
    handles = [Line2D([0], [0], color=colors(i), marker="o", linestyle="", label=f"Change cluster {i}") for i in range(k)]
    axis.legend(handles=handles, fontsize=8)
    axis.set_xlabel("Known-age 65+ share (%)")
    axis.set_ylabel("Single-household share of general households (%)")
    axis.set_title(f"2020 (open) to 2025 (filled) | n={len(rows)}\nColor comes from the three-feature change model")
    axis.grid(alpha=0.2)
    second = output_directory / "share_movements.png"
    fig.savefig(second, dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    summaries = [row for row in result["k_summary"] if row["mean_silhouette"] is not None]
    for row in summaries:
        color = "#087e8b" if row["eligible"] else "#bbbbbb"
        axes[0].scatter(row["k"], row["mean_silhouette"], color=color, s=65)
        axes[1].scatter(row["k"], row["min_pairwise_ari"], color=color, s=65)
    for axis in axes:
        axis.axvline(k, color="#c04b2e", linestyle="--", label=f"Selected k={k}")
        axis.set_xlabel("Number of clusters (k)")
        axis.set_xticks(range(2, 7))
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("Mean silhouette across three seeds")
    axes[1].set_ylabel("Minimum adjusted Rand index across seed pairs")
    axes[0].legend()
    fig.suptitle("Teal: all seeds have minimum cluster size >=2; gray: excluded candidate")
    third = output_directory / "k_selection.png"
    fig.savefig(third, dpi=160)
    plt.close(fig)
    return [str(first), str(second), str(third)]
