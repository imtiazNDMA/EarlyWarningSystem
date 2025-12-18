from services.map_service import MapService
import json

ms = MapService()
locations = {"Islamabad": (33.6844, 73.0479)}
html = ms.create_map(locations, selected_districts=["Islamabad"])

# Print the JS part
start_idx = html.find("<script>")
end_idx = html.find("</script>", start_idx) + 9
print(html[start_idx:end_idx])

# Print the other JS part
start_idx = html.find("<script>", end_idx)
end_idx = html.find("</script>", start_idx) + 9
print(html[start_idx:end_idx])
