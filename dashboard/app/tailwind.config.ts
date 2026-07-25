import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // dark chrome (headers, nav, ops shell)
        'beacon': {
          bg: {
            900: '#0A0F1A',
            800: '#101725',
            700: '#182130',
          },
          text: {
            hi: '#F1F5F9',
            mid: '#94A3B8',
            lo: '#64748B',
          },
          line: {
            dark: 'rgba(255, 255, 255, 0.08)',
          },
        },
        // light content (data panels, member view, exec view)
        'content': {
          bg: {
            50: '#F7F9FC',
            0: '#FFFFFF',
          },
          ink: {
            hi: '#0F172A',
            mid: '#475569',
            lo: '#94A3B8',
          },
          line: {
            light: 'rgba(15, 23, 42, 0.08)',
          },
        },
        // brand
        'discovery': {
          DEFAULT: '#0B5FA5',
          soft: '#E8F1F9',
        },
        // risk ramp
        'risk': {
          safe: '#10B981',
          watch: '#F59E0B',
          high: '#F0653A',
          critical: '#E11D48',
        },
        // semantic
        'live': '#22D3EE',
        'stale': '#6B7280',
      },
      backgroundImage: {
        'beacon-grad': 'linear-gradient(135deg, #F5A623 0%, #F27B21 100%)',
      },
      boxShadow: {
        'beacon-card': '0 1px 2px rgba(15, 23, 42, 0.06), 0 6px 20px rgba(15, 23, 42, 0.06)',
        'beacon-card-dark': '0 1px 2px rgba(0, 0, 0, 0.3), 0 8px 28px rgba(0, 0, 0, 0.35)',
      },
      animation: {
        'button-lift': 'buttonLift 0.12s ease',
        'button-press': 'buttonPress 0.12s ease',
      },
      keyframes: {
        buttonLift: {
          'from': { transform: 'translateY(0)', filter: 'brightness(1)' },
          'to': { transform: 'translateY(-1px)', filter: 'brightness(1.08)' },
        },
        buttonPress: {
          'from': { transform: 'translateY(-1px)', filter: 'brightness(1.08)' },
          'to': { transform: 'translateY(0)', filter: 'brightness(0.95)' },
        },
      },
      fontFamily: {
        'sans': ['Inter Variable', 'Inter', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
