import { resolveHeaders, searchPost, toResult, type JobResult } from "../helpers.js"

export interface SearchOpts {
  query?: string
  jobage: number // days; 0/9999 = all. CTgoodjobs daterange is coarse; we narrow client-side.
  page: number
  limit?: number
  format: "json" | "table" | "plain"
}

function renderTable(cards: JobResult[]): string {
  if (cards.length === 0) return "No results."
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 40).padEnd(40)
    const company = (c.company || "—").slice(0, 26).padEnd(26)
    const loc = (c.location || "—").slice(0, 22).padEnd(22)
    const date = (c.date || "—").slice(0, 10)
    return `${c.id.padEnd(10)} ${title} ${company} ${loc} ${date}`
  })
  const header =
    "ID".padEnd(10) + " " + "TITLE".padEnd(40) + " " + "COMPANY".padEnd(26) + " " + "LOCATION".padEnd(22) + " DATE"
  return [header, "-".repeat(header.length), ...rows].join("\n")
}

export async function runSearch(opts: SearchOpts): Promise<number> {
  try {
    const headers = await resolveHeaders()
    // CTgoodjobs search is a POST. `keyword` is free text; pageSize caps the page.
    const body: Record<string, unknown> = {
      PagingInputs: {
        page: opts.page,
        pageSize: opts.limit && opts.limit > 0 ? Math.min(opts.limit, 100) : 30,
      },
    }
    if (opts.query) body.keyword = opts.query

    const env = await searchPost(headers, body)
    let cards = (env.data.jobs || []).map(toResult)

    // `--jobage` is not a first-class server filter here, so narrow by publish
    // date on the client (based on the ISO `timestamp` when available).
    if (opts.jobage && opts.jobage < 9999) {
      const cutoff = Date.now() - opts.jobage * 86400_000
      cards = cards.filter((c) => {
        if (!c.date) return true
        const t = Date.parse(c.date)
        return isNaN(t) ? true : t >= cutoff
      })
    }
    if (opts.limit !== undefined && opts.limit >= 0) cards = cards.slice(0, opts.limit)

    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + "\n")
    } else if (opts.format === "plain") {
      process.stdout.write(
        cards
          .map(
            (c) =>
              `${c.title}\n  ${c.company || "—"} · ${c.location || "—"} · ${c.date || "—"}\n  id: ${c.id}\n  ${c.url}`,
          )
          .join("\n\n") + "\n",
      )
    } else {
      process.stdout.write(
        JSON.stringify(
          {
            meta: { count: cards.length, page: opts.page, total: env.data.meta.jobsTotal ?? env.data.total ?? null },
            results: cards,
          },
          null,
          2,
        ) + "\n",
      )
    }
    return 0
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    process.stderr.write(JSON.stringify({ error: msg, code: "SEARCH_FAILED" }) + "\n")
    return 1
  }
}
