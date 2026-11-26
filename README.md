# Parquet to CSV Converter

Live site: https://parquet-csv-converter.pages.dev (download the converter from [How to start](https://parquet-csv-converter.pages.dev/start/)).

Converts large local Parquet files, or folders of Parquet shards such as BigQuery exports, into CSV parts. Parts respect row limits, filter values and intact groups (PRD v1.3). The website is only the interface: all reading, processing and writing happens on the user's PC through a local API on `127.0.0.1:8765`.

```
frontend/   Next.js + Tailwind + shadcn/ui, static export (out/) for Cloudflare Pages
backend/    FastAPI app, DuckDB planner/exporter, worker subprocess
app.py      launcher: per-launch token, single instance, opens the browser
Start.bat   one-click setup and launch for end users
tests/      acceptance tests (pytest)
```

## End users

1. Install Python 3.10+ (tick "Add python.exe to PATH").
2. Extract the approved ZIP to a writable folder, for example Documents.
3. Double-click `Start.bat`. The first launch creates `.venv` and installs the pinned `requirements.txt`. Later launches reuse it and reinstall only when `requirements.txt` changes.
4. The browser opens already paired. Allow local network access if the browser asks. Keep the converter window open while working.

Paths can be typed, pasted or picked with **Browse**. Browsers never reveal real file paths, so the Browse buttons ask the local converter to open a Windows Explorer dialog on the PC (Tk, or the Windows Forms dialog through PowerShell if Tk is missing). The dialog can only pick a path. The path is still checked against the approved folders like a typed one.

The first launch also creates a **Parquet to CSV Converter** desktop shortcut to `Start.bat`, with `converter.ico` as its icon. It does this once: a deleted shortcut is not recreated. If the folder moves, the shortcut is updated. Use `app.py --no-shortcut` to skip it.

Running `Start.bat` again while the converter is running reopens the browser with the existing session instead of starting a second backend.

## Configuration (`config.json`, optional)

Copy `config.example.json` to `config.json` next to `app.py`.

| Key | Default | Meaning |
| --- | --- | --- |
| `frontend_url` | local `web/` build if present, otherwise `http://localhost:3000/` | Site that `Start.bat` opens. Its origin is the trusted CORS origin. |
| `approved_roots` | the user profile folder | Only paths inside these folders are accepted. |
| `extra_trusted_origins` | `[]` | Additional exact origins. |
| `allow_network_paths` | `false` | UNC paths and mapped network drives are rejected unless this is `true`. |
| `memory_limit`, `threads` | `6GB`, `4` | DuckDB tuning for a 16 GB PC. |

**Local fallback:** the download ZIP always contains the compiled site in `web\`. Without a `frontend_url`, `Start.bat` opens `http://127.0.0.1:8765/convert/`, which FastAPI serves offline.

## Website and download

The site has three pages: `/` (what the converter is), `/convert/` (the converter) and `/start/` (setup guide with the download). `bun run build` in `frontend\` does three things:

1. `next build` creates the static site in `out\`.
2. It copies `out\` to `..\web` (offline copy).
3. It writes `out\downloads\ParquetConverter.zip`, served by the site at `/downloads/ParquetConverter.zip`. The ZIP contains `Start.bat`, `app.py`, `backend\`, the pinned requirements, `config.example.json`, `README.txt` and `web\`.

Set `PQCSV_FRONTEND_URL=https://<project>.pages.dev/` during the build (e.g. as a Cloudflare Pages environment variable) to include a `config.json` that makes `Start.bat` open the hosted site. For Cloudflare Pages: root directory `frontend`, build command `bun run build`, output directory `out`.

## Development

```
PS> python -m venv .venv
PS> .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
PS> .\.venv\Scripts\python.exe -m pytest
PS> .\.venv\Scripts\python.exe app.py --dev          # API + opens http://localhost:3000/convert/
PS> cd frontend; bun install; bun run dev
```

`bun run build` writes the static site to `frontend\out\` for Cloudflare Pages. `public\_headers` sets the CSP there.

## Output format

* **CSV:** UTF-8 without BOM, comma separator, one header row, standard double-quote quoting. Multiline fields are quoted.
* **NULL vs empty:** NULL is written as an empty, unquoted field (`a,,c`). An empty string is written as `""` (`a,"",c`). This applies to data parts and `_catalog.csv`.
* **Filenames:** `<prefix>_<filter value>_partXX.csv`. Numbering restarts at 01 for each filter value and widens beyond 99 parts. Without a filter: `<prefix>_partXX.csv`. Single CSV without a filter: `<prefix>.csv`. NULL and empty filter values become `__NULL__` and `__EMPTY__`. Windows-invalid characters become `_`. Values that collide case-insensitively or after sanitising get a stable `~<hash>` suffix. Raw values are always kept in `_catalog.csv`. The prefix must start with a letter or digit, so `_catalog.csv` always sorts above the data files in Windows Explorer.
* **`_catalog.csv`:** `file_name`, filter column, grouping columns, `row_count`. A source column named `file_name` or `row_count` is renamed `source_<name>`.
* **Row order:** the original row order is not preserved.
* **Excel:** values such as leading zeros or long IDs may be changed when a CSV is opened directly. Use Data > From Text/CSV to import them as text. Files with more than 1,048,575 rows trigger a warning.

## How a conversion runs

1. `/inspect` reads Parquet metadata only (schema, row count) and fingerprints every file's path, size and modified time.
2. `/preview` runs one aggregate scan of the filter and grouping columns. It applies sequential next-fit per filter value (deterministic order, NULLs last) and stores the plan in a DuckDB file.
3. `/jobs` starts `python -m backend.worker` (one at a time). The worker joins the source to the plan with NULL-safe equality and writes every part in a single `COPY … PARTITION_BY` into a hidden staging folder inside the destination.
4. The worker reads every part back to count its records and checks each against the plan and the total against the source. It re-checks the source fingerprint, writes `_catalog.csv` and renames everything into place. It never overwrites, and it rolls back if a rename fails.
5. Cancellation, failure or a crashed worker removes staging, and nothing is published.

## Security

* The API binds to `127.0.0.1` only. Requests must use a `Host` of `127.0.0.1:8765` or `localhost:8765`.
* CORS allows only the exact trusted origins and answers Private Network Access preflights.
* Every data endpoint requires the per-launch bearer token. The token is passed in the URL fragment, which is never sent to the web host.
* Paths are resolved (removing `..` traversal) and must sit inside an approved root. Device paths are refused, and network paths are refused by default.
* Column names are accepted only if they exist in the inspected schema, and are always quoted. No SQL is accepted from the client.
* There is no telemetry, no external fonts or scripts, and DuckDB extension auto-install is off.
