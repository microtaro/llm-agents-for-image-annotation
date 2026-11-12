// Buttons of DESIGN.md 3 and 7: white with a border, primary (the action color), and text
// links (blue, or red for removing a saved record).
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

const button = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm cursor-pointer disabled:cursor-default disabled:opacity-55 focus-visible:outline-2 focus-visible:outline-offset-1",
  {
    variants: {
      variant: {
        default: "border border-line bg-surface px-3.5 py-1.5 text-ink hover:bg-hover",
        primary: "border border-action bg-action px-3.5 py-1.5 text-white hover:bg-action-hover",
        // Pressed, it changes what training uses at once, nothing to decide after (DESIGN.md 6:
        // green; user 2026-10-16).
        use: "border border-annotated bg-annotated px-3.5 py-1.5 text-fill-ink hover:brightness-110",
        link: "px-0 py-0 text-action underline underline-offset-2",
        danger: "px-0 py-0 text-failed underline underline-offset-2",
        // The button that deletes or takes out, in a confirm: red as its entry is (Astra
        // 2026-10-06: it was blue like Save).
        destructive:
          "border border-failed bg-failed px-3.5 py-1.5 text-fill-ink hover:bg-failed-hover",
      },
      size: { default: "", small: "px-2.5 py-0.5 text-body" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export function Button({
  className,
  variant,
  size,
  type = "button",
  ...props
}: ComponentProps<"button"> & VariantProps<typeof button>) {
  return <button type={type} className={cn(button({ variant, size }), className)} {...props} />;
}
