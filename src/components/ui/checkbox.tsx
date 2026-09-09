import { forwardRef } from "react";
import { cn } from "@/lib/utils";

type CheckboxProps = Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "type" | "onChange"
> & {
  checked?: boolean;
  indeterminate?: boolean;
  onCheckedChange?: (checked: boolean) => void;
};

/**
 * shadcn-shaped checkbox over the native control.
 *
 * `@radix-ui/react-checkbox` is not a dependency of this app and adding one for
 * a single control is not worth the install; the native input carries the same
 * keyboard and screen-reader behaviour for free. The API (`checked`,
 * `onCheckedChange`) matches shadcn's so a swap later is mechanical.
 */
export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  function Checkbox(
    { className, checked, indeterminate, onCheckedChange, ...props },
    ref,
  ) {
    return (
      <input
        ref={(node) => {
          if (node) node.indeterminate = Boolean(indeterminate) && !checked;
          if (typeof ref === "function") ref(node);
          else if (ref) ref.current = node;
        }}
        type="checkbox"
        checked={checked}
        onChange={(event) => onCheckedChange?.(event.target.checked)}
        className={cn(
          "h-3.5 w-3.5 shrink-0 cursor-pointer rounded border-[var(--border-default)] accent-[var(--accent-500)]",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--accent-500)]",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      />
    );
  },
);
