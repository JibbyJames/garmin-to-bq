# Testing Cloud Function

import os
import sys
import json
from unittest.mock import MagicMock

# Mock environment variables for Cloud Function
os.environ['K_SERVICE'] = 'garmin-to-bq'
os.environ['FUNCTION_TARGET'] = 'cloud_function_entry'

# Import the function to test from the parent directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import cloud_function_entry

# Mock request object
request = MagicMock()
request.get_json.return_value = None

# Run the function
cloud_function_entry(request)