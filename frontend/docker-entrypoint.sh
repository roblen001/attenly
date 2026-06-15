#!/bin/sh
set -eu

CONFIG_PATH=/usr/share/nginx/html/config.js

json_string() {
  escaped=$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r//g')
  printf '"%s"' "$escaped"
}

{
  printf 'window.__ATTENLY_CONFIG__ = {\n'
  printf '  VITE_API_BASE_URL: %s,\n' "$(json_string "${VITE_API_BASE_URL:-/api}")"
  printf '  VITE_AUTH_PROVIDER: %s,\n' "$(json_string "${VITE_AUTH_PROVIDER:-local}")"
  printf '  VITE_SUPABASE_URL: %s,\n' "$(json_string "${VITE_SUPABASE_URL:-}")"
  printf '  VITE_SUPABASE_ANON_KEY: %s,\n' "$(json_string "${VITE_SUPABASE_ANON_KEY:-}")"
  printf '  VITE_LOCAL_AUTH_USER_ID: %s,\n' "$(json_string "${VITE_LOCAL_AUTH_USER_ID:-local-admin}")"
  printf '  VITE_LOCAL_AUTH_EMAIL: %s,\n' "$(json_string "${VITE_LOCAL_AUTH_EMAIL:-local-admin@example.com}")"
  printf '  VITE_LOCAL_AUTH_DISPLAY_NAME: %s,\n' "$(json_string "${VITE_LOCAL_AUTH_DISPLAY_NAME:-Local Admin}")"
  printf '  VITE_LOCAL_AUTH_TOKEN: %s,\n' "$(json_string "${VITE_LOCAL_AUTH_TOKEN:-}")"
  printf '  VITE_TINYMCE_MODE: %s,\n' "$(json_string "${VITE_TINYMCE_MODE:-self_hosted}")"
  printf '  VITE_TINYMCE_SCRIPT_SRC: %s,\n' "$(json_string "${VITE_TINYMCE_SCRIPT_SRC:-/tinymce/tinymce.min.js}")"
  printf '  VITE_TINYMCE_LICENSE_KEY: %s,\n' "$(json_string "${VITE_TINYMCE_LICENSE_KEY:-gpl}")"
  printf '  VITE_TINYMCE_API_KEY: %s\n' "$(json_string "${VITE_TINYMCE_API_KEY:-}")"
  printf '};\n'
} > "$CONFIG_PATH"
