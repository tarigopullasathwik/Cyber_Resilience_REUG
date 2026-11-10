/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#040a12",
          900: "#07111d",
          850: "#0a1624",
          800: "#0d1b2cab",
          750: "#102134",
          700: "#14283e",
        },
        line: "#1b3049",
        cyan: "#22d3ee",
        electric: "#3b82f6",
        normal: "#34d399",
        suspicious: "#fbbf24",
        threat: "#f87171",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "Consolas", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 18px 44px -26px rgba(0, 0, 0, 0.9)",
        glow: "0 0 0 1px rgba(34, 211, 238, 0.18), 0 0 28px -8px rgba(34, 211, 238, 0.35)",
      },
      animation: {
        "fade-in": "fadeIn 0.25s ease-out",
        "pulse-soft": "pulseSoft 2.4s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: 0, transform: "translateY(4px)" }, "100%": { opacity: 1, transform: "none" } },
        pulseSoft: { "0%,100%": { opacity: 0.55 }, "50%": { opacity: 1 } },
      },
    },
  },
  plugins: [],
};
