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

# Collect all district names from GeoJSON along with their property keys
geojson_info = []
for feature in geojson_data["features"]:
    props = feature["properties"]
    geojson_info.append(props)

mismatches = [
    "Dera Ghazi Khan",
    "Layyah",
    "Mandi Bahauddin",
    "Nankana Sahib",
    "Rahim Yar Khan",
    "Toba Tek Singh",
    "Karachi Central",
    "Karachi East",
    "Karachi South",
    "Karachi West",
    "Korangi",
    "Malir",
    "Mirpurkhas",
    "Naushahro Feroze",
    "Qambar Shahdadkot",
    "Shaheed Benazirabad",
    "Tando Allahyar",
    "Tando Muhammad Khan",
    "Umerkot",
    "Allai",
    "Battagram",
    "Central Dir",
    "Dera Ismail Khan",
    "Kolai-Palas",
    "Lakki Marwat",
    "Lower Chitral",
    "Lower Dir",
    "Lower Kohistan",
    "Lower South Waziristan",
    "North Waziristan",
    "Tor Ghar",
    "Upper South Waziristan",
    "Upper Chitral",
    "Upper Dir",
    "Upper Kohistan",
    "Hattian Bala",
    "Diamer",
    "Roundu",
]


def fuzzy_find(name):
    name_upper = name.upper().replace(" ", "").replace("-", "")
    matches = []
    for info in geojson_info:
        for val in info.values():
            if isinstance(val, str):
                val_clean = val.upper().replace(" ", "").replace("-", "").replace("_", "")
                if name_upper in val_clean or val_clean in name_upper:
                    matches.append(info)
                    break
    return matches


with open("fuzzy_matches.txt", "w") as out:
    for m in mismatches:
        found = fuzzy_find(m)
        out.write(f"Search for '{m}':\n")
        if found:
            for f in found:
                out.write(f"  Match: {f}\n")
        else:
            out.write("  NO MATCH FOUND\n")
        out.write("-" * 50 + "\n")

print("Fuzzy search complete. Check fuzzy_matches.txt")
