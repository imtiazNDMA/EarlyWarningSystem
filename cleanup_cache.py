import glob
import json
import os

def cleanup_cache():
    files = glob.glob("static/weatherdata/weather_*.json")
    deleted = 0
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as rf:
                data = json.load(rf)
                if "current_weather" not in data:
                    print(f"Deleting incomplete cache: {f}")
                    os.remove(f)
                    deleted += 1
        except Exception as e:
            print(f"Error processing {f}: {e}")
            os.remove(f)
            deleted += 1
    print(f"Deleted {deleted} incomplete cache files.")

if __name__ == "__main__":
    cleanup_cache()
