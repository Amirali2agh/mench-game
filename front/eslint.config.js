import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

/**
 * Flat ESLint config for the game client.
 *
 * The interesting rule is `react-hooks/exhaustive-deps`: the board has several
 * effects that close over render values, and a missing dependency there is a
 * real desync bug, not a style issue.
 */
export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // Config files run under Node and use CommonJS exports.
    files: ["*.config.js"],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      // Only the two classic hook rules: the newer compiler-oriented rules
      // (set-state-in-effect, preserve-manual-memoization) flag patterns this
      // client relies on and are out of scope for this change.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "no-console": ["warn", { allow: ["warn", "error", "debug"] }],
    },
  },
);
