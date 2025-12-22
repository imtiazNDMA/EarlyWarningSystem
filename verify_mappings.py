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
print("Testing district name normalization:\n")
print("=" * 80)

all_good = True
for province, districts in PROVINCES.items():
    mismatches_in_province = []
    for district in districts:
        # Apply the same normalization as map_service.py
        normalized = map_service._district_aliases.get(district, district)
        normalized = normalized.replace(" ", "_").upper()

        if normalized not in geojson_districts:
            mismatches_in_province.append(f"  ❌ {district} -> {normalized} NOT FOUND")
            all_good = False
        else:
            geojson_name, geojson_prov = geojson_districts[normalized]
            if district in map_service._district_aliases:
                mismatches_in_province.append(
                    f"  ✓ {district} -> {normalized} (mapped from {district})"
                )

    if mismatches_in_province:
        print(f"\n[{province}]")
        for m in mismatches_in_province:
            print(m)

print("\n" + "=" * 80)
if all_good:
    print("✅ ALL DISTRICTS CAN BE MAPPED SUCCESSFULLY!")
else:
    print("⚠️  Some districts still have issues")
