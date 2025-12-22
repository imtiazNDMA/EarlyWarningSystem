import json

file_path = (
    r"g:\AI Projects\projects\earlyWarnings\static\boundary\pakistan_districts_fixed.geojson"
)
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

search_terms = ["DIAMER", "DIAMIR", "ROUNDU", "RUNDU"]

results = []
for feature in data["features"]:
    props = feature["properties"]
    for val in props.values():
        if isinstance(val, str):
            val_upper = val.upper()
            for term in search_terms:
                if term in val_upper:
                    results.append(props)
                    break

with open("geojson_search_results.txt", "w") as out:
    for r in results:
        out.write(str(r) + "\n")
print(f"Found {len(results)} potential matches.")
