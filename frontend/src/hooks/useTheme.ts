import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("ssg_theme") as Theme | null) || "light"
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("ssg_theme", theme);
  }, [theme]);

  const toggle = () => setTheme((t) => (t === "light" ? "dark" : "light"));

  return { theme, toggle };
}
