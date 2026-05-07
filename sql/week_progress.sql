WITH constants AS (
  -- Dynamically calculates the most recent Monday at 00:00:00
  SELECT TIMESTAMP(DATETIME_TRUNC(CURRENT_DATETIME(), WEEK(MONDAY))) AS start_of_week
)
SELECT
  goal.goal_name,
  goal.progress,
  goal.target,
  goal.last_recorded,
  ROUND(SAFE_DIVIDE(goal.progress, goal.target), 4) AS percentage
FROM (
  -- 90 Vigorous Minutes (Cardio)
  SELECT
    'Cardio' AS goal_name,
    COALESCE(SUM(`Vigorous Intensity _min_`), 0) AS progress,
    90 AS target,
    MAX(CASE WHEN `Vigorous Intensity _min_` > 0 THEN `Start Time` END) AS last_recorded
  FROM `james-gcp-project.garmin.activity`, constants
  WHERE `Start Time` >= constants.start_of_week
    -- Exclude Martial Arts (Sauna) by Name
    AND (LOWER(`Activity Name`) != 'martial arts' OR `Activity Name` IS NULL)
    -- Exclude Strength Training by Type
    AND (LOWER(`Activity Type`) != 'strength_training' OR `Activity Type` IS NULL)

  UNION ALL

  -- 60 Minutes of "Sauna" (Martial Arts)
  SELECT
    'Sauna' AS goal_name,
    COALESCE(SUM(CASE WHEN LOWER(`Activity Name`) = 'martial arts' THEN `Duration _s_` / 60.0 ELSE 0 END), 0) AS progress,
    60 AS target,
    MAX(CASE WHEN LOWER(`Activity Name`) = 'martial arts' THEN `Start Time` END) AS last_recorded
  FROM `james-gcp-project.garmin.activity`, constants
  WHERE `Start Time` >= constants.start_of_week

  UNION ALL

  -- 3 Pilates Activities (Flexibility)
  SELECT
    'Flexibility' AS goal_name,
    CAST(COUNTIF(LOWER(`Activity Type`) = 'pilates') AS FLOAT64) AS progress,
    3 AS target,
    MAX(CASE WHEN LOWER(`Activity Type`) = 'pilates' THEN `Start Time` END) AS last_recorded
  FROM `james-gcp-project.garmin.activity`, constants
  WHERE `Start Time` >= constants.start_of_week

  UNION ALL

  -- 3 Strength Activities (Strength)
  SELECT
    'Strength' AS goal_name,
    CAST(COUNTIF(LOWER(`Activity Type`) = 'strength_training') AS FLOAT64) AS progress,
    3 AS target,
    MAX(CASE WHEN LOWER(`Activity Type`) = 'strength_training' THEN `Start Time` END) AS last_recorded
  FROM `james-gcp-project.garmin.activity`, constants
  WHERE `Start Time` >= constants.start_of_week
) AS goal
ORDER BY goal.goal_name;