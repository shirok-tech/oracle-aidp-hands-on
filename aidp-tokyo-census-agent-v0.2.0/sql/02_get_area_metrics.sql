SELECT area_code, area_name, cluster_id,
       population_2020, population_2025,
       ROUND(population_growth_pct, 2) AS population_growth_pct,
       ROUND(single_households_pct_2020, 2) AS single_households_pct_2020,
       ROUND(single_households_pct_2025, 2) AS single_households_pct_2025,
       ROUND(single_share_change_pp, 2) AS single_share_change_pp,
       ROUND(age_65plus_share_known_pct_2020, 2) AS age_65plus_share_known_pct_2020,
       ROUND(age_65plus_share_known_pct_2025, 2) AS age_65plus_share_known_pct_2025,
       ROUND(elderly_share_change_pp, 2) AS elderly_share_change_pp,
       ROUND(age_unknown_pct_2020, 2) AS age_unknown_pct_2020,
       ROUND(age_unknown_pct_2025, 2) AS age_unknown_pct_2025,
       ROUND(age_unknown_change_pp, 2) AS age_unknown_change_pp,
       comparison_run_id, ai_run_id
FROM blog_catalog.opendata.census_agent_areas_v1
WHERE area_code = {{area_code}}
