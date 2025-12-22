import json
import sys

sys.path.append(r"g:\AI Projects\projects\earlyWarnings")
from models import PROVINCES
from services.map_service import MapService

# Initialize MapService to get access to the aliases
map_service = MapService()

# Load the GeoJSON
file_path = (
    r"g:\AI Projects\projects\earlyWarnings\static\boundary\pakistan_districts_fixed.geojson"
)
with open(file_path, "r", encoding="utf-8") as f:
    geojson_data = json.load(f)

# Extract all district names from GeoJSON
geojson_districts = {}
for feature in geojson_data["features"]:
    props = feature["properties"]
    name = props.get("District") or props.get("DISTRICT")
    province = props.get("Province") or props.get("PROVINCE")
    if name:
        geojson_districts[name.upper().replace("_", " ").replace(" ", "_")] = (name, province)

# Test the mapping
all_missing = []
for province, districts in PROVINCES.items():
    for district in districts:
        # Apply the same normalization as map_service.py
        normalized = map_service._district_aliases.get(district, district)
        normalized = normalized.replace(" ", "_").upper()

        if normalized not in geojson_districts:
            all_missing.append(f"{province}: {district} -> {normalized}")

with open("still_missing.txt", "w") as f:
    if all_missing:
        f.write("Still missing:\n")
        for m in all_missing:
            f.write(m + "\n")
    else:
        f.write("ALL GOOD!\n")

print(f"Found {len(all_missing)} still missing. Check still_missing.txt")
