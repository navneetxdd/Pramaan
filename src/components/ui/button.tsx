import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-glow)] disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        default: "border border-[var(--border-default)] bg-[var(--accent-500)] text-[var(--text-primary)] hover:bg-[var(--accent-400)]",
        secondary: "border border-[var(--border-subtle)] bg-[var(--surface-3)] text-[var(--text-primary)] hover:bg-[var(--surface-4)]",
        outline: "border border-[var(--border-default)] bg-transparent text-[var(--text-primary)] hover:bg-[var(--surface-4)]",
        ghost: "text-[var(--text-secondary)] hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]",
        destructive: "border border-[var(--status-danger)] bg-[var(--surface-3)] text-[var(--status-danger)] hover:bg-[var(--surface-4)]",
      },
      size: {
        default: "h-9 px-3 py-1.5",
        sm: "h-8 px-2.5 text-[12px]",
        lg: "h-10 px-4",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";
