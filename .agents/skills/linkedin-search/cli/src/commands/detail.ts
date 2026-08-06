import { DETAIL_URL, htmlFetch, parseJobDetail, writeError } from "../helpers.js"

export interface DetailOpts {
  id: string
  format: "json" | "plain"
}

/** Accept a raw job ID, a job-view URL, or a job URN. */
export function normalizeId(input: string): string | null {
  const urn = input.match(/urn:li:jobPosting:(\d+)/)
  if (urn) return urn[1]
  const url = input.match(/-(\d{6,})(?:\?|$)/) || input.match(/\/(\d{6,})(?:\?|$)/)
  if (url) return url[1]
  const bare = input.match(/^\d{6,}$/)
  if (bare) return input
  return null
}

/** Fetch and parse one detail record without writing to stdout. */
export async function fetchDetail(input: string): Promise<ReturnType<typeof parseJobDetail>> {
  const id = normalizeId(input)
  if (!id) throw new Error(`Could not parse a job ID from "${input}"`)
  const html = await htmlFetch(`${DETAIL_URL}/${id}`)
  if (!html) throw new Error("Job not found")
  return parseJobDetail(html, id)
}

export async function runDetail(opts: DetailOpts): Promise<number> {
  const id = normalizeId(opts.id)
  if (!id) {
    writeError(`Could not parse a job ID from "${opts.id}"`, "BAD_ID")
    return 1
  }
  try {
    const job = await fetchDetail(id)

    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"}`,
        "",
        job.seniority ? `Seniority: ${job.seniority}` : "",
        job.employmentType ? `Employment: ${job.employmentType}` : "",
        job.jobFunction ? `Function: ${job.jobFunction}` : "",
        job.industries ? `Industries: ${job.industries}` : "",
        "",
        job.description || "(no description)",
        "",
        `URL: ${job.url}`,
        job.applyUrl ? `Apply: ${job.applyUrl}` : "",
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(job, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    writeError(message, message === "Job not found" ? "NOT_FOUND" : "DETAIL_FAILED")
    return 1
  }
}
