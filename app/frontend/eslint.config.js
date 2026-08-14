import js from '@eslint/js'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import prettierConfig from 'eslint-config-prettier'
import globals from 'globals'

export default [
  {
    files: ['src/**/*.{js,jsx}'],
    plugins: {
      react,
      'react-hooks': reactHooks,
    },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    settings: {
      react: { version: 'detect' },
    },
    rules: {
      ...js.configs.recommended.rules,
      ...react.configs.flat.recommended.rules,
      // Only the two rules this project has always had. eslint-plugin-react-hooks
      // v7's own "recommended" adds 14 new React-Compiler-oriented strict rules
      // (purity, immutability, set-state-in-render, etc.) this codebase has never
      // been evaluated against — adopting those is a deliberate future decision,
      // not an implied side effect of a version bump. Same reasoning as
      // react/prop-types below.
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      ...prettierConfig.rules,

      'react/react-in-jsx-scope': 'off',
      // Never adopted anywhere in this codebase (confirmed 2026-08-14: 1417
      // pre-existing warnings across ~90 components once this migration fixed
      // the .jsx files this linter had been silently skipping) — an established
      // convention, not oversight. See docs/MEMORY.md.
      'react/prop-types': 'off',
      // "error"/"warn" are deliberate diagnostics used throughout (crash
      // handlers, caught-exception logging) — only console.log-style debug
      // output is disallowed, matching docs/AGENTS.md's actual stated
      // convention ("No console.log in committed code").
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      // A handful of intentional best-effort `catch {}` blocks exist on
      // purpose (e.g. a cached-value read that's fine to skip if malformed).
      'no-empty': ['error', { allowEmptyCatch: true }],
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    },
  },
]
