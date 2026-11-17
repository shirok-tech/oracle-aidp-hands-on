SELECT cluster_id, COUNT(*) AS member_count,
       ROUND(AVG(population_growth_pct), 2) AS mean_population_growth_pct,
       ROUND(AVG(single_share_change_pp), 2) AS mean_single_share_change_pp,
       ROUND(AVG(elderly_share_change_pp), 2) AS mean_elderly_share_change_pp,
       COUNT(age_unknown_change_pp) AS age_unknown_change_available_count,
       COUNT(*) - COUNT(age_unknown_change_pp) AS age_unknown_change_null_count,
       ROUND(AVG(age_unknown_change_pp), 2) AS mean_age_unknown_change_pp,
       ROUND(MAX(ABS(age_unknown_change_pp)), 2) AS max_abs_age_unknown_change_pp,
       comparison_run_id, ai_run_id
FROM blog_catalog.opendata.census_agent_areas_v1
GROUP BY cluster_id, comparison_run_id, ai_run_id
ORDER BY cluster_id
