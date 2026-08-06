#!/usr/bin/env bun
// Self-contained CLI for searching jobs on LinkedIn's public jobs-guest endpoints,
// for any country/region (plus remote). No external CLI framework, so it runs
// anywhere `bun` is available with zero install beyond the repo clone.
//
// Personal use only. This reads LinkedIn's public job pages; automated access is
// against LinkedIn's Terms of Service, so keep volume low and do not use it
// commercially or for bulk data collection. Run it on your own responsibility.

import { runSearch, searchData, type SearchOpts } from "./commands/search.js"
import { fetchDetail, runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  const alias: Record<string, string> = { q: "query", l: "location", n: "limit" }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a.startsWith("--") || a.startsWith("-")) {
      const key = alias[a.replace(/^-+/, "")] ?? a.replace(/^-+/, "")
      const next = argv[i + 1]
      if (next === undefined || next.startsWith("-")) {
        flags[key] = true
      } else {
        flags[key] = next
        i++
      }
    } else {
      ;(flags._ as string[]).push(a)
    }
  }
  return flags
}

const HELP = `linkedin-cli — search jobs on LinkedIn (any country/region, plus remote)

USAGE
  bun run src/cli.ts search --location "<place>" [flags]
  bun run src/cli.ts batch --delay-ms <milliseconds> < requests.jsonl
  bun run src/cli.ts detail <id|url> [--format json|plain]
  bun run src/cli.ts detail-batch --delay-ms <milliseconds> < requests.jsonl

SEARCH FLAGS
  --location, -l <text>   Location to search. REQUIRED. e.g. "Mumbai, Maharashtra, India",
                          "Berlin, Germany", "London, United Kingdom", or "Remote".
  --query, -q <text>      Keywords (job title, skill, or role). Recommended.
  --jobage <days>         Posted within N days: 1, 7, 14, 30. Default: all.
  --remote <mode>         remote | hybrid | onsite. Filter by workplace type.
  --page <n>              1-indexed page (10 results/page). Default 1.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

EXAMPLES
  bun run src/cli.ts search -q "data engineer" -l "Bengaluru, Karnataka, India" --jobage 30 --format table
  bun run src/cli.ts search -q "product manager" -l "Berlin, Germany" --remote remote --format table
  bun run src/cli.ts search -q "paralegal" -l "Remote" --format table
  bun run src/cli.ts detail 4300011451 --format plain

Personal use only — uses LinkedIn's public pages; keep volume low (LinkedIn ToS).
`

interface BatchRequest {
  request_id?: unknown
  query?: unknown
  location?: unknown
  jobage?: unknown
  remote?: unknown
  page?: unknown
  limit?: unknown
}

interface DetailBatchRequest {
  request_id?: unknown
  job_id?: unknown
  id?: unknown
  url?: unknown
}

