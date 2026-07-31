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

4. 问用户：「要推到 Google Sheets 吗？」（如果用户之前说「只看不进表」则跳过）

## 注意

- 临时模式自动记住本次刷新时间，下次 `/scan` 只扫这段时间内的新岗
- CTgoodjobs 的 JD 通常是 teaser（不拉浏览器）；LinkedIn 能拿到全文；JobsDB 用 Playwright
- 扫描不会自动做材料，材料需要用户点名后用 `/materials`
