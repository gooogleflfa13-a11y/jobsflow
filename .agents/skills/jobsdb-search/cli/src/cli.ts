#!/usr/bin/env bun
// Self-contained CLI for searching JobsDB Hong Kong's public REST search API.
// Zero runtime dependencies — runs anywhere `bun` is available.
//
// Data source: https://hk.jobsdb.com/api/jobsearch/v5/search (Seek "HK-Main"
// market). No authentication, no browser; returns JSON. See url-reference.md.

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

const HELP = `jobsdb-cli — search JobsDB Hong Kong job listings (https://hk.jobsdb.com)

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [--jobage <days>] [--page <n>] [--limit <n>] [--format json|table|plain]
  bun run src/cli.ts detail <id|url> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>    Keywords (title, skill, role, company). Optional.
  --jobage <days>       Posted within N days: 7 | 14 | 30. Omit for all postings.
  --page <n>            1-indexed page. Default 1.
  --limit, -n <n>       Cap results emitted (client-side). Default 30.
  --format <fmt>        json (default) | table | plain.

DETAIL
  <id|url>              A numeric JobsDB job id (e.g. 93369834) or a
                        https://hk.jobsdb.com/job/<id> URL.

EXAMPLES
  bun run src/cli.ts search -q "paralegal" --jobage 14 --format table
  bun run src/cli.ts search -q "legal counsel" --limit 10 --format json
  bun run src/cli.ts detail 93369834 --format plain

No authentication required. Personal use only — keep volume low; the endpoint is
public but Seek/Cloudflare may rate-limit bulk access.
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
