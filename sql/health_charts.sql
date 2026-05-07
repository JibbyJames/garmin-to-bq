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
daily AS (
  SELECT Date AS date, metric, AVG(value) AS value, 'day' AS agg_type
  FROM metrics_raw
  GROUP BY 1, 2
),
weekly AS (
  SELECT DATE_TRUNC(Date, ISOWEEK) AS date, metric, AVG(value) AS value, 'week' AS agg_type
  FROM metrics_raw
  GROUP BY 1, 2
),
monthly AS (
  SELECT DATE_TRUNC(Date, MONTH) AS date, metric, AVG(value) AS value, 'month' AS agg_type
  FROM metrics_raw
  GROUP BY 1, 2
)
SELECT date, metric, ROUND(value, 2) AS value, agg_type FROM daily
UNION ALL SELECT date, metric, ROUND(value, 2) AS value, agg_type FROM weekly
UNION ALL SELECT date, metric, ROUND(value, 2) AS value, agg_type FROM monthly
ORDER BY date DESC;
