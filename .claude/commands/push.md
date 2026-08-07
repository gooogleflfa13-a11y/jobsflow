# /push - 推送到 Google Sheets

把评分结果推送到 Google Sheets 的 fresh_24h tab。

## 用法

```
/push                        # 使用已确认的扫描深度和保留偏好
/push --retention selective  # 临时使用精选 3.5
/push --min-score 3.5        # 兼容的数值化最终保留线覆盖
/push --scan-depth economy   # 临时使用节能网络预算
/push --mode daily           # 日更模式
/push --local-only           # 不使用 Google Sheets，更新本地主 CSV
```

深评若有未完成的语义任务，`/push` 和 `--local-only` 默认会停止，并列出任务键。
先执行 `semantic_match_agent.py list/show/complete`，再重跑评分；只有明确的诊断场景
才使用 `--allow-pending-semantic` 覆盖闸门。

## 执行步骤

1. 推送：

```bash
python3 tools/fresh_24h/push_to_gsheet.py --also-local --mode temp
```

如果 setup 选择了本地 CSV 或暂时没有 Google 凭据：

```bash
python3 tools/fresh_24h/push_to_gsheet.py --local-only --mode temp
```

`--local-only` 会把完整 JD 深评达到最终门槛的岗位，以及明确标记为
`待审-JD不足` 的 provisional 岗位合并进
`JobSearch_2026/02_Tracker/hk_apply_list_YYYY-MM-DD.csv`，保留批次标记和状态，
不会尝试连接 Google Sheets。待审项不属于最终排名，需用户先看岗位或补充 JD；
初评标题分数不会冒充最终判断。

2. 向用户报告：
   - 写入了哪个 tab
   - 总行数、本轮新增数、较早入表数
   - 批次号和入表时间
   - Google Sheet 链接

## 合并规则

- 如果 tab 已存在：旧批「本轮新增」从「是」改为「否」，去掉米色底；新行标「是」+ 米色底
- 如果 tab 不存在：新建 tab
- 排序：本轮新增=是 置顶，然后按分数降序
