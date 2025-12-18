import json

with open("static/boundary/district.geojson", "r", encoding="utf-8") as f:
    data = json.load(f)
    if "features" in data and len(data["features"]) > 0:
        print("Properties of first feature:")
        print(data["features"][0]["properties"])
    else:
        print("No features found")
