/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Custom colors for that premium feel if needed later
        // For now, relying on standard tailwind colors
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}

