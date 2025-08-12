import "./App.css";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import LandingPage from "./pages/LandingPage";
import Dashboard from "./pages/Dashboard";
import { useState, useEffect } from "react";
import { createClient } from "@supabase/supabase-js";
import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import type { Session } from "@supabase/supabase-js";

const supabase = createClient(
  "https://<project>.supabase.co",
  "<your-anon-key>"
);

export default function App() {
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
    });

    return () => subscription.unsubscribe();
  }, []);

  if (!session) {
    return <Auth supabaseClient={supabase} appearance={{ theme: ThemeSupa }} />;
  } else {
    return (
      <Router>
        <div>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route
              path="/dashboard"
              element={<Dashboard profiles={profiles} />}
            />
          </Routes>
        </div>
      </Router>
    );
  }
}

// import { useState, useEffect } from "react";
// import { Auth } from "@supabase/auth-ui-react";
// import { ThemeSupa } from "@supabase/auth-ui-shared";
// import { supabase } from "../supabaseClient";
// import type { Session } from "@supabase/supabase-js";

// export default function App() {
//   const [session, setSession] = useState<Session | null>(null);
//   const [profiles, setProfiles] = useState([]);

//   useEffect(() => {
//     // Load the session
//     supabase.auth.getSession().then(({ data: { session } }) => {
//       setSession(session);
//     });

//     // Listen for auth changes
//     const {
//       data: { subscription },
//     } = supabase.auth.onAuthStateChange((_event, session) => {
//       setSession(session);
//     });

//     // Example query: Fetch profiles
//     const fetchProfiles = async () => {
//       const { data, error } = await supabase.from("profiles").select("*");
//       if (error) {
//         console.error("Error fetching profiles:", error);
//       } else {
//         setProfiles(data || []);
//       }
//     };

//     fetchProfiles();

//     return () => subscription.unsubscribe();
//   }, []);

//   if (!session) {
//     return <Auth supabaseClient={supabase} appearance={{ theme: ThemeSupa }} />;
//   }

//   return (
//     <Router>
//       <div>
//         <Routes>
//           <Route path="/" element={<LandingPage />} />
//           <Route
//             path="/dashboard"
//             element={<Dashboard profiles={profiles} />}
//           />
//         </Routes>
//       </div>
//     </Router>
//   );
// }
