import json
import os
import sys

# Add project root to path to import models
sys.path.append(r"g:\AI Projects\projects\earlyWarnings")
from models import PROVINCES

file_path = (
    r"g:\AI Projects\projects\earlyWarnings\static\boundary\pakistan_districts_fixed.geojson"
)
with open(file_path, "r", encoding="utf-8") as f:
    geojson_data = json.load(f)

# Extract all district names from GeoJSON
geojson_districts = set()
for feature in geojson_data["features"]:
    props = feature["properties"]
    name = (
        props.get("District")
        or props.get("DISTRICT")
        or props.get("districts")
        or props.get("NAME_2")
    )
    if name:
        geojson_districts.add(name.upper())

# Compare with models.py
mismatches = {}
for province, districts in PROVINCES.items():
    province_mismatches = []
    for district in districts:
        if district.upper() not in geojson_districts:
            province_mismatches.append(district)
    if province_mismatches:
        mismatches[province] = province_mismatches

with open("all_mismatches.txt", "w") as out:
    out.write("Districts in models.py NOT found in GeoJSON:\n")
    for province, mdists in mismatches.items():
        out.write(f"\n[{province}]\n")
        for d in mdists:
            out.write(f"  - {d}\n")

print(f"Comparison complete. Found mismatches in {len(mismatches)} provinces.")
print("Check all_mismatches.txt for details.")
