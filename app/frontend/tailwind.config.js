/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        orange: {
          400: '#fb923c',
          500: '#f97316',
          600: '#ea580c',
        },
        charcoal: {
          50:  '#f5f5f5',
          100: '#ebebeb',
          200: '#d4d4d4',
          300: '#b0b0b0',
          400: '#888888',
          500: '#6d6d6d',
          600: '#555555',
          700: '#3a3a3a',
          800: '#2a2a2a',
          900: '#1a1a1a',
          950: '#111111',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
