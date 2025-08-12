# FILE INFO: This config.py use to store Supabase URL and API key.
# TODO delete restart when supabase set up backend
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
