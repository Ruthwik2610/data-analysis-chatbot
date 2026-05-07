export type Theme = "light" | "dark";

export function getTheme(): Theme {
  if (typeof window === "undefined") return "light";
  if (typeof localStorage?.getItem !== "function") return "light";
  return (localStorage.getItem("theme") as Theme) ?? "light";
}

export function setTheme(t: Theme) {
  if (typeof localStorage?.setItem === "function") localStorage.setItem("theme", t);
  document.documentElement.setAttribute("data-theme", t);
}

export function toggleTheme() {
  setTheme(getTheme() === "dark" ? "light" : "dark");
}
