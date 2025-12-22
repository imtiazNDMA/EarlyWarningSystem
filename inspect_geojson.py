import json

file_path = (
    r"g:\AI Projects\projects\earlyWarnings\static\boundary\pakistan_districts_fixed.geojson"
)
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

provinces = set()
for feature in data["features"]:
    props = feature["properties"]
    p = props.get("Province") or props.get("PROVINCE")
    if p:
        provinces.add(p)

print(f"Unique provinces in fixed GeoJSON: {provinces}")
print(f"Total features: {len(data['features'])}")

# Print keys of the first feature
if data["features"]:
    print(f"Keys: {list(data['features'][0]['properties'].keys())}")
