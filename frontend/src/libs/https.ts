import { API_BASE_URL } from "./configs";

export async function api(path: string, init: RequestInit = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
    ...init,
  });
  if (!res.ok)
    throw new Error(`${res.status} ${await res.text().catch(() => "")}`);
  return res;
}
