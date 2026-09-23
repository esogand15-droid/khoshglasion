/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Vazirmatn", "Fira Sans", "Tahoma", "sans-serif"],
        mono: ["Fira Code", "Vazirmatn", "ui-monospace", "monospace"],
      },
      colors: {
        background: "#020617",
        foreground: "#F8FAFC",
        card: "#0E1223",
        accent: "#16A34A",
        border: "#334155",
        destructive: "#DC2626",
      },
      borderRadius: { none: "0px" },
    },
  },
  plugins: [],
};
