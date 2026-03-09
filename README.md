# Garmin to BigQuery (garmin-to-bq)

This script is designed to extract daily health metrics from Garmin Connect. It focuses on gathering critical user data such as:

- Resting Heart Rate (RHR)
- Body Fat %
- VO2 Max (Precise Value)
- Fitness Age
- "Youth Bonus" (Chronological Age - Fitness Age)
- Sleep Score

## Inspiration & References

The extraction logic uses the excellent [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) library. 

Many of the precise metric extractions (like VO2 Max, Sleep Score, and Body Composition) were modeled directly from the library's primary [demo.py file](https://github.com/cyberjunky/python-garminconnect/blob/master/demo.py).
