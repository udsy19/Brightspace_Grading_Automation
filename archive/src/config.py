import os
import sys
from dotenv import load_dotenv

# Load .env file
load_dotenv()

def load_config():
    username = os.getenv("PURDUE_USERNAME")
    password = os.getenv("PURDUE_PASSWORD")

    if not username or not password:
        print("Error: PURDUE_USERNAME or PURDUE_PASSWORD not found in environment variables.")
        print("Please create a .env file with your credentials.")
        sys.exit(1)

    return {
        "username": username,
        "password": password
    }
