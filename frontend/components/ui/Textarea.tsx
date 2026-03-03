"use client";

import * as React from "react";
import { cn } from "./cn";

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { className, ...rest } = props;
  return <textarea className={cn("input", className)} {...rest} />;
}