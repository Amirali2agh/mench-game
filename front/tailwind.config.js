/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class', // Supports standard dark class toggle
  theme: {
    extend: {
      colors: {
        textPrimary: "var(--text-primary)",
        textSecondary: "var(--text-secondary)",
        textTertiary: "var(--text-tertiary)",
        textInvierte: "var(--text-invierte)",
        backgroundPrimary: "var(--background-primary)",
        backgroundSecondary: "var(--background-secondary)",
        backgroundTertiary: "var(--background-tertiary)",
        primary: "var(--primary)",
        primaryContent: "var(--primary-content)",
        secondary: "var(--secondary)",
        secondaryContent: "var(--secondary-content)",
        buttonPrimary: "var(--button-primary)",
        buttonSecondary: "var(--button-secondary)",
        success: "var(--success)",
        error: "var(--error)",
        warning: "var(--warning)",
        info: "var(--info)",
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'fade-in': 'fade-in 180ms ease-out',
      },
    },
  },
  plugins: [],
}