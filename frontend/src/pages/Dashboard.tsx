import type { Session } from "@supabase/supabase-js";

type DashboardProps = {
  session: Session;
};
// TODO important to adjust supabase polies to include email confirmation and what not
export default function Dashboard({ session }: DashboardProps) {
  const user = session.user;

  return (
    <div style={{ padding: 24 }}>
      <h1>Dashboard</h1>
      <p>
        <b>Email:</b> {user.email}
      </p>
      <p>
        <b>Name:</b> {user.user_metadata.full_name || "—"}
      </p>
      <button
        onClick={async () => {
          await import("../libs/supabase").then(({ supabase }) =>
            supabase.auth.signOut()
          );
        }}
      >
        Sign Out
      </button>
    </div>
  );
}
