/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        panel: {
          bg: '#0B0E11',
          surface: '#12161C',
          elevated: '#181D25',
          border: '#1E2530',
          hover: '#222A36',
        },
        accent: {
          cyan: 'rgb(0, 212, 170)',
          'cyan-dim': 'rgba(0, 212, 170, 0.2)',
          blue: 'rgb(59, 130, 246)',
          'blue-dim': 'rgba(59, 130, 246, 0.2)',
        },
        bull: 'rgb(0, 212, 170)',
        'bull-dim': 'rgba(0, 212, 170, 0.13)',
        bear: 'rgb(255, 71, 87)',
        'bear-dim': 'rgba(255, 71, 87, 0.13)',
        warn: 'rgb(255, 179, 71)',
        'warn-dim': 'rgba(255, 179, 71, 0.13)',
        muted: '#5C6A7F',
        subtle: '#3A4553',
      },
      fontFamily: {
        sans: ['JetBrains Mono', 'SF Mono', 'monospace'],
        display: ['Space Grotesk', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.65rem', { lineHeight: '1rem' }],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.4s ease-out',
        'slide-in-right': 'slideInRight 0.3s ease-out',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(100%)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        glow: {
          '0%': { boxShadow: '0 0 5px #00D4AA33' },
          '100%': { boxShadow: '0 0 20px #00D4AA44' },
        },
      },
    },
  },
  plugins: [],
};
