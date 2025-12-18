from services.map_service import MapService
import json

ms = MapService()
locations = {"Islamabad": (33.6844, 73.0479)}
html = ms.create_map(locations, selected_districts=["Islamabad"])
print(html[:500])
if "<iframe" in html:
    print("Output contains iframe")
else:
    print("Output does NOT contain iframe")
