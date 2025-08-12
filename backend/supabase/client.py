# This file defines the main Client class and associated methods that enable Python applications to interact with various Supabase services.

from supabase import create_client, Client
from .config import SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
