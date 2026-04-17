import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sar: {
          orange: "#E8650A",
          dark: "#1A1F2E",
          panel: "#242938",
          border: "#2F3650",
          text: "#E2E8F0",
          muted: "#6B7A99",
        },
      },
    },
  },
  plugins: [],
};

export default config;
