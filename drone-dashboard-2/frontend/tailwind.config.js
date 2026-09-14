/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        hud: {
          bg: "#0a0d12",
          panel: "#11161d",
          panelBorder: "#1f2937",
          sky: "#3a6ea5",
          ground: "#5b3f25",
          text: "#e2e8f0",
          dim: "#64748b",
          green: "#22c55e",
          amber: "#f59e0b",
          red: "#ef4444",
        },
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
