/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
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
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-down': {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out',
        'slide-up': 'slide-up 0.4s ease-out',
        'slide-down': 'slide-down 0.4s ease-out',
        'pulse-glow': 'pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        shimmer: 'shimmer 2s linear infinite',
      },
      backdropBlur: {
        xs: '2px',
      },
      transitionTimingFunction: {
        'out-expo': 'cubic-bezier(0.16, 1, 0.3, 1)',
        'in-expo': 'cubic-bezier(0.7, 0, 0.84, 0)',
      },
    },
  },
  plugins: [],
};
