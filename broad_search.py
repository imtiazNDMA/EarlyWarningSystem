import json

file_path = (
    r"g:\AI Projects\projects\earlyWarnings\static\boundary\pakistan_districts_fixed.geojson"
)
with open(file_path, "r", encoding="utf-8") as f:
    geojson_data = json.load(f)

search_terms = [
    "KARACHI",
    "DIR",
    "CHITRAL",
    "KOHISTAN",
    "WAZIRISTAN",
    "KHAN",
    "DERA",
    "LAYYAH",
    "SHAH",
    "FEROZE",
    "AZAD",
    "KASHMIR",
    "BALA",
    "HATTIAN",
    "DIAM",
]

results = []
for feature in geojson_data["features"]:
    props = feature["properties"]
    for val in props.values():
        if isinstance(val, str):
            val_upper = val.upper()
            found = False
            for term in search_terms:
                if term in val_upper:
                    results.append(props)
                    found = True
                    break
            if found:
                break

with open("geojson_broad_search.txt", "w") as out:
    for r in results:
        out.write(str(r) + "\n")
print(f"Found {len(results)} matches.")
