/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html","./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: { vazir: ["Vazirmatn","sans-serif"] },
      colors: {
        glass: "rgba(255,255,255,0.06)",
        glassBorder: "rgba(255,255,255,0.10)",
      }
    }
  },
  plugins: []
}
