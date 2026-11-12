// The switch between light and dark, at the right end of every screen's top row.
import { Moon, Sun } from "lucide-react";
import { t } from "@/i18n";
import { setTheme, useTheme } from "@/lib/theme";

export function ThemeToggle() {
  const theme = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      aria-label={t(`theme.to.${next}`)}
      title={t(`theme.to.${next}`)}
      onClick={() => setTheme(next)}
      className="inline-flex size-8 cursor-pointer items-center justify-center rounded-md border border-line bg-surface text-ink hover:bg-hover"
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}
