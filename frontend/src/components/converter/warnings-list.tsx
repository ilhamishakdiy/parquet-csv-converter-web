import { AlertTriangle, Ban, Info } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { PlanWarning } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICONS = { blocking: Ban, warning: AlertTriangle, info: Info };

export function WarningsList({ warnings }: { warnings: PlanWarning[] }) {
  if (!warnings.length) return null;
  const order = { blocking: 0, warning: 1, info: 2 };
  return (
    <div className="space-y-2">
      {[...warnings]
        .sort((a, b) => order[a.severity] - order[b.severity])
        .map((w) => {
          const Icon = ICONS[w.severity];
          return (
            <Alert
              key={w.code + w.message}
              variant={w.severity === "blocking" ? "destructive" : "default"}
              className={cn(w.severity === "warning" && "border-amber-300 bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200")}
            >
              <Icon />
              <AlertDescription className={cn(w.severity === "warning" && "text-amber-900 dark:text-amber-200")}>
                {w.message}
              </AlertDescription>
            </Alert>
          );
        })}
    </div>
  );
}

export function ErrorAlert({ message, title, id }: { message: string | null; title?: string; id?: string }) {
  if (!message) return null;
  return (
    <Alert variant="destructive" id={id}>
      <Ban />
      {title && <AlertTitle>{title}</AlertTitle>}
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}
