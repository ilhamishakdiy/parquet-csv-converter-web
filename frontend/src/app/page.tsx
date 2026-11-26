import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  FileSpreadsheet,
  Filter,
  Layers,
  ListChecks,
  Lock,
  ShieldCheck,
  SplitSquareVertical,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const FEATURES = [
  {
    icon: Lock,
    title: "Stays on your PC",
    body: "Files are read and written by a small converter running on your own computer. Nothing is uploaded. This website is only the screen you use to control it.",
  },
  {
    icon: SplitSquareVertical,
    title: "Excel-sized parts",
    body: "Split millions of rows into CSV files of up to 800,000 rows each, or any limit you choose. Excel opens at most 1,048,575 rows per sheet.",
  },
  {
    icon: Layers,
    title: "Groups stay together",
    body: "Pick columns such as store_code and every store's rows land in the same file. A group is never split across two parts.",
  },
  {
    icon: Filter,
    title: "Separate files per value",
    body: "Choose a filter column such as department_code to get separate files per value, e.g. …_HARDWARE_part01.csv.",
  },
  {
    icon: ListChecks,
    title: "catalog.csv lookup",
    body: "Every export includes catalog.csv, listing which file holds each department and store, so you can find the right file in seconds.",
  },
  {
    icon: ShieldCheck,
    title: "Checked before you see it",
    body: "Every file's row count is verified against the source before it appears. Existing files are never overwritten.",
  },
];

const STEPS = [
  { title: "Choose the source", body: "Browse to a .parquet file, or a folder of shards such as a BigQuery export." },
  { title: "Configure", body: "Set the filename prefix, row limit, filter column and grouping columns." },
  { title: "Preview", body: "See the exact file names and row counts before anything is written." },
  { title: "Convert", body: "Watch the progress, then open the folder or catalog.csv when it's done." },
];

const EXAMPLE = [
  "Malaysia_Sales_Nov2026_HARDWARE_part01.csv",
  "Malaysia_Sales_Nov2026_HARDWARE_part02.csv",
  "Malaysia_Sales_Nov2026_ELECTRICAL_part01.csv",
  "catalog.csv",
];

export default function HomePage() {
  return (
    <div className="flex-1">
      <section className="border-b bg-muted/30">
        <div className="mx-auto grid max-w-5xl gap-10 px-4 py-14 md:grid-cols-[1.2fr_1fr] md:items-center">
          <div className="space-y-5">
            <p className="inline-flex items-center gap-1.5 rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground">
              <Lock className="size-3" /> Your data never leaves your computer
            </p>
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Turn huge Parquet exports into Excel-friendly CSV files
            </h1>
            <p className="text-muted-foreground">
              Parquet files from BigQuery or data pipelines are often millions of rows: too big to open, and in a
              format Excel can&apos;t read. This converter splits them into CSV files you can actually use, keeping
              related rows together. No coding needed.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="lg">
                <Link href="/convert/">
                  Open the converter <ArrowRight />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href="/start/">
                  <BookOpen /> How to start
                </Link>
              </Button>
            </div>
          </div>
          <Card className="shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm font-medium">
                <FileSpreadsheet className="size-4" /> Example output
              </CardTitle>
              <CardDescription>sales_nov2026.parquet, 1.45 million rows, filtered by department</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1.5 font-mono text-xs">
                {EXAMPLE.map((name) => (
                  <li
                    key={name}
                    className={
                      name === "catalog.csv"
                        ? "rounded-md border border-dashed px-2 py-1.5 text-muted-foreground"
                        : "rounded-md border bg-muted/40 px-2 py-1.5"
                    }
                  >
                    {name}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-12">
        <h2 className="text-xl font-semibold tracking-tight">What it does</h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="space-y-2 rounded-xl border bg-card p-5">
              <Icon className="size-5 text-primary" />
              <h3 className="font-medium">{title}</h3>
              <p className="text-sm text-muted-foreground">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="border-t bg-muted/30">
        <div className="mx-auto max-w-5xl px-4 py-12">
          <h2 className="text-xl font-semibold tracking-tight">How it works</h2>
          <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step, i) => (
              <li key={step.title} className="space-y-2 rounded-xl border bg-background p-5">
                <span className="flex size-7 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                  {i + 1}
                </span>
                <h3 className="font-medium">{step.title}</h3>
                <p className="text-sm text-muted-foreground">{step.body}</p>
              </li>
            ))}
          </ol>
          <div className="mt-8 flex flex-col items-start gap-3 rounded-xl border bg-background p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-medium">First time here?</p>
              <p className="text-sm text-muted-foreground">
                Download the converter, double-click Start.bat, and you&apos;re ready in a few minutes.
              </p>
            </div>
            <Button asChild>
              <Link href="/start/">
                Set it up <ArrowRight />
              </Link>
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
