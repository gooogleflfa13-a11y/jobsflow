# /rank — 兼容入口

旧版 `/rank` 依赖已经移除的 `/scrape` 和 `job_search_tracker.csv`，不再执行
批量评分。当前产品的唯一检索/评分主线是：

```text
/scan → two-pass gate 3.3 → /push 或 /push --local-only
```

用户需要为单个岗位做深度分析时，请使用 `/materials <岗位编号>`；材料流程会
读取本地 tracker 行、完整 JD、公司研究和事实核验过的 A–F 基础版。

如果旧 agent 请求 `/rank`，明确说明它已被替换，并给出上面的 `/scan` 命令，
不要创建或修改 `job_search_tracker.csv`、`job_scraper/seen_jobs.json` 或任何
旧版 tracker。
