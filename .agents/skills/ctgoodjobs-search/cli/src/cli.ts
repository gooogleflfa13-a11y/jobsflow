#!/usr/bin/env bun
// Self-contained CLI for searching CTgoodjobs Hong Kong's public job search API.
// Zero runtime dependencies — runs anywhere `bun` is available.
//
// Data source: https://api01.ctgoodjobs.hk/job/api/jobs/search
// The API requires session headers (sid, channel-id, visitor-id) that a real
// browser obtains as cookies. This CLI reads them from env vars or bootstraps
// them from the homepage. See url-reference.md.

import { runSearch, type SearchOpts } from "./commands/search.js"
import { runDetail, type DetailOpts } from "./commands/detail.js"

interface Flags {
  _: string[]
  [k: string]: string | boolean | string[]
}

const ALIAS: Record<string, string> = { q: "query", n: "limit" }

function parseFlags(argv: string[]): Flags {
  const flags: Flags = { _: [] }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (!a.startsWith("-")) {
      ;(flags._ as string[]).push(a)
      continue
    }
    const name = a.replace(/^-+/, "")
    const key = ALIAS[name] ?? name
    const next = argv[i + 1]
    let value: string | boolean = true
    if (next !== undefined && !next.startsWith("-")) {
      value = next
      i++
    }
    flags[key] = value
  }
  return flags
}

function stringFlag(raw: string | boolean | string[] | undefined): string | undefined {
  return typeof raw === "string" ? raw : undefined
}

function parseIntOr(raw: string | boolean | string[] | undefined, fallback: number): number {
  if (raw === undefined) return fallback
  const v = parseInt(raw as string, 10)
  return isNaN(v) ? fallback : v
}

const HELP = `ctgoodjobs-cli — search CTgoodjobs Hong Kong job listings (https://www.ctgoodjobs.hk)

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [--jobage <days>] [--page <n>] [--limit <n>] [--format json|table|plain]
  bun run src/cli.ts detail <id|url> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>    Keywords (title, skill, role, company). Optional.
  --jobage <days>       Posted within N days (narrowed client-side by publish date).
  --page <n>            1-indexed page. Default 1.
  --limit, -n <n>       Cap results emitted (client-side). Default 30.
  --format <fmt>        json (default) | table | plain.

DETAIL
  <id|url>              A numeric CTgoodjobs job id (e.g. 10189838) or a
                        https://jobs.ctgoodjobs.hk/job/<id> URL.

EXAMPLES
  bun run src/cli.ts search -q "paralegal" --jobage 14 --format table
  bun run src/cli.ts search -q "legal counsel" --limit 10 --format json
  bun run src/cli.ts detail 10189838 --format plain

AUTHENTICATION
  The search API requires session headers (sid, channel-id, visitor-id) that a
  real browser obtains as cookies. Set CTGOOD_SID and CTGOOD_VISITOR_ID (and
  optionally CTGOOD_CHANNEL_ID, default "1") from a browser session, or leave
  them unset to bootstrap fresh cookies from www.ctgoodjobs.hk. Personal use
  only — keep volume low.
`

async function main(): Promise<number> {
  const argv = process.argv.slice(2)
  const flags = parseFlags(argv)
  const cmd = (flags._ as string[])[0]

  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP)
    return cmd ? 0 : 1
  }

  if (cmd === "search") {
    const fmt = (flags.format as string) || "json"
    const opts: SearchOpts = {
      query: stringFlag(flags.query),
      jobage: parseIntOr(flags.jobage, 9999),
      page: Math.max(1, parseIntOr(flags.page, 1)),
      limit: flags.limit !== undefined ? Math.max(1, parseIntOr(flags.limit, 30)) : 30,
      format: (["json", "table", "plain"].includes(fmt) ? fmt : "json") as SearchOpts["format"],
    }
    return runSearch(opts)
  }

  if (cmd === "detail") {
    const id = (flags._ as string[])[1]
    if (!id) {
      process.stderr.write(JSON.stringify({ error: "detail requires a <id|url>", code: "NO_ID" }) + "\n")
      return 1
    }
    const fmt = (flags.format as string) || "json"
    const opts: DetailOpts = { id, format: fmt === "plain" ? "plain" : "json" }
    return runDetail(opts)
  }

  process.stderr.write(JSON.stringify({ error: `Unknown command "${cmd}"`, code: "BAD_CMD" }) + "\n")
  return 1
}

main().then((code) => process.exit(code))
