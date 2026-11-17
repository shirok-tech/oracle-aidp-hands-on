SELECT area_code, area_name, cluster_id,
       population_2020, population_2025,
       ROUND(population_growth_pct, 2) AS population_growth_pct,
       comparison_run_id
FROM blog_catalog.opendata.census_agent_areas_v1 AS a
ORDER BY a.population_growth_pct DESC, a.area_code
LIMIT 5
