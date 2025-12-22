import geopandas as gpd
import json

gdf = gpd.read_file(r"static/boundary/pakistan_districts_fixed.geojson")
geojson_dict = json.loads(gdf.to_json())

# Check the first feature's properties
first_feature = geojson_dict["features"][0]
print("Properties keys:", list(first_feature["properties"].keys()))
print("First feature properties:", first_feature["properties"])
