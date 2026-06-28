import type { Config } from "tailwindcss";

/**
 * TailwindCSS configuration.
 *
 * Scans the App Router tree under src/ for class usage.
 */
const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        court: "#c0612b",
      },
    },
  },
  plugins: [],
};

export default config;
