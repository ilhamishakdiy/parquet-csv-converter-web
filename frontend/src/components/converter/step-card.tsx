import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function StepCard({
  step,
  title,
  description,
  disabled,
  action,
  children,
}: {
  step: number;
  title: string;
  description?: ReactNode;
  disabled?: boolean;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card className={cn("transition-opacity", disabled && "pointer-events-none opacity-50")} aria-disabled={disabled}>
      <CardHeader className="flex flex-row items-start gap-3">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
          {step}
        </span>
        <div className="flex-1 space-y-1">
          <CardTitle className="text-base">{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {action}
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}
