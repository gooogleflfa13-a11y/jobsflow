# /setup - 首次安装与个性化配置

为新用户建立一条私有、跨行业、可直接扫描的求职工作流。

## 用法

```text
/setup ~/Documents/my-cv
/setup
```

## 执行步骤

### 1. 运行确定性向导

```bash
python3 setup.py --doctor
python3 setup.py --resume-folder <用户给的路径>
```

向导会：

- 检查 Python、Bun、LibreOffice、Playwright 与门户 lockfile；
- 创建被 Git 忽略的 `JobSearch_2026/` 私有工作区；
- 读取简历并询问目标岗位、地点、薪资、工作时间等限制；
- 询问简历匹配画像上沿幅度：低（保守）、中（平衡）或高（扩展）；
- 生成私有 `config.personal.json`、`queries.json`、基础
  `tracker_schema.json` 与空 tracker；方向默认为 A-F，模型可在有依据时提出可选 G 能力线；
- 生成 `00_Profile/setup_design_request.json`。该文件只包含配置所需的
  意向与简历证据关键词，不把完整简历写回产品配置。

### 2. 用当前大模型提出受控个性化设计

读取 `JobSearch_2026/00_Profile/setup_design_request.json`，对目标行业
做简短、可核验的调研并记录至少一个当前来源 URL。只按文件中的
`required_output`、`limits` 和
`model_contract` 返回 JSON，重点综合：

- 用户明确的求职方向、地点、工作时间、薪资和资格限制；
- 简历中真实存在的技能、行业和经历证据；
- 目标行业常见但值得逐岗检查的要求。

简历匹配的“上沿幅度”只控制语义匹配允许的能力迁移范围，不会把潜力改写成
已做过的经历。低/中/高分别对应保守、平衡、扩展；任何档位都禁止编造雇主、职责、
工具、证书、指标或结果。用户没有明确选择时使用中（平衡），并记录在私有评分配置中。

可新增最多 8 个真正有筛选价值的表头，例如技术岗位的“技术栈/值班要求”、
医药岗位的“治疗领域/注册要求”。不要把行业常识写成候选人事实，不要复制
基础列，不要添加仅适用于法律/合规的默认字段。

将纯 JSON 提议写到私有路径：

```text
JobSearch_2026/00_Profile/setup_schema_proposal.json
```

然后必须调用验证器：

```bash
python3 setup.py \
  --schema-proposal JobSearch_2026/00_Profile/setup_schema_proposal.json
```

只有验证通过的提议才能更新私有搜索关键词、A-F 方向、评分权重和 tracker
表头。若模型遗漏字段、输出非法类型或权重错误，系统保留确定性 fallback；
不得手工绕过验证。已有数据行的 tracker 不会被隐式改表。

### 3. 询问下一步

问用户：

> 先做基础版简历（按个性化 A-F 方向），还是先检索新职位？

基础版：

```bash
python3 -m tools.job_materials base sync --lane <字母>
python3 -m tools.job_materials base factcheck --lane <字母>
```

检索：执行 `/scan`。

### 4. 可选安装门户

用户同意后：

```bash
python3 setup.py --install-portals
```

### 5. 报告

报告环境检查、提议是否通过验证、最终 A-F 映射、个性化表头及下一步。
不得回显完整简历、联系方式或私有配置内容。
