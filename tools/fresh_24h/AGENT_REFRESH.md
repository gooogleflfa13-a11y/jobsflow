# Agent contract: daily and temporary scans

Read `docs/system_rules.md` first. Search relevance, exclusions, A-F directions
and scoring evidence come from the user's private setup configuration:

```text
JobSearch_2026/00_Profile/queries.json
```

The tracked `queries.json` is an industry-neutral setup-required template.

## Modes

| User request | Mode | Window |
|--------------|------|--------|
| default, temp, 临时 | `--mode temp` | since the last successful refresh, with bounded padding |
| daily, 日更, 24 hours | `--mode daily` | about 24 hours |
| explicit N hours | `--mode temp --hours N` | N hours |

If no refresh state exists, temp establishes a 24-hour baseline. Failed portal
runs must not advance the cursor. Use `--no-record` for previews and debugging.

```bash
./tools/fresh_24h/fresh_24h_scan.sh --show-state
./tools/fresh_24h/temp_two_pass.sh temp
./tools/fresh_24h/temp_two_pass.sh daily
```

## Two-pass contract

1. Scan titles and teasers using configured queries.
2. Score pass 1 with the private scoring profile.
3. Only rows meeting the default 3.3 gate continue.
4. Check `02_Tracker/jds/cache/<sha256(url)[:16]>.json` first. A valid cache hit
   is the only JD input and makes zero network requests. If absent, retrieve
   structured detail; use Playwright only as a bounded fallback.
5. Score pass 2 and record the actual JD depth.
6. For deep rows, process pending `position_profile` and
   `semantic_resume_match` tasks with `semantic_match_agent.py`. The former
   returns lane + company brief; the latter labels each verdict as direct,
   transferable, upper_only or none. Both tasks consume the cached JD, and the
   profile calibration caps transferable/upper-only scores deterministically.
7. Rerun scoring after completion. Inspect `语义匹配来源` and
   `语义待处理数`; formal local/Google pushes stop when pending tasks remain.
8. Write local/Google tracker rows only when requested.
9. Never create application materials during scan.

Use a full JD for materials. If a portal remains shallow, mark `paste_needed` and
ask for pasted text instead of fabricating requirements.

## 首次使用：门户会话复用

JobsDB、CTgoodjobs 和 LinkedIn 详情页默认使用无头 Chrome，并会尝试读取：

```text
~/.config/jobsearch/storage_state_<portal>.json
```

如果首次抓取遇到人机验证，请在用户明确允许的情况下运行：

```bash
python3 tools/fresh_24h/portal_jd_browser.py \
  --url '<job-detail-url>' \
  --headed \
  --save-storage-state ~/.config/jobsearch/storage_state_jobsdb.json
```

在浏览器窗口中人工完成一次验证后关闭窗口；后续抓取会复用该会话。可用
`--storage-state` 或 `PORTAL_JD_STORAGE_STATE` 覆盖读取路径，`--channel` 或
`PORTAL_JD_CHANNEL` 覆盖浏览器通道。Cookie/session 文件属于敏感数据，必须放在
用户主目录下，禁止写入仓库、CSV、日志或报告。

详情页默认对 `waf`、`timeout`、`empty` 失败自动重试 2 次；可用
`--retry 0` 关闭，或用 `--retry-delay` 调整间隔。成功抓取会自动写入
`02_Tracker/jds/cache/<sha256(url)[:16]>.json`，`--out` 仍可同时生成 Markdown。

## Batch and identifiers

`JobSearch_2026/02_Tracker/fresh_refresh_state.json` stores the last successful
refresh and recent history. New rows use `本轮新增=是`, a batch ID and timestamp;
older rows are demoted and lose new-batch styling.

IDs use `{A-F direction}{0-3 tier}-{sequence}` (an optional G capability lane is
allowed when private setup defines it). A-F meanings come from private setup,
never from a built-in profession. Continue the maximum existing prefix;
do not invent placeholder ranges.

## Required agent behavior

- Respect preview/no-record and never push implicitly.
- Follow the run JSON `model_contract` for counters, failures and next actions.
- Do not reinterpret an unconfigured template as search intent.
- Do not spend unbounded time on WAF, CAPTCHA or browser recovery.
- A single-job “deep analysis” request uses `deep_analyze_job.py`, not a teaser.
- A pending semantic task may remain visible in a scan preview, but it must be
  labeled `pending_fallback` and capped conservatively. Never present it as a
  completed semantic score; formal push requires completion unless the user
  explicitly authorizes the diagnostic override.
- Keep search, tracking, materials and submission as separate user-authorized
  stages.
