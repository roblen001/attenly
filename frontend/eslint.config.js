import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import { globalIgnores } from "eslint/config";

export default tseslint.config([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat["recommended-latest"],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // TinyMCE and PDF.js expose several dynamic APIs without complete public
      // TypeScript surfaces. Keep lint focused on actionable application errors.
      "@typescript-eslint/no-explicit-any": "off",
      // These compiler-oriented rules were added after the application's hooks
      // were written. Adopt them incrementally instead of blocking security
      // upgrades to the lint toolchain.
      "react-hooks/immutability": "off",
      "react-hooks/set-state-in-effect": "off",
      "no-useless-assignment": "off",
    },
  },
]);
