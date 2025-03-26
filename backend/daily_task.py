# daily_task.py
from app import fetchRecommendations
import requests

# Replace with the actual endpoint of your Flask app
endpoint = "http://127.0.0.1:5000/fetch-recs"

data = {
    "email": "rishabk2004@gmail.com"
}

try:
    response = requests.post(endpoint, json=data)
    print(response.json())  # or log it
except Exception as e:
    print(f"Error during cron task: {e}")
'''
{
  "AMZN": {
    "rating": "Buy",
    "indicator": 0.68
  },
  "NVDA": {
    "rating": "Hold",
    "indicator": 0.59
  },
  ...
}
'''