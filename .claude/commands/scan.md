# /scan - 扫描新职位 + 两段评分

扫描招聘门户的新职位，去重后做两段评分（内部初评调度/不确定性救援 -> 用户选择的扫描深度 -> 完整 JD 深评 -> 用户选择的保留偏好）。

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

   每个被评分的岗位还会在私有工作区生成一份版本化评估记录：
   `JobSearch_2026/02_Tracker/job_assessments/<hash>.json`。其中保存初评/深评/最终分数、
   结构化优势与待核对缺口，以及 JD/评分配置哈希；JD 或意向变更后会重新生成，不能沿用旧判断。
   `/materials` 会读取同一记录来排序 CV 证据、约束 Cover Letter/邮件的共同证据；
   `/interview` 用 `python3 -m tools.job_materials assessment show --job-id <JOB-ID>`
   读取同一记录准备缺口问题，不会各自重新猜一个匹配结论。

3. 向用户报告：
   - 扫到多少新职位，多少直接通过初评、多少因缓存/摘要不足/灰区被救援、多少初评过滤
   - 多少命中 JD 缓存、多少发起网络深取、多少拿到了 deep JD
   - 当前扫描深度、网络深取预算、最终保留偏好，以及 `待审-JD不足` 数量
   - 初评分布和完整 JD 深评分布：<3.0、3.0–3.3、3.3–3.5、3.5+
   - Top 5 按最终深评分数降序：编号 | 职位 | 公司 | 分数 | JD深度；待审项另列，不混入最终排名
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
- 初评 3.3 是内部直接调度线而非用户最终取舍线；摘要缺失/过短、缓存命中和灰区岗位会被救援
- 扫描深度控制 cache-miss 网络深取：节能约 10、平衡约 20、广覆盖约 40；缓存命中不占预算
- 最终保留偏好独立选择宽松 3.0、标准 3.3、精选 3.5；改变它只重筛保存的深评分数
- 未命中时 LinkedIn 用 CLI，JobsDB 才用 Playwright，CTgoodjobs 不拉浏览器
- 未能取得完整 JD 的岗位保留为 `待审-JD不足`，不能把其标题/teaser 分数当作最终分数
- 扫描不会自动做材料，材料需要用户点名后用 `/materials`
