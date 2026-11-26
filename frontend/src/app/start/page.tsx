import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowRight, Download, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "How to start | Parquet to CSV Converter",
};

const ZIP_PATH = "/downloads/ParquetConverter.zip";
const PYTHON_URL = "https://www.python.org/downloads/";
// Official Python Install Manager (per-user MSIX). Update when python.org publishes a new version.
const PYTHON_MANAGER_URL = "https://www.python.org/ftp/python/pymanager/python-manager-26.4.msix";

function PythonLink({ children = "python.org/downloads" }: { children?: ReactNode }) {
  return (
    <a className="underline" href={PYTHON_URL} target="_blank" rel="noreferrer">
      {children} <ExternalLink className="inline size-3" />
    </a>
  );
}

const REQUIREMENTS: [string, ReactNode][] = [
  ["Windows 10 or 11", "Administrator rights are not needed."],
  [
    "Python 3.10 or newer",
    <>
      A one-time install from the official site, <PythonLink />. Tick “Add python.exe to PATH” during setup.
    </>,
  ],
  ["16 GB RAM recommended", "For 5–8 GB Parquet files. Smaller files work with less."],
  ["Free disk space", "About 150 MB for the converter, plus room for the CSV output (usually 3–5× the Parquet size)."],
  ["Chrome or Edge", "Allow access to devices on your local network if asked."],
];

const TROUBLE: { q: string; a: ReactNode }[] = [
  {
    q: "“Python 3.10 or newer was not found”",
    a: (
      <>
        Install Python from your company software portal or the official site, <PythonLink />, and tick <strong>Add python.exe to PATH</strong>. Then double-click Start.bat again.
      </>
    ),
  },
  {
    q: "“Installing dependencies failed”",
    a: "The PC could not download the Python packages. Check your internet or VPN connection, or ask IT whether the Python package repository (PyPI) is blocked.",
  },
  {
    q: "The page says “Not connected”",
    a: "The converter is not running. Double-click Start.bat and keep its black window open. The page reconnects by itself.",
  },
  {
    q: "The page says “Not paired” or “older version”",
    a: "Close the black converter window, then double-click Start.bat again. It reopens the page already paired with the new session.",
  },
  {
    q: "“Port 8765 is used by another program”",
    a: "Another program is using the converter's port. Close it or restart the PC, then double-click Start.bat again.",
  },
  {
    q: "“The path is outside the approved folders”",
    a: "For safety the converter only reads and writes inside approved folders (your user folder by default). Move the data there, or ask IT to add a folder to config.json.",
  },
  {
    q: "The Browse window doesn't appear",
    a: "It may have opened behind the browser. Check the taskbar for a Python window and click it.",
  },
];

export default function StartPage() {
  return (
    <div className="flex-1">
      <section className="border-b bg-muted/30">
        <div className="mx-auto max-w-5xl space-y-4 px-4 py-12">
          <h1 className="text-3xl font-semibold tracking-tight">How to start</h1>
          <p className="max-w-2xl text-muted-foreground">
            The converter runs on your own PC, so it needs a one-time setup. It takes about five minutes, and after
            that it&apos;s one double-click.
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Button asChild size="lg">
              <a href={ZIP_PATH} download>
                <Download /> Download ParquetConverter.zip
              </a>
            </Button>
            <Button asChild size="lg" variant="outline">
              <a href={PYTHON_MANAGER_URL}>
                <Download /> Download Python (python.org)
              </a>
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            The ZIP contains Start.bat, the converter program and an offline copy of this website. Python (the official
            Python Install Manager, about 96 MB) is needed once; skip it if Python 3.10+ is already installed.
          </p>
        </div>
      </section>

      <div className="mx-auto max-w-5xl space-y-12 px-4 py-12">
        <section>
          <h2 className="text-xl font-semibold tracking-tight">What you need</h2>
          <dl className="mt-4 divide-y rounded-xl border bg-card">
            {REQUIREMENTS.map(([title, body]) => (
              <div key={title} className="grid gap-1 px-5 py-3 sm:grid-cols-[14rem_1fr]">
                <dt className="font-medium">{title}</dt>
                <dd className="text-sm text-muted-foreground">{body}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section>
          <h2 className="text-xl font-semibold tracking-tight">First launch</h2>
          <ol className="mt-4 space-y-4">
            <Step n={1} title="Install Python (once)">
              <a className="underline" href={PYTHON_MANAGER_URL}>
                Download the Python Install Manager
              </a>{" "}
              (official, from python.org, about 96 MB), double-click it and choose <strong>Install</strong>. No
              administrator rights needed. The first time you run Start.bat it downloads Python itself; if it asks a
              question in the black window, answer it there.
              <span className="mt-2 block">
                Prefer the classic installer, or the file above is blocked? Get Python 3.10 or newer from{" "}
                <PythonLink /> or your company software portal, and tick <strong>Add python.exe to PATH</strong> on the
                installer&apos;s first screen. Already have Python 3.10+? Skip this step.
              </span>
            </Step>
            <Step n={2} title="Download and extract the converter">
              <a className="underline" href={ZIP_PATH} download>
                Download ParquetConverter.zip
              </a>
              , right-click it and choose <strong>Extract All…</strong>. Any local folder you can write to works. We
              recommend{" "}
              <code className="rounded bg-muted px-1 font-mono text-xs">C:\Users\&lt;your name&gt;\ParquetConverter</code>.
              <span className="mt-2 block">Avoid these locations:</span>
              <span className="mt-1 block pl-3">
                • <strong>Program Files</strong>: needs administrator rights.
                <br />• <strong>Network drives</strong>: slow, and may be blocked.
                <br />• <strong>OneDrive-synced folders</strong> (often Desktop and Documents on work laptops): OneDrive
                would upload the converter&apos;s files.
                <br />• <strong>Inside the ZIP</strong>: Start.bat must be run from the extracted folder.
              </span>
              <span className="mt-2 block">
                The first launch adds about 150 MB to this folder. Where you extract it does not limit which data you
                can convert.
              </span>
            </Step>
            <Step n={3} title="Double-click Start.bat">
              A black window opens. The first launch installs what the converter needs, which takes a minute or two,
              and adds a <strong>Parquet to CSV Converter</strong> shortcut to your desktop. If Windows SmartScreen
              appears, choose <strong>More info → Run anyway</strong> if your IT policy allows it.
            </Step>
            <Step n={4} title="Allow local network access">
              The converter page opens in your browser. If the browser asks to access devices on your local network,
              choose <strong>Allow</strong>. This only lets the page talk to the converter on your own PC.
            </Step>
            <Step n={5} title="Convert">
              When the badge shows <strong>Converter connected</strong>, follow the four steps on the page.
            </Step>
          </ol>
        </section>

        <section>
          <h2 className="text-xl font-semibold tracking-tight">Every time after that</h2>
          <ul className="mt-4 list-disc space-y-2 pl-5 text-sm">
            <li>
              Double-click the <strong>Parquet to CSV Converter</strong> shortcut on your desktop (or Start.bat). It
              starts in seconds and opens the converter page.
            </li>
            <li>
              Keep the black window open while you work. Closing it stops the converter.
            </li>
            <li>
              Deleted the shortcut? It won&apos;t come back by itself. Right-click Start.bat →{" "}
              <strong>Send to → Desktop (create shortcut)</strong> to add it again. If you extract a new version to a
              different folder, the shortcut is updated automatically.
            </li>
            <li>When a new version is released, download the new ZIP and extract it over the old folder.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold tracking-tight">Troubleshooting</h2>
          <div className="mt-4 space-y-2">
            {TROUBLE.map((t) => (
              <details key={t.q} className="group rounded-xl border bg-card px-5 py-3">
                <summary className="cursor-pointer font-medium">{t.q}</summary>
                <p className="mt-2 text-sm text-muted-foreground">{t.a}</p>
              </details>
            ))}
          </div>
        </section>

        <div className="flex flex-col items-start gap-3 rounded-xl border bg-muted/30 p-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="font-medium">Converter running?</p>
          <Button asChild>
            <Link href="/convert/">
              Open the converter <ArrowRight />
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="flex gap-4 rounded-xl border bg-card p-5">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
        {n}
      </span>
      <div className="space-y-1">
        <h3 className="font-medium">{title}</h3>
        <div className="text-sm text-muted-foreground">{children}</div>
      </div>
    </li>
  );
}
