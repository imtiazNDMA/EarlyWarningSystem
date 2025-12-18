from services.map_service import MapService
import json

ms = MapService()
locations = {"Islamabad": (33.6844, 73.0479)}
html = ms.create_map(locations, selected_districts=["Islamabad"])

# Check for CSS
if "@keyframes breathing" in html:
    print("SUCCESS: CSS animation found")
else:
    print("FAILURE: CSS animation NOT found")

# Check for JS injection
if "applyBlinking" in html:
    print("SUCCESS: applyBlinking function found")
else:
    print("FAILURE: applyBlinking function NOT found")

# Check for case normalization in JS
if '["ISLAMABAD"]' in html:
    print("SUCCESS: Normalized district name found in JS")
else:
    print("FAILURE: Normalized district name NOT found in JS")

# Check for robust injection pattern
if "document.readyState === 'complete'" in html:
    print("SUCCESS: Robust injection pattern found")
else:
    print("FAILURE: Robust injection pattern NOT found")
