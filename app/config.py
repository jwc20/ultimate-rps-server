from dotenv import load_dotenv

import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM =  os.getenv("ALGORITHM") 
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REDIS_URL = os.getenv("REDIS_URL")

# SQLITE_URL="sqlite:///database.db"

DEV = os.environ.get("DEV", "true").lower() == "true"
SQLITE_URL = os.environ.get("SQLITE_URL", "sqlite:///./sql_app.db")
POSTGRES_URL = os.environ.get("POSTGRES_URL")