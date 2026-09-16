import type { Config } from "tailwindcss";

/**
 * PulseIQ design tokens.
 *
 * The palette is intentionally narrow: a neutral graphite ramp carries almost
 * everything, one accent marks interactive intent, and the three signal colours
 * are reserved for screening risk. Anything outside that vocabulary should be
 * treated as a bug rather than a styling choice.
 */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /* Named `canvas` rather than `base` so it cannot collide with the
           `text-base` font-size utility, which would silently repaint text. */
        canvas: "#0B0C0F",
        panel: "#121418",
        elev: "#181B21",
        inset: "#0E1014",
        line: "#24282F",
        line2: "#31363F",
        fg: "#EBEDF0",
        muted: "#99A1AB",
        faint: "#6B7280",
        accent: {
          DEFAULT: "#35D1BA",
          strong: "#5FE3CE",
          soft: "#16302C",
          ink: "#04211D"
        },
        danger: { DEFAULT: "#F2555A", soft: "#33161A", strong: "#FF7A7E" },
        warn: { DEFAULT: "#E9A23B", soft: "#33260F", strong: "#F7BC63" },
        ok: { DEFAULT: "#44C186", soft: "#132B20", strong: "#6BD6A4" },
        info: { DEFAULT: "#5AA9F5", soft: "#132434", strong: "#83C1FF" }
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif"
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace"
        ]
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.01em" }],
        xs: ["0.75rem", { lineHeight: "1.05rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.875rem", { lineHeight: "1.45rem" }],
        lg: ["1rem", { lineHeight: "1.55rem" }],
        xl: ["1.125rem", { lineHeight: "1.6rem", letterSpacing: "-0.01em" }],
        "2xl": ["1.375rem", { lineHeight: "1.75rem", letterSpacing: "-0.015em" }],
        "3xl": ["1.75rem", { lineHeight: "2.1rem", letterSpacing: "-0.02em" }],
        "4xl": ["2.25rem", { lineHeight: "2.5rem", letterSpacing: "-0.025em" }],
        "5xl": ["3rem", { lineHeight: "3.15rem", letterSpacing: "-0.03em" }]
      },
      borderRadius: {
        sm: "0.375rem",
        DEFAULT: "0.5rem",
        md: "0.625rem",
        lg: "0.75rem",
        xl: "0.875rem",
        "2xl": "1.125rem"
      },
      boxShadow: {
        panel: "0 1px 1px rgba(0,0,0,0.35), 0 12px 28px -18px rgba(0,0,0,0.9)",
        lift: "0 2px 4px rgba(0,0,0,0.4), 0 20px 40px -24px rgba(0,0,0,0.95)",
        pop: "0 16px 48px -12px rgba(0,0,0,0.85), 0 0 0 1px rgba(255,255,255,0.05)",
        inset: "inset 0 1px 0 0 rgba(255,255,255,0.04)",
        focus: "0 0 0 3px rgba(53,209,186,0.18)"
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.22, 1, 0.36, 1)",
        spring: "cubic-bezier(0.34, 1.36, 0.64, 1)"
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" }
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" }
        },
        "slide-in": {
          "0%": { opacity: "0", transform: "translateY(6px) scale(0.99)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" }
        },
        sweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(300%)" }
        },
        shimmer: {
          "0%": { backgroundPosition: "-300% 0" },
          "100%": { backgroundPosition: "300% 0" }
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.45", transform: "scale(0.82)" }
        },
        "ring-pulse": {
          "0%": { boxShadow: "0 0 0 0 rgba(53,209,186,0.35)" },
          "70%": { boxShadow: "0 0 0 8px rgba(53,209,186,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(53,209,186,0)" }
        },
        "draw-line": {
          "0%": { strokeDashoffset: "620" },
          "55%": { strokeDashoffset: "0" },
          "100%": { strokeDashoffset: "-620" }
        }
      },
      animation: {
        "fade-up": "fade-up 0.45s cubic-bezier(0.22,1,0.36,1) both",
        "fade-in": "fade-in 0.35s ease-out both",
        "slide-in": "slide-in 0.28s cubic-bezier(0.22,1,0.36,1) both",
        sweep: "sweep 2.6s cubic-bezier(0.4,0,0.2,1) infinite",
        shimmer: "shimmer 1.8s linear infinite",
        "pulse-soft": "pulse-soft 2.2s ease-in-out infinite",
        "ring-pulse": "ring-pulse 2.4s ease-out infinite",
        "draw-line": "draw-line 5.5s linear infinite"
      }
    }
  },
  plugins: []
} satisfies Config;
