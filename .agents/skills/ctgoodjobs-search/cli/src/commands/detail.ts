import {
  resolveHeaders,
  searchPost,
  toResult,
  normalizeId,
  writeError,
  type JobResult,
} from "../helpers.js"

export interface DetailOpts {
  id: string // a numeric job id or a /job/<id> URL
  format: "json" | "plain"
}

/**
 * CTgoodjobs' public detail *page* (jobs.ctgoodjobs.hk/job/<id>) is behind an
 * AWS WAF / client-rendered SPA, so a plain GET returns the challenge shell, not
 * the job body. There is no documented single-job REST endpoint either.
 *
 * Instead, `detail` re-queries the search API with a `jobIds` filter
 * (`{"jobIds":["<id>"]}`), which returns exactly the one matching job (total: 1).
 * This yields the rich card fields already in the search response (title,
 * company, location, salary, areas, employment type, career level, date, URL)
 * without a headless browser. See url-reference.md.
 */
export async function runDetail(opts: DetailOpts): Promise<number> {
  const id = normalizeId(opts.id)
  if (!id) {
    writeError(`could not parse a CTgoodjobs job id from "${opts.id}"`, "BAD_ID")
    return 1
  }
  try {
    const headers = await resolveHeaders()
    const env = await searchPost(headers, {
      PagingInputs: { page: 1, pageSize: 5 },
      jobIds: [id],
    })
    const match = (env.data.jobs || []).map(toResult).find((j: JobResult) => j.id === id)
    if (!match) {
      writeError("job not found", "NOT_FOUND")
      return 1
    }

    if (opts.format === "plain") {
      const lines = [
        match.title,
        `${match.company ?? "—"} · ${match.location ?? "—"}`,
        match.date ? `Posted: ${match.date.slice(0, 10)}` : "",
        match.salary ? `Salary: ${match.salary}` : "",
        match.areas.length ? `Areas: ${match.areas.join(", ")}` : "",
        match.employmentTypes.length ? `Employment: ${match.employmentTypes.join(", ")}` : "",
        match.careerLevels.length ? `Level: ${match.careerLevels.join(", ")}` : "",
        match.teaser ? `\n${match.teaser}` : "",
        "",
        `URL: ${match.url}`,
        `id: ${match.id}`,
      ].filter((l) => l !== "")
      process.stdout.write(lines.join("\n") + "\n")
    } else {
      process.stdout.write(JSON.stringify(match, null, 2) + "\n")
    }
    return 0
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    writeError(msg, "DETAIL_FAILED")
    return 1
  }
}
