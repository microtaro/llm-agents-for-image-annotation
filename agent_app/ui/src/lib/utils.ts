import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// The text steps of index.css (--text-*) are sizes, not colors: without this, "text-body"
// took the place of a button's "text-white" (user 2026-10-14: dark text on the purple).
const twMerge = extendTailwindMerge({
  extend: {
    theme: { text: ["tiny", "note", "small", "body", "lead", "heading", "large", "title"] },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
