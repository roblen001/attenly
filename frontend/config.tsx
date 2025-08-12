// import path from "path";
import dotenv from "dotenv";
dotenv.config(); // This loads environment variables into process.env

import { createClient } from "@supabase/supabase-js";
import { Database } from "./database_types";

// dotenv.config({
//   path: path.resolve(__dirname, "../.env"), // adjust relative path as needed
// });

export const supabase = createClient<Database>(
  process.env.VITE_SUPABASE_URL as string,
  process.env.VITE_SUPABASE_KEY as string
);
