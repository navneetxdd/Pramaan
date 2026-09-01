import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Instrument Sans", "IBM Plex Sans", "system-ui", "sans-serif"],
        serif: ["Instrument Serif", "Georgia", "serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        canvas: "var(--canvas)",
        surface: "var(--surface)",
        raised: "var(--raised)",
        sunken: "var(--sunken)",
        hairline: "var(--hairline)",
        "hairline-strong": "var(--hairline-strong)",
        ink: "var(--ink)",
        "ink-muted": "var(--ink-muted)",
        "ink-faint": "var(--ink-faint)",
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          soft: "var(--accent-soft)",
          line: "var(--accent-line)",
        },
        solved: {
          DEFAULT: "var(--solved)",
          soft: "var(--solved-soft)",
          line: "var(--solved-line)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          soft: "var(--danger-soft)",
        },
      },
      boxShadow: {
        ambient: "var(--shadow-ambient)",
        lifted: "var(--shadow-lifted)",
      },
    },
  },
  plugins: [],
} satisfies Config;
