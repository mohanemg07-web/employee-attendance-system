/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "var(--color-border)",
        input: "var(--color-border)",
        ring: "var(--color-accent-glow)",
        background: "var(--color-bg-primary)",
        foreground: "var(--color-text-primary)",
        primary: {
          DEFAULT: "var(--color-accent)",
          foreground: "#ffffff",
        },
        secondary: {
          DEFAULT: "var(--color-bg-secondary)",
          foreground: "var(--color-text-secondary)",
        },
        muted: {
          DEFAULT: "var(--color-bg-muted)",
          foreground: "var(--color-text-muted)",
        },
        accent: {
          DEFAULT: "var(--color-accent-glow)",
          foreground: "var(--color-accent-light)",
        },
        card: {
          DEFAULT: "var(--color-bg-card)",
          foreground: "var(--color-text-primary)",
        },
        popover: {
          DEFAULT: "var(--color-bg-card)",
          foreground: "var(--color-text-primary)",
        },
      },
      borderRadius: {
        lg: "var(--radius-lg)",
        md: "var(--radius-md)",
        sm: "var(--radius-sm)",
      },
      fontFamily: {
        sans: ["var(--font-family)"],
        mono: ["var(--font-mono)"],
      },
    },
  },
  plugins: [],
}
