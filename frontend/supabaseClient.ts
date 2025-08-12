// import path from "path";
import dotenv from "dotenv";
dotenv.config(); // This loads environment variables into process.env

import { createClient } from "@supabase/supabase-js";
import type { Database } from "./database_types";

export const supabase = createClient<Database>(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_KEY
);
