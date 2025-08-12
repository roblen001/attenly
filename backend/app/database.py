# In a Python project, a database.py file typically encapsulates all the logic and functions
# related to interacting with a database. Its primary purpose is to centralize database operations,
# making the rest of the application cleaner and more organized.

# This file can contain:

# Database connection management:
# Functions to establish and close connections to the database (e.g., SQLite, PostgreSQL, MySQL).

# SQL query execution:
# Functions to execute various SQL commands like CREATE TABLE, INSERT, SELECT, UPDATE, and DELETE.

# Data modeling:
# Definitions of how data is structured within the database, potentially using Object-Relational
# Mappers (ORMs) like SQLAlchemy or Flask-SQLAlchemy to map Python objects to database tables.

# Helper functions:
# Utility functions for common database tasks, such as creating tables,
# adding data, retrieving specific records, or handling transactions.

# Error handling:
# Mechanisms to gracefully manage potential errors during database interactions.
# By isolating database logic in database.py, developers can easily modify the database system or
# its schema without significantly impacting other parts of the application.

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY]):
    raise ValueError("Supabase URL and Key must be set in environment variables.")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
