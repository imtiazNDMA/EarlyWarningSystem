"""Fail fast when the configured MongoDB instance is unavailable."""

import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()
uri = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
database = os.getenv("MONGODB_DATABASE", "early_warnings")
timeout_ms = int(os.getenv("MONGODB_TIMEOUT_MS", "5000"))

try:
    client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
    client.admin.command("ping")
except PyMongoError as error:
    print(f"[ERROR] MongoDB is unavailable at {uri}: {error}")
    print("[ERROR] MongoDB is required for forecast and warning persistence.")
    sys.exit(1)
finally:
    if "client" in locals():
        client.close()

print(f"[INFO] MongoDB is ready with database '{database}'.")
