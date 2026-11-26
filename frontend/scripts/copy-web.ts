// Copies the static export (out/) to ../web, which FastAPI serves when the hosted site is blocked.
import { cpSync, existsSync, rmSync } from "node:fs";
import { resolve } from "node:path";

// Run via `bun run build:local` from the frontend folder.
const src = resolve(process.cwd(), "out");
const dest = resolve(process.cwd(), "..", "web");
if (!existsSync(src)) throw new Error("out/ not found: run `bun run build` first");
if (existsSync(dest)) rmSync(dest, { recursive: true });
cpSync(src, dest, { recursive: true });
console.log(`Copied ${src} -> ${dest}`);
