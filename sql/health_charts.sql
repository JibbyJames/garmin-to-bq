WITH metrics_raw AS (
  -- VO2 Max from the dedicated table
  SELECT Date, 'VO2 Max' AS metric, NULLIF(VO2max, 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.vo2max`
  WHERE VO2max IS NOT NULL
  UNION ALL
  -- VO2 Max from activities
  SELECT DATE(`Start Time`) AS Date, 'VO2 Max' AS metric, NULLIF(VO2max, 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.activity`
  WHERE VO2max IS NOT NULL
  UNION ALL
  -- Sleep Score
  SELECT Date, 'Sleep Score' AS metric, NULLIF(CAST(sleep_score AS FLOAT64), 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.sleep`
  WHERE sleep_score IS NOT NULL
  UNION ALL
  -- Body Fat %
  SELECT Date, 'Body Fat %' AS metric, NULLIF(`Body Fat _%_`, 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.weight`
  WHERE NULLIF(`Body Fat _%_`, 0) IS NOT NULL
  UNION ALL
  -- Resting Heart Rate
  SELECT Date, 'Resting Heart Rate' AS metric, NULLIF(CAST(`Resting HR _bpm_` AS FLOAT64), 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.heart_rate`
  WHERE `Resting HR _bpm_` IS NOT NULL
  UNION ALL
  -- Youth Bonus
  SELECT Date, 'Youth Bonus' AS metric, CAST(`Chronological Age` - `Fitness Age` AS FLOAT64) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.fitness_age`
  WHERE `Chronological Age` IS NOT NULL AND `Fitness Age` IS NOT NULL
  UNION ALL
  -- Stress
  SELECT Date, 'Stress' AS metric, NULLIF(CAST(`Avg Stress` AS FLOAT64), 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.daily_summary`
  WHERE `Avg Stress` IS NOT NULL

  UNION ALL

  -- Cardio (Vigorous Intensity min)
  SELECT DATE(`Start Time`) as Date, 'Cardio' as metric, CAST(`Vigorous Intensity _min_` as FLOAT64) as value, 'SUM' as agg_method 
  FROM `james-gcp-project.garmin.activity` 
  WHERE `Vigorous Intensity _min_` > 0
    AND (LOWER(`Activity Name`) != 'martial arts' OR `Activity Name` IS NULL)
    AND (LOWER(`Activity Type`) != 'strength_training' OR `Activity Type` IS NULL)

  UNION ALL

  -- Sauna
  SELECT DATE(`Start Time`) as Date, 'Sauna' as metric, CAST(`Duration _s_` / 60.0 as FLOAT64) as value, 'SUM' as agg_method 
  FROM `james-gcp-project.garmin.activity` 
  WHERE LOWER(`Activity Name`) = 'martial arts'

  UNION ALL

  -- Flexibility
  SELECT DATE(`Start Time`) as Date, 'Flexibility' as metric, 1.0 as value, 'SUM' as agg_method 
  FROM `james-gcp-project.garmin.activity` 
  WHERE LOWER(`Activity Type`) = 'pilates'

  UNION ALL

  -- Strength
  SELECT DATE(`Start Time`) as Date, 'Strength' as metric, 1.0 as value, 'SUM' as agg_method 
  FROM `james-gcp-project.garmin.activity` 
  WHERE LOWER(`Activity Type`) = 'strength_training'

  UNION ALL

  -- Nutrition Metrics
  SELECT Date, 'Calories' AS metric, NULLIF(CAST(Calories AS FLOAT64), 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.nutrition_summary`
  WHERE Calories IS NOT NULL
  UNION ALL
  SELECT Date, 'Fat' AS metric, NULLIF(Fat, 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.nutrition_summary`
  WHERE Fat IS NOT NULL
  UNION ALL
  SELECT Date, 'Protein' AS metric, NULLIF(Protein, 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.nutrition_summary`
  WHERE Protein IS NOT NULL
  UNION ALL
  SELECT Date, 'Carbs' AS metric, NULLIF(Carbs, 0) AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.nutrition_summary`
  WHERE Carbs IS NOT NULL

  UNION ALL

  -- Weight Metrics (Grams to KG conversion)
  SELECT Date, 'Weight' AS metric, `Weight _kg_` / 1000.0 AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.weight`
  WHERE `Weight _kg_` IS NOT NULL AND NULLIF(`Body Fat _%_`, 0) IS NOT NULL
  UNION ALL
  SELECT Date, 'Fat Mass' AS metric, (`Weight _kg_` * `Body Fat _%_` / 100.0) / 1000.0 AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.weight`
  WHERE `Weight _kg_` IS NOT NULL AND NULLIF(`Body Fat _%_`, 0) IS NOT NULL
  UNION ALL
  SELECT Date, 'Muscle Mass' AS metric, `Muscle Mass _kg_` / 1000.0 AS value, 'AVG' AS agg_method
  FROM `james-gcp-project.garmin.weight`
  WHERE `Muscle Mass _kg_` IS NOT NULL AND NULLIF(`Body Fat _%_`, 0) IS NOT NULL
),
daily AS (
  SELECT Date AS date, metric, 
         CASE WHEN agg_method = 'SUM' THEN SUM(value) ELSE AVG(value) END AS value, 
         'day' AS agg_type
  FROM metrics_raw
  GROUP BY 1, 2, agg_method
),
weekly AS (
  SELECT DATE_TRUNC(Date, ISOWEEK) AS date, metric, 
         CASE WHEN agg_method = 'SUM' THEN SUM(value) ELSE AVG(value) END AS value, 
         'week' AS agg_type
  FROM metrics_raw
  GROUP BY 1, 2, agg_method
),
monthly AS (
  SELECT DATE_TRUNC(Date, MONTH) AS date, metric, 
         CASE WHEN agg_method = 'SUM' THEN SUM(value) ELSE AVG(value) END AS value, 
         'month' AS agg_type
  FROM metrics_raw
  GROUP BY 1, 2, agg_method
)
SELECT date, metric, ROUND(value, 2) AS value, agg_type FROM daily
UNION ALL SELECT date, metric, ROUND(value, 2) AS value, agg_type FROM weekly
UNION ALL SELECT date, metric, ROUND(value, 2) AS value, agg_type FROM monthly
ORDER BY date DESC, metric ASC;