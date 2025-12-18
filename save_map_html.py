from services.map_service import MapService
import json

ms = MapService()
locations = {"Islamabad": (33.6844, 73.0479)}
html = ms.create_map(locations, selected_districts=["Islamabad"])

with open("g:/AI Projects/projects/earlyWarnings/debug_map.html", "w", encoding="utf-8") as f:
    f.write(html)
print("HTML saved to debug_map.html")
