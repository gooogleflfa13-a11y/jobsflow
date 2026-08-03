# /scan - 扫描新职位 + 两段评分

扫描招聘门户的新职位，去重后做两段评分（初评 -> 门槛 3.3 -> 深 JD -> 深评）。

## 用法

```
/scan              # 临时模式：只扫上次刷新之后的新岗（系统自动记忆时间）
/scan temp         # 同上
/scan daily        # 扫最近 24 小时
/scan 3            # 扫最近 3 小时
/scan 6            # 扫最近 6 小时
```

## 执行步骤

1. 运行扫描 + 两段评分：

```bash
./tools/fresh_24h/temp_two_pass.sh temp    # 或 daily，或传 --hours N
```

2. 读取生成的 `_twopass_scored.csv` 和 `_run.json`

3. 向用户报告：
   - 扫到多少新职位，多少通过门槛 3.3
   - 多少拿到了 deep JD（LinkedIn 为主）
   - Top 5 按深评分数降序：编号 | 职位 | 公司 | 分数 | JD深度
   - 有无 portal 错误（CT cookie 过期等）

4. 如果深评生成了职位定性或语义简历匹配任务，读取并完成待处理任务：

```bash
python3 tools/fresh_24h/semantic_match_agent.py list
python3 tools/fresh_24h/semantic_match_agent.py show <key>
# position_profile 任务：
python3 tools/fresh_24h/semantic_match_agent.py complete <key> \
  --lane G --company-brief "公司主营跨境支付，为企业提供金融科技服务" \
  --note "公司业务性质与职位范围共同决定 lane"
# semantic_resume_match 任务：
python3 tools/fresh_24h/semantic_match_agent.py complete <key> \
  --score 4.0 --basis transferable --note "与事实基线相邻且可迁移"
```

完成后重新运行评分，才会把语义判断回填到 `resume` 维度。扫描预览可以保留
明确标记的关键词回退，但结果会显示 `语义匹配来源=pending_fallback`、待处理数，
且回退上限默认为 4.0。正式 `/push`（包括本地台账）在 pending 存在时会停止；
只有显式传入 `--allow-pending-semantic` 才能进行诊断性覆盖。

5. 问用户：「要推到 Google Sheets 吗？」（如果用户之前说「只看不进表」则跳过）

## 注意

- 临时模式自动记住本次刷新时间，下次 `/scan` 只扫这段时间内的新岗
- 深评先查 URL-keyed JD 缓存；命中不发网络请求。未命中时 LinkedIn 用 CLI，JobsDB 才用 Playwright，CTgoodjobs 不拉浏览器
- 扫描不会自动做材料，材料需要用户点名后用 `/materials`
