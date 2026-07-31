// Data source: CTgoodjobs Hong Kong job search API (api01.ctgoodjobs.hk).
// Endpoint: https://api01.ctgoodjobs.hk/job/api/jobs/search
//
// Authentication: the API requires three headers that are normally issued by a
// real browser session as cookies — `sid`, `channel-id`, and `visitor-id`.
// This skill reads them from environment variables (CTGOOD_SID,
// CTGOOD_CHANNEL_ID, CTGOOD_VISITOR_ID) and, if unset, fetches a fresh homepage
// to obtain them. See url-reference.md for the full schema and why headers (not
// body fields) are the binding mechanism.

import { requestSignal, retryDelayMs } from "../../../_shared/http-policy.ts"

export const SEARCH_BASE = "https://api01.ctgoodjobs.hk/job/api/jobs/search"
export const JOB_URL_PREFIX = "https://jobs.ctgoodjobs.hk/job/"
export const HOMEPAGE = "https://www.ctgoodjobs.hk/"

export function writeError(error: string, code: string): void {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
}

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

/**
 * Resolve the required API headers. Prefers explicit env vars; otherwise loads
 * the homepage once to capture the cookies CTgoodjobs sets (sid, visitor_id).
 * channel-id defaults to "1" (web channel).
 */
export async function resolveHeaders(): Promise<Record<string, string>> {
  const sid = process.env.CTGOOD_SID
  const visitorId = process.env.CTGOOD_VISITOR_ID
  const channelId = process.env.CTGOOD_CHANNEL_ID || "1"

  if (sid && visitorId) {
    return authHeaders(sid, channelId, visitorId)
  }

  // No env vars: fetch homepage to obtain cookies.
  try {
    const res = await fetch(HOMEPAGE, {
      headers: { "User-Agent": UA, Accept: "text/html,application/xhtml+xml" },
      redirect: "follow",
      signal: requestSignal(),
    })
    const setCookie = res.headers.get("set-cookie") || ""
    const sidFromCookie = (setCookie.match(/sid=([^;]+)/) || [])[1]
    const visitorFromCookie = (setCookie.match(/visitor_id=([^;]+)/) || [])[1]
    if (sidFromCookie && visitorFromCookie) {
      return authHeaders(sidFromCookie, channelId, visitorFromCookie)
    }
  } catch {
    // fall through to error below
  }
  throw new Error(
    "could not obtain CTgoodjobs session headers. Set CTGOOD_SID and " +
      "CTGOOD_VISITOR_ID (from a real browser session), or ensure network " +
      "access to www.ctgoodjobs.hk to bootstrap cookies.",
  )
}

function authHeaders(sid: string, channelId: string, visitorId: string): Record<string, string> {
  return {
    "User-Agent": UA,
    Accept: "application/json",
    "Content-Type": "application/json",
    sid,
    "channel-id": channelId,
    "visitor-id": visitorId,
  }
}

export interface SearchResponse {
  statusCode: number
  data: {
    meta: { jobsTotal?: number; title?: string; desc?: string }
    total: number
    jobs: JobRaw[]
  }
}

export interface JobRaw {
  jobId: string
  jobTitle: string
  url: string
  companyId?: string | null
  companyName?: string | null
  publishTime?: { display?: string; date?: string; timestamp?: string } | null
  validThrough?: { display?: string; date?: string } | null
  salary?: {
    case?: number
    salaryValue?: string | null
    salaryFrom?: number | null
    salaryTo?: number | null
    salaryMonthHour?: string | null
    isNegotiable?: boolean
  } | null
  locations?: string[] | null
  jobareas?: string[] | null
  benefits?: string[] | null
  empTypes?: { id?: string; name?: string }[] | null
  careerLevels?: { id?: string; name?: string }[] | null
  highlights?: string | null
}

export interface JobResult {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
  teaser: string | null
  salary: string | null
  areas: string[]
  employmentTypes: string[]
  careerLevels: string[]
}

function salaryText(j: JobRaw): string | null {
  const s = j.salary
  if (!s) return null
  if (s.salaryValue && s.salaryValue.trim() && s.salaryValue.trim() !== "N/A") {
    return s.salaryValue.trim()
  }
  if (s.salaryFrom != null && s.salaryTo != null) {
    const unit = s.salaryMonthHour === "HR" ? "/hour" : "/month"
    return `${s.salaryFrom}-${s.salaryTo} ${unit}`
  }
  return null
}

/** Reshape a raw CTgoodjobs job into the portal-skill contract result shape. */
export function toResult(j: JobRaw): JobResult {
  const location = j.locations && j.locations.length ? j.locations[0] : null
  const date = j.publishTime?.timestamp ?? j.publishTime?.date ?? null
  return {
    id: j.jobId,
    title: stripHtml(j.jobTitle) || "(untitled)",
    company: j.companyName || null,
    location,
    date,
    // Canonical openable URL: /job/<id>/  (API often returns /job/<id>-/slug which 404s in browser)
    url: `${JOB_URL_PREFIX}${j.jobId}/`,
    teaser: j.highlights ? stripHtml(j.highlights) : null,
    salary: salaryText(j),
    areas: j.jobareas ?? [],
    employmentTypes: (j.empTypes ?? []).map((e) => e.name || "").filter(Boolean),
    careerLevels: (j.careerLevels ?? []).map((e) => e.name || "").filter(Boolean),
  }
}

/** Strip the <strong>…</strong> highlighting CTgoodjobs wraps around matches. */
export function stripHtml(s: unknown): string {
  if (typeof s !== "string") return ""
  return s.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim()
}

/**
 * POST the CTgoodjobs search API. Retries with backoff on 429/5xx. `extra` is
 * merged into the JSON body (used by detail to pass `jobIds`).
 */
export async function searchPost(
  headers: Record<string, string>,
  body: Record<string, unknown>,
): Promise<SearchResponse> {
  const maxRetries = 6
  let delay = 500
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    let response: Response
    try {
      response = await fetch(SEARCH_BASE, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        redirect: "follow",
        signal: requestSignal(),
      })
    } catch (e) {
      throw new Error(
        `could not reach CTgoodjobs search API (${e instanceof Error ? e.message : String(e)})`,
      )
    }
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`CTgoodjobs request failed: ${response.status} ${response.statusText}`)
      }
      await sleep(retryDelayMs(response, delay + Math.floor(Math.random() * 500)))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 400) {
      const txt = await response.text()
      throw new Error(`CTgoodjobs rejected the request (400): ${txt.slice(0, 200)}`)
    }
    if (!response.ok) {
      throw new Error(`CTgoodjobs request failed: ${response.status} ${response.statusText}`)
    }
    return (await response.json()) as SearchResponse
  }
  throw new Error("CTgoodjobs request failed after retries")
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

/** Extract a numeric job id from an id or a /job/<id> URL. */
export function normalizeId(input: string): string | null {
  const trimmed = input.trim()
  if (/^\d+$/.test(trimmed)) return trimmed
  const m = trimmed.match(/\/job\/(\d+)/)
  if (m) return m[1]
  return null
}