function batchNumber(raw: unknown, fallback: number): number {
  if (typeof raw === "number" && Number.isFinite(raw)) return raw
  if (typeof raw === "string") {
    const parsed = Number(raw)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function batchSleep(ms: number): Promise<void> {
  return ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve()
}

/** Keep one LinkedIn process alive; requests for this portal are serial. */
async function runBatch(delayMs: number): Promise<number> {
  const input = await Bun.stdin.text()
  const lines = input.split(/\r?\n/).filter((line) => line.trim())
  for (let index = 0; index < lines.length; index++) {
    if (index > 0) await batchSleep(delayMs)
    let requestId = `line-${index + 1}`
    try {
      const request = JSON.parse(lines[index]) as BatchRequest
      if (!request || typeof request !== "object") throw new Error("request must be a JSON object")
      if (request.request_id !== undefined) requestId = String(request.request_id)
      const location = typeof request.location === "string" ? request.location : "Hong Kong"
      const payload = await searchData({
        query: typeof request.query === "string" ? request.query : undefined,
        location,
        jobage: batchNumber(request.jobage, 9999),
        remote: typeof request.remote === "string" ? request.remote : undefined,
        page: Math.max(1, Math.trunc(batchNumber(request.page, 1))),
        limit: Math.max(1, Math.trunc(batchNumber(request.limit, 30))),
        format: "json",
      })
      process.stdout.write(JSON.stringify({ request_id: requestId, ok: true, payload }) + "\n")
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      process.stdout.write(JSON.stringify({ request_id: requestId, ok: false, error }) + "\n")
    }
  }
  return 0
}

/** Keep one Bun process alive while fetching LinkedIn detail pages serially. */
async function runDetailBatch(delayMs: number): Promise<number> {
  const input = await Bun.stdin.text()
  const lines = input.split(/\r?\n/).filter((line) => line.trim())
  for (let index = 0; index < lines.length; index++) {
    if (index > 0) await batchSleep(delayMs)
    let requestId = `line-${index + 1}`
    try {
      const request = JSON.parse(lines[index]) as DetailBatchRequest
      if (!request || typeof request !== "object") throw new Error("request must be a JSON object")
      if (request.request_id !== undefined) requestId = String(request.request_id)
      const inputId = request.job_id ?? request.id ?? request.url
      if (typeof inputId !== "string" || !inputId.trim()) throw new Error("job_id is required")
      const payload = await fetchDetail(inputId)
      process.stdout.write(JSON.stringify({ request_id: requestId, ok: true, payload }) + "\n")
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      process.stdout.write(JSON.stringify({ request_id: requestId, ok: false, error }) + "\n")
    }
  }
  return 0
}

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  if (cmd === "search") {
    const location = typeof flags.location === "string" ? flags.location : undefined
    if (!location) {
      process.stderr.write(
        JSON.stringify({
          error: 'the --location/-l flag is required (e.g. -l "Mumbai, Maharashtra, India", -l "Berlin, Germany", or -l "Remote")',
          code: "NO_LOCATION",
        }) + "\n",
      )
      return 1
    }
    const fmt = (flags.format as string) || "json"

    const parseIntFlag = (name: string, raw: string | boolean | string[]): number | null => {
      const val = parseInt(raw as string, 10)
      if (isNaN(val)) {
        process.stderr.write(JSON.stringify({ error: `--${name} must be a number, got "${raw}"`, code: "BAD_ARG" }) + "\n")
        return null
      }
      return val
    }

    if (flags.jobage !== undefined) {
      const v = parseIntFlag("jobage", flags.jobage)
      if (v === null) return 1
      flags.jobage = String(v)
    }
    if (flags.page !== undefined) {
      const v = parseIntFlag("page", flags.page)
      if (v === null) return 1
      flags.page = String(v)
    }
    if (flags.limit !== undefined) {
      const v = parseIntFlag("limit", flags.limit)
      if (v === null) return 1
      flags.limit = String(v)
    }

    const opts: SearchOpts = {
      query: typeof flags.query === "string" ? flags.query : undefined,
      location,
      jobage: flags.jobage ? parseInt(flags.jobage as string, 10) : 9999,
      remote: typeof flags.remote === "string" ? flags.remote : undefined,
      page: flags.page ? Math.max(1, parseInt(flags.page as string, 10)) : 1,
      limit: flags.limit ? parseInt(flags.limit as string, 10) : undefined,
      format: (["json", "table", "plain"].includes(fmt) ? fmt : "json") as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "batch") {
    const rawDelay = flags["delay-ms"]
    const parsedDelay = typeof rawDelay === "string" ? Number(rawDelay) : 0
    const delayMs = Number.isFinite(parsedDelay) ? Math.max(0, Math.trunc(parsedDelay)) : 0
    return runBatch(delayMs)
  }

  if (cmd === "detail-batch") {
    const rawDelay = flags["delay-ms"]
    const parsedDelay = typeof rawDelay === "string" ? Number(rawDelay) : 0
    const delayMs = Number.isFinite(parsedDelay) ? Math.max(0, Math.trunc(parsedDelay)) : 0
    return runDetailBatch(delayMs)
  }

  if (cmd === "detail") {
    const id = (flags._ as string[])[1]
    if (!id) {
      process.stderr.write(JSON.stringify({ error: "detail requires an <id|url>", code: "NO_ID" }) + "\n")
      return 1
    }
    const fmt = (flags.format as string) || "json"
    const opts: DetailOpts = {
      id,
      format: (fmt === "plain" ? "plain" : "json") as DetailOpts["format"],
    }
    return runDetail(opts)
  }

  process.stderr.write(JSON.stringify({ error: `Unknown command "${cmd}"`, code: "BAD_CMD" }) + "\n")
  return 1
}

main().then((code) => process.exit(code))
