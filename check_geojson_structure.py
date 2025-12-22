import geopandas as gpd
import json

gdf = gpd.read_file(r"static/boundary/pakistan_districts_fixed.geojson")
with open("geojson_columns.txt", "w") as f:
    f.write("Columns: " + str(list(gdf.columns)) + "\n\n")
    f.write("First 3 rows:\n")
    for i in range(min(3, len(gdf))):
        row_dict = {k: v for k, v in gdf.iloc[i].to_dict().items() if k != "geometry"}
        f.write(f"Row {i}: {row_dict}\n")
print("Written to geojson_columns.txt")
