"use client";

import * as React from "react";
import { cn } from "./cn";

export function Input(
  props: React.InputHTMLAttributes<HTMLInputElement>
) {
  const { className, ...rest } = props;
  return <input className={cn("input", className)} {...rest} />;
}
