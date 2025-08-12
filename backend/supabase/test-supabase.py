# TODO DELETE: ths file is for testing purposes delete once you understand how to use supabase
from supabase import create_client, Client
from .config import SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

results = supabase.table("demo-table").select("*").execute()

print(results)
