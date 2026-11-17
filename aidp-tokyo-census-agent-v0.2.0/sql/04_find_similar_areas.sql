SELECT source_area_code, source_area_name, neighbor_rank,
       neighbor_area_code, neighbor_area_name, neighbor_cluster_id,
       ROUND(distance_standardized, 6) AS distance_standardized,
       ROUND(population_growth_pct, 2) AS population_growth_pct,
       ROUND(single_share_change_pp, 2) AS single_share_change_pp,
       ROUND(elderly_share_change_pp, 2) AS elderly_share_change_pp,
       ROUND(age_unknown_pct_2020, 2) AS age_unknown_pct_2020,
       ROUND(age_unknown_pct_2025, 2) AS age_unknown_pct_2025,
       ROUND(age_unknown_change_pp, 2) AS age_unknown_change_pp,
       comparison_run_id, ai_run_id
FROM blog_catalog.opendata.census_agent_neighbors_v1
WHERE source_area_code = {{area_code}}
ORDER BY neighbor_rank
