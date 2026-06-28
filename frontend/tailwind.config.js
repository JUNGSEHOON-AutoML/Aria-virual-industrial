/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Outfit', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      colors: {
        // ARIA Cybernetic Tokens — Zinc base
        zinc: {
          950: '#09090b',
        },
        accent: {
          cyan:   '#38bdf8',
          violet: '#a78bfa',
          green:  '#4ade80',
          red:    '#f87171',
          amber:  '#fbbf24',
          orange: '#fb923c',
        },
      },
      backdropBlur: {
        xs: '2px',
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.25rem',
      },
      animation: {
        'scan':         'scanlines 10s linear infinite',
        'glow-pulse':   'glow-pulse 1.5s ease-in-out infinite alternate',
        'cursor-blink': 'cursor-blink 0.75s step-end infinite',
        'spin-ring':    'spin-ring 0.9s linear infinite',
        'eva-blink':    'eva-blink 0.8s ease-in-out infinite alternate',
        'fade-in-up':   'fade-in-up 0.3s ease forwards',
        'slide-up':     'slide-up 0.25s cubic-bezier(0.16,1,0.3,1) forwards',
      },
      keyframes: {
        scanlines: {
          '0%':   { backgroundPosition: '0 0' },
          '100%': { backgroundPosition: '0 200px' },
        },
        'glow-pulse': {
          from: { boxShadow: '0 0 8px rgba(56,189,248,0.3)' },
          to:   { boxShadow: '0 0 24px rgba(56,189,248,0.75)' },
        },
        'cursor-blink': {
          '0%,100%': { opacity: '1' },
          '50%':     { opacity: '0' },
        },
        'spin-ring': {
          to: { transform: 'rotate(360deg)' },
        },
        'eva-blink': {
          '0%':   { opacity: '0.45' },
          '100%': { opacity: '1' },
        },
        'fade-in-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(20px) scale(0.97)' },
          to:   { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
      },
    },
  },
  plugins: [],
}
