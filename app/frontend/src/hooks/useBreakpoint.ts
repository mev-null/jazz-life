import { useEffect, useState } from "react";

type Breakpoint = "sm" | "md" | "lg";

const MD = 768;
const LG = 1024;

const getBreakpoint = (): Breakpoint => {
  if (typeof window === "undefined") return "lg";
  if (window.matchMedia(`(min-width: ${LG}px)`).matches) return "lg";
  if (window.matchMedia(`(min-width: ${MD}px)`).matches) return "md";
  return "sm";
};

export function useBreakpoint() {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(getBreakpoint);

  useEffect(() => {
    const handler = () => setBreakpoint(getBreakpoint());
    const mqMd = window.matchMedia(`(min-width: ${MD}px)`);
    const mqLg = window.matchMedia(`(min-width: ${LG}px)`);
    mqMd.addEventListener("change", handler);
    mqLg.addEventListener("change", handler);
    return () => {
      mqMd.removeEventListener("change", handler);
      mqLg.removeEventListener("change", handler);
    };
  }, []);

  return {
    breakpoint,
    isMobile: breakpoint === "sm",
    isDesktop: breakpoint !== "sm",
  };
}
