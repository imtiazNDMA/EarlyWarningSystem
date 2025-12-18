import glob
import os

def purge_all():
    files = glob.glob("static/weatherdata/*.json")
    print(f"Found {len(files)} files. Deleting...")
    for f in files:
        try:
            os.remove(f)
        except Exception as e:
            print(f"Error deleting {f}: {e}")
    print("All cache files deleted.")

if __name__ == "__main__":
    purge_all()
