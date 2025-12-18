import requests
import json

def debug_bulk():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": [33.6844, 31.5204],
        "longitude": [73.0479, 74.3587],
        "daily": ["temperature_2m_max", "temperature_2m_min"],
        "current_weather": "true",
        "timezone": "auto"
    }
    
    print("Sending bulk request...")
    response = requests.get(url, params=params)
    data = response.json()
    
    print(f"Response type: {type(data)}")
    
    if isinstance(data, list):
        for i, item in enumerate(data):
            print(f"Item {i} keys: {list(item.keys())}")
            if "current_weather" in item:
                print(f"Item {i} current_weather: {item['current_weather']}")
            else:
                print(f"Item {i} MISSING current_weather")
    elif isinstance(data, dict):
        print(f"Dict keys: {list(data.keys())}")
        if "current_weather" in data:
            print(f"Dict current_weather: {data['current_weather']}")
        else:
            print("Dict MISSING current_weather")

if __name__ == "__main__":
    debug_bulk()
