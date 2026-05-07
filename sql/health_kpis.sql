WITH metrics_raw AS (
  -- VO2 Max from the dedicated table
  SELECT 
    Date, 
    'VO2 Max' AS metric, 
    VO2max AS value 
  FROM `james-gcp-project.garmin.vo2max`
  WHERE VO2max IS NOT NULL
  UNION ALL
  -- VO2 Max from activities
  SELECT 
    DATE(`Start Time`) AS Date, 
    'VO2 Max' AS metric, 
    VO2max AS value 
  FROM `james-gcp-project.garmin.activity`
  WHERE VO2max IS NOT NULL
  UNION ALL
  -- Sleep Score
  SELECT 
    Date, 
    'Sleep Score' AS metric, 
    CAST(sleep_score AS FLOAT64) AS value 
  FROM `james-gcp-project.garmin.sleep`
  WHERE sleep_score IS NOT NULL
  UNION ALL
  -- Body Fat %
  SELECT 
    Date, 
    'Body Fat %' AS metric, 
    `Body Fat _%_` AS value 
  FROM `james-gcp-project.garmin.weight`
  WHERE `Body Fat _%_` IS NOT NULL
  UNION ALL
  -- Resting Heart Rate
  SELECT 
    Date, 
    'Resting Heart Rate' AS metric, 
    CAST(`Resting HR _bpm_` AS FLOAT64) AS value 
  FROM `james-gcp-project.garmin.heart_rate`
  WHERE `Resting HR _bpm_` IS NOT NULL
  UNION ALL
  -- Youth Bonus
  SELECT 
    Date, 
    'Youth Bonus' AS metric, 
    CAST(`Chronological Age` - `Fitness Age` AS FLOAT64) AS value 
  FROM `james-gcp-project.garmin.fitness_age`
  WHERE `Chronological Age` IS NOT NULL AND `Fitness Age` IS NOT NULL
  UNION ALL
  -- Stress
  SELECT 
    Date, 
    'Stress' AS metric, 
    CAST(`Avg Stress` AS FLOAT64) AS value 
  FROM `james-gcp-project.garmin.daily_summary`
  WHERE `Avg Stress` IS NOT NULL
),
stats_with_periods AS (
  SELECT
    *,
    CASE
      WHEN Date > DATE_SUB(CURRENT_DATE, INTERVAL 42 DAY) THEN 'Current'
      WHEN Date > DATE_SUB(CURRENT_DATE, INTERVAL 84 DAY) THEN 'Previous'
    END AS period
  FROM metrics_raw
  WHERE Date > DATE_SUB(CURRENT_DATE, INTERVAL 84 DAY)
),
aggregated_metrics AS (
  SELECT
    metric,
    period,
    AVG(value) AS avg_val,
    -- 1) 7 Day Average Calculation
    AVG(CASE WHEN Date > DATE_SUB(CURRENT_DATE, INTERVAL 7 DAY) THEN value END) AS avg_7d,
    MIN(value) AS min_val,
    MAX(value) AS max_val,
    ARRAY_AGG(value IGNORE NULLS ORDER BY Date DESC LIMIT 1)[SAFE_OFFSET(0)] AS latest_val,
    MAX(CASE WHEN value IS NOT NULL THEN Date END) AS latest_date,
    COUNT(value) AS record_count,
    ROUND(COUNT(value) / 42.0 * 100, 2) AS record_pct
  FROM stats_with_periods
  WHERE period IS NOT NULL
  GROUP BY metric, period
)
SELECT
  curr.metric,
  -- Averages
  ROUND(curr.avg_val, 2) AS current_6w_avg,
  ROUND(prev.avg_val, 2) AS previous_6w_avg,
  ROUND(SAFE_DIVIDE(curr.avg_val - prev.avg_val, prev.avg_val) * 100, 2) AS pct_diff_avg_6w,
  
  -- New Metrics
  ROUND(curr.avg_7d, 2) AS avg_7d,
  -- 2) 7 day average vs 6 week average diff
  ROUND(SAFE_DIVIDE(curr.avg_7d - curr.avg_val, curr.avg_val) * 100, 2) AS pct_diff_7d_vs_6w,
  -- 3) Latest vs 6 week average
  ROUND(SAFE_DIVIDE(curr.latest_val - curr.avg_val, curr.avg_val) * 100, 2) AS pct_diff_latest_vs_6w,

  -- Min/Max Values
  ROUND(curr.min_val, 2) AS current_min,
  ROUND(curr.max_val, 2) AS current_max,
  
  -- Metadata & Latest
  curr.latest_date AS latest_date,
  ROUND(curr.latest_val, 2) AS latest_val,
  curr.record_count AS current_6w_record_count,
  curr.record_pct AS current_6w_record_pct
FROM aggregated_metrics AS curr
LEFT JOIN aggregated_metrics AS prev
  ON curr.metric = prev.metric AND prev.period = 'Previous'
WHERE curr.period = 'Current'
ORDER BY curr.metric;