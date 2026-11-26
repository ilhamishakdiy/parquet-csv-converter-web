import type { Metadata } from "next";
import { SiteHeader } from "@/components/site-header";
import { TokenCapture } from "@/components/token-capture";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

export const metadata: Metadata = {
  title: "Parquet to CSV Converter",
  description: "Convert large local Parquet files into CSV parts. All processing stays on your PC.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <TokenCapture />
        <TooltipProvider>
          <SiteHeader />
          <main className="flex flex-1 flex-col">{children}</main>
          <footer className="border-t bg-background">
            <div className="mx-auto max-w-5xl px-4 py-4 text-xs text-muted-foreground">
              Your data is processed only on your own PC. This website never receives your files.
            </div>
          </footer>
        </TooltipProvider>
      </body>
    </html>
  );
}
