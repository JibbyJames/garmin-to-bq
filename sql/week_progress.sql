SELECT
  goal.goal_name,
  goal.progress,
  goal.target,
  goal.last_recorded,
  ROUND(SAFE_DIVIDE(goal.progress, goal.target), 4) AS percentage
FROM (
  -- 90 Vigorous Minutes
  SELECT
    'Cardio' AS goal_name,
    COALESCE(SUM(activities.VigorousIntensityMinutes), 0) AS progress,
    90 AS target,
    MAX(CASE WHEN activities.VigorousIntensityMinutes > 0 THEN activities.StartTime END) AS last_recorded
  FROM `james-gcp-project.garmin.activities` AS activities
  WHERE activities.StartTime >= DATETIME_TRUNC(CURRENT_DATETIME(), WEEK(MONDAY))
    AND LOWER(activities.ActivityName) != 'martial arts'

  UNION ALL

  -- 60 Minutes of "Sauna" (recorded as Martial Arts)
  SELECT
    'Sauna' AS goal_name,
    COALESCE(SUM(CASE WHEN LOWER(activities.ActivityName) = 'martial arts' THEN activities.DurationMin ELSE 0 END), 0) AS progress,
    60 AS target,
    MAX(CASE WHEN LOWER(activities.ActivityName) = 'martial arts' THEN activities.StartTime END) AS last_recorded
  FROM `james-gcp-project.garmin.activities` AS activities
  WHERE activities.StartTime >= DATETIME_TRUNC(CURRENT_DATETIME(), WEEK(MONDAY))

  UNION ALL

  -- 3 Pilates Activities
  SELECT
    'Flexibility' AS goal_name,
    CAST(COUNTIF(LOWER(activities.ActivityType) = 'pilates') AS FLOAT64) AS progress,
    3 AS target,
    MAX(CASE WHEN LOWER(activities.ActivityType) = 'pilates' THEN activities.StartTime END) AS last_recorded
  FROM `james-gcp-project.garmin.activities` AS activities
  WHERE activities.StartTime >= DATETIME_TRUNC(CURRENT_DATETIME(), WEEK(MONDAY))

  UNION ALL

  -- 3 Strength Activities
  SELECT
    'Strength' AS goal_name,
    CAST(COUNTIF(LOWER(activities.ActivityType) = 'strength_training') AS FLOAT64) AS progress,
    3 AS target,
    MAX(CASE WHEN LOWER(activities.ActivityType) = 'strength_training' THEN activities.StartTime END) AS last_recorded
  FROM `james-gcp-project.garmin.activities` AS activities
  WHERE activities.StartTime >= DATETIME_TRUNC(CURRENT_DATETIME(), WEEK(MONDAY))
) AS goal
ORDER BY goal.goal_name;