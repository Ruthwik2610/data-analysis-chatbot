export type Theme = "light" | "dark";

export function getTheme(): Theme {
  if (typeof window === "undefined") return "light";
  return (localStorage.getItem("theme") as Theme) ?? "light";
}

export function setTheme(t: Theme) {
  localStorage.setItem("theme", t);
  document.documentElement.setAttribute("data-theme", t);
}

export function toggleTheme() {
  setTheme(getTheme() === "dark" ? "light" : "dark");
}
