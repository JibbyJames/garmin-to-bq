import datetime
import json
from main import init_api

api = init_api()
if api:
    for i in range(30):
        date_str = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        try:
            hrv_data = api.get_hrv_data(date_str)
            if hrv_data is not None:
                print(f"FOUND HRV DATA for {date_str}:", json.dumps(hrv_data))
                break
        except Exception as e:
            pass
