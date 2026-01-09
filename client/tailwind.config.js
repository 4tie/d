/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"] ,
  theme: {
    extend: {
      colors: {
        bg: {
          950: "rgb(var(--bg-950) / <alpha-value>)",
          900: "rgb(var(--bg-900) / <alpha-value>)",
          850: "rgb(var(--bg-850) / <alpha-value>)",
        },
        panel: {
          900: "rgb(var(--panel-900) / <alpha-value>)",
          800: "rgb(var(--panel-800) / <alpha-value>)",
          750: "rgb(var(--panel-750) / <alpha-value>)",
        },
        border: {
          700: "rgb(var(--border-700) / <alpha-value>)",
          650: "rgb(var(--border-650) / <alpha-value>)",
        },
        fg: {
          100: "rgb(var(--fg-100) / <alpha-value>)",
          200: "rgb(var(--fg-200) / <alpha-value>)",
          400: "rgb(var(--fg-400) / <alpha-value>)",
        },
        semantic: {
          pos: "rgb(var(--semantic-pos) / <alpha-value>)",
          neg: "rgb(var(--semantic-neg) / <alpha-value>)",
          warn: "rgb(var(--semantic-warn) / <alpha-value>)",
          info: "rgb(var(--semantic-info) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: ["Segoe UI", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "Liberation Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
