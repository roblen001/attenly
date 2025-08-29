# used in web applications to organize and manage user-related functionalities,
# such as registration, login, and profile management.
# They handle routing for user-specific URLs and actions,
# often interacting with a database to manage user data.




@router.get("/users")
async def get_users():
    response = supabase.table("users").select("*").execute()
    return response.data

