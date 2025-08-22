"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost";
}

export function Button({ className, variant = "default", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2",
        variant === "default" && "bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-400",
        variant === "outline" && "border border-neutral-300 bg-transparent hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800",
        variant === "ghost" && "bg-transparent hover:bg-neutral-100 dark:hover:bg-neutral-800",
        className
      )}
      {...props}
    />
  );
}
