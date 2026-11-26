// Builds the end-user download: out/downloads/ParquetConverter.zip (served by the site at
// /downloads/ParquetConverter.zip) and a copy in ../web/downloads for the offline site.
// Run from the frontend folder after `next build` and `bun scripts/copy-web.ts`.
//
// Set PQCSV_FRONTEND_URL (e.g. https://<project>.pages.dev/) at build time to include a
// config.json that makes Start.bat open the hosted site; otherwise it opens the offline copy.
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import { deflateRawSync } from "node:zlib";

const ROOT = resolve(process.cwd(), "..");
const OUT_FILE = resolve(process.cwd(), "out", "downloads", "ParquetConverter.zip");
const WEB_COPY = resolve(ROOT, "web", "downloads", "ParquetConverter.zip");
const TOP = "ParquetConverter/";

const README = `Parquet to CSV Converter
========================

1. Install Python 3.10 or newer (tick "Add python.exe to PATH").
2. Extract this ZIP (right-click > Extract All...) to a local folder you can write to.
   Recommended: C:\\Users\\<your name>\\ParquetConverter
   Avoid: Program Files (needs admin), network drives, OneDrive-synced folders,
   and running Start.bat from inside the ZIP without extracting.
3. Double-click Start.bat. The first launch installs what it needs (1-2 minutes).
4. The converter page opens in your browser. Allow local network access if asked.

Keep the black window open while you work; closing it stops the converter.
Your files are processed only on this PC. Nothing is uploaded.

IT: copy config.example.json to config.json to set approved folders or the website URL.
`;

// --- files ------------------------------------------------------------------
function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (name === "__pycache__") return [];
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

const entries: { name: string; data: Buffer; mtime: Date }[] = [];
function add(rel: string, data?: Buffer) {
  const full = join(ROOT, rel);
  let bytes = data ?? readFileSync(full);
  if (rel.toLowerCase().endsWith(".bat")) {
    bytes = Buffer.from(bytes.toString("utf8").replace(/\r?\n/g, "\r\n"), "utf8"); // cmd.exe needs CRLF
  }
  entries.push({ name: TOP + rel.split(sep).join("/"), data: bytes, mtime: data ? new Date() : statSync(full).mtime });
}

for (const f of ["Start.bat", "app.py", "requirements.txt", "config.example.json"]) add(f);
for (const f of walk(join(ROOT, "backend")).filter((p) => p.endsWith(".py"))) add(relative(ROOT, f));
const web = join(ROOT, "web");
if (existsSync(web)) {
  for (const f of walk(web).filter((p) => !p.includes(`${sep}downloads${sep}`))) add(relative(ROOT, f));
} else {
  console.warn("warning: ../web not found; the ZIP will not contain the offline site");
}
add("README.txt", Buffer.from(README.replace(/\n/g, "\r\n"), "utf8"));
const frontendUrl = process.env.PQCSV_FRONTEND_URL;
if (frontendUrl) add("config.json", Buffer.from(JSON.stringify({ frontend_url: frontendUrl }, null, 2) + "\r\n"));

// --- minimal ZIP writer (deflate, UTF-8 names) --------------------------------
const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(buf: Buffer): number {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function dos(d: Date): [number, number] {
  const time = (d.getHours() << 11) | (d.getMinutes() << 5) | Math.floor(d.getSeconds() / 2);
  const date = ((Math.max(d.getFullYear(), 1980) - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
  return [time, date];
}

const locals: Buffer[] = [];
const centrals: Buffer[] = [];
let offset = 0;
for (const e of entries) {
  const name = Buffer.from(e.name, "utf8");
  const comp = deflateRawSync(e.data, { level: 9 });
  const crc = crc32(e.data);
  const [time, date] = dos(e.mtime);

  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4);
  local.writeUInt16LE(0x0800, 6); // UTF-8 names
  local.writeUInt16LE(8, 8); // deflate
  local.writeUInt16LE(time, 10);
  local.writeUInt16LE(date, 12);
  local.writeUInt32LE(crc, 14);
  local.writeUInt32LE(comp.length, 18);
  local.writeUInt32LE(e.data.length, 22);
  local.writeUInt16LE(name.length, 26);
  local.writeUInt16LE(0, 28);
  locals.push(local, name, comp);

  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt16LE(20, 4);
  central.writeUInt16LE(20, 6);
  central.writeUInt16LE(0x0800, 8);
  central.writeUInt16LE(8, 10);
  central.writeUInt16LE(time, 12);
  central.writeUInt16LE(date, 14);
  central.writeUInt32LE(crc, 16);
  central.writeUInt32LE(comp.length, 20);
  central.writeUInt32LE(e.data.length, 24);
  central.writeUInt16LE(name.length, 28);
  central.writeUInt32LE(offset, 42);
  centrals.push(central, name);

  offset += local.length + name.length + comp.length;
}
const cd = Buffer.concat(centrals);
const end = Buffer.alloc(22);
end.writeUInt32LE(0x06054b50, 0);
end.writeUInt16LE(entries.length, 8);
end.writeUInt16LE(entries.length, 10);
end.writeUInt32LE(cd.length, 12);
end.writeUInt32LE(offset, 16);

const zip = Buffer.concat([...locals, cd, end]);
mkdirSync(resolve(OUT_FILE, ".."), { recursive: true });
writeFileSync(OUT_FILE, zip);
if (existsSync(web)) {
  mkdirSync(resolve(WEB_COPY, ".."), { recursive: true });
  copyFileSync(OUT_FILE, WEB_COPY);
}
console.log(`Wrote ${OUT_FILE} (${entries.length} files, ${(zip.length / 1024).toFixed(0)} KB)${frontendUrl ? ` with frontend_url=${frontendUrl}` : ""}`);
