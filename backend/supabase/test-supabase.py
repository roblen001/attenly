# TODO DELETE: ths file is for testing purposes delete once you understand how to use supabase
from supabase import create_client, Client
from .config import SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# new_row: Client = {    # This line creates a new first_name_demo value for testing purposes
#     "first_name_demo": "Fella",
# }

# supabase.table("demo-table").insert(new_row).execute() # This line inserts a new row
# supabase.table("demo-table").update(new_row).eq("id", 2).execute() # This line updates the row with id 2

results = supabase.table("demo-table").select("*").execute()


print(results)
