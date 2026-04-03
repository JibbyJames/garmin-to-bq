WITH stats_with_periods AS (
  SELECT
    *,
    CASE
      WHEN Date > DATE_SUB(CURRENT_DATE(), INTERVAL 42 DAY) THEN 'Current' # Previous six weeks
      WHEN Date > DATE_SUB(CURRENT_DATE(), INTERVAL 84 DAY) THEN 'Previous' # Six weeks before that
    END AS period
  FROM `james-gcp-project.garmin.daily_stats`
  WHERE Date > DATE_SUB(CURRENT_DATE(), INTERVAL 84 DAY)
),
metrics_unpivoted AS (
  SELECT period, Date, 'VO2 Max' AS metric, VO2Max AS value FROM stats_with_periods
  UNION ALL
  SELECT period, Date, 'Body Fat %' AS metric, BodyFat AS value FROM stats_with_periods
  UNION ALL
  SELECT period, Date, 'Resting Heart Rate' AS metric, CAST(RestingHeartRate AS FLOAT64) AS value FROM stats_with_periods
  UNION ALL
  SELECT period, Date, 'Youth Bonus' AS metric, YouthBonus AS value FROM stats_with_periods
  UNION ALL
  SELECT period, Date, 'Stress' AS metric, CAST(AverageStress AS FLOAT64) AS value FROM stats_with_periods
  UNION ALL
  SELECT period, Date, 'Sleep Score' AS metric, CAST(SleepScore AS FLOAT64) AS value FROM stats_with_periods
),
aggregated_metrics AS (
  SELECT
    metric,
    period,
    AVG(value) AS avg_val,
    MIN(value) AS min_val,
    MAX(value) AS max_val,
    ARRAY_AGG(value IGNORE NULLS ORDER BY Date DESC LIMIT 1)[SAFE_OFFSET(0)] AS latest_val,
    MAX(CASE WHEN value IS NOT NULL THEN Date END) AS latest_date,
    COUNT(value) AS record_count,
    ROUND(COUNT(value) / 42.0 * 100, 2) AS record_pct
  FROM metrics_unpivoted
  WHERE period IS NOT NULL
  GROUP BY metric, period
)
SELECT
  curr.metric,
  -- Averages
  ROUND(curr.avg_val, 2) AS current_avg,
  ROUND(prev.avg_val, 2) AS previous_avg,
  ROUND(SAFE_DIVIDE(curr.avg_val - prev.avg_val, prev.avg_val) * 100, 2) AS pct_diff_avg,
  
  -- Min Values
  ROUND(curr.min_val, 2) AS current_min,
  ROUND(prev.min_val, 2) AS previous_min,
  ROUND(SAFE_DIVIDE(curr.min_val - prev.min_val, prev.min_val) * 100, 2) AS pct_diff_min,
  
  -- Max Values
  ROUND(curr.max_val, 2) AS current_max,
  ROUND(prev.max_val, 2) AS previous_max,
  ROUND(SAFE_DIVIDE(curr.max_val - prev.max_val, prev.max_val) * 100, 2) AS pct_diff_max,
  
  -- Metadata & Latest
  curr.latest_date AS current_latest_date,
  ROUND(curr.latest_val, 2) AS current_latest,
  curr.record_count AS current_record_count,
  curr.record_pct AS current_record_pct,
  prev.record_count AS previous_record_count,
  prev.record_pct AS previous_record_pct
FROM aggregated_metrics AS curr
LEFT JOIN aggregated_metrics AS prev
  ON curr.metric = prev.metric AND prev.period = 'Previous'
WHERE curr.period = 'Current'
ORDER BY curr.metric;