WITH constants AS (
  SELECT
    DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY)) AS start_of_this_week,
    DATE_SUB(DATE_TRUNC(CURRENT_DATE(), WEEK(MONDAY)), INTERVAL 104 WEEK) AS start_of_period
),
weeks AS (
  SELECT week_start
  FROM UNNEST(GENERATE_DATE_ARRAY(
    (SELECT start_of_period FROM constants),
    (SELECT start_of_this_week FROM constants),
    INTERVAL 1 WEEK
  )) AS week_start
),
activity_agg AS (
  SELECT
    DATE(TIMESTAMP_TRUNC(activity.`Start Time`, WEEK(MONDAY))) AS week_start,
    COALESCE(SUM(CASE WHEN (LOWER(activity.`Activity Name`) != 'martial arts' OR activity.`Activity Name` IS NULL) AND (LOWER(`Activity Type`) != 'strength_training' OR `Activity Type` IS NULL) THEN activity.`Vigorous Intensity _min_` ELSE 0 END), 0) AS cardio_raw,
    COALESCE(SUM(CASE WHEN LOWER(activity.`Activity Name`) = 'martial arts' THEN activity.`Duration _s_` / 60.0 ELSE 0 END), 0) AS sauna_raw,
    COALESCE(COUNTIF(LOWER(activity.`Activity Type`) = 'pilates'), 0) AS flexibility_raw,
    COALESCE(COUNTIF(LOWER(activity.`Activity Type`) = 'strength_training'), 0) AS strength_raw
  FROM `james-gcp-project.garmin.activity` AS activity
  WHERE DATE(activity.`Start Time`) >= (SELECT start_of_period FROM constants)
  GROUP BY 1
),
calculated_pcts AS (
  SELECT
    weeks.week_start,
    ROUND(SAFE_DIVIDE(COALESCE(activity_agg.cardio_raw, 0), 90), 4) AS cardio_pct,
    ROUND(SAFE_DIVIDE(COALESCE(activity_agg.sauna_raw, 0), 60), 4) AS sauna_pct,
    ROUND(SAFE_DIVIDE(COALESCE(activity_agg.flexibility_raw, 0), 3), 4) AS flexibility_pct,
    ROUND(SAFE_DIVIDE(COALESCE(activity_agg.strength_raw, 0), 3), 4) AS strength_pct
  FROM weeks
  LEFT JOIN activity_agg ON weeks.week_start = activity_agg.week_start
)
SELECT
  *,
  -- Proportional weighting logic: 
  -- Each exercise is capped at 1.0 (100%) and then multiplied by 0.25 (its maximum contribution).
  ROUND(
    (LEAST(cardio_pct, 1.0) * 0.25) +
    (LEAST(sauna_pct, 1.0) * 0.25) +
    (LEAST(flexibility_pct, 1.0) * 0.25) +
    (LEAST(strength_pct, 1.0) * 0.25)
  , 4) AS total_completion_pct
FROM calculated_pcts
ORDER BY week_start DESC;