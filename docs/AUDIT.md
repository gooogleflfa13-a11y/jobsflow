# JobsFlow 外部审计手册 v2.0

> 将此文档作为 prompt 交给任意 AI agent（Claude Code、Cursor、Codex 等），对
> jobsflow 仓库执行全维度独立审计。每节末尾列出必须回答（pass/fail/risk）的
> 问题，审计 agent 应逐条回答并提供证据（文件路径 + 行号）。

> **2026-07-31 更新说明：** 本手册已按跨行业产品和当前源码刷新。旧的法律/合规、
> LaTeX、`/scrape` 和 `job-scraper` 假设不再适用；审计时以当前文件系统、
> `AGENTS.md`、`docs/system_rules.md` 和 `README.md` 为准。目录树中不存在的路径
> 应记录为文档漂移，而不是假设它仍然是运行时入口。

## 0. 仓库上下文

- **用途**: 面向各行业的本地优先 AI 求职执行系统
- **核心管线**: `/setup`（简历→私有配置）→ `/scan`（多门户搜索→两段评分）→ `/push`（Google Sheets 或本地 CSV）→ `/materials`（JD/公司研究定制 CV/CL）→ `/apply`（LibreOffice headless PDF + 人工确认）
- **门户**: LinkedIn、JobsDB、CTgoodjobs、FreeHire
- **语言**: Python (工具管线) + TypeScript/Bun (门户 CLI) + Shell (胶水脚本) + Markdown (agent 规则)
- **个人数据存储**: 仅本地 `JobSearch_2026/`（gitignored），仓库不含真实 PII

### 0.1 完整目录树与审计对象

> 审计 agent 应**逐目录遍历**，对照下表理解每个文件/目录的职责，避免遗漏审计面。

```
ai-job-search/
├── CLAUDE.md                    ← 主导：agent 行为规则、候选人 profile、两段评分强制执行
├── AGENTS.md                    ← 导2：平台无关的斜杠命令参考 + 系统规则引用
├── README.md / README_EN.md     ← 审：公开文档、上手引导
├── SETUP.md                     ← 审：fork 更新手册
├── CONTRIBUTING.md              ← 审：贡献指南
├── LICENSE                      ← 审：MIT
├── .gitignore                   ← 审（P0）：隐私保护规则、ALLOWED_IGNORE_NEGATIONS
├── .mcp.json                    ← 安全：MCP 服务器配置（gitignored）
├── setup.py                     ← 审：/setup 向导（环境检查、简历解析、配置生成）
│
├── tools/                       ← 核心管线——所有 Python/Shell 工具
│   ├── security_guards.py       ← 审（P0）：权限白名单 + gitignore + 生命周期脚本 三方检查
│   ├── lint_skills.py           ← 审：技能文件规范检查
│   ├── salary_lookup.py         ← 审：薪金查询（可选）
│   ├── convert_salary_excel.py  ← 审：薪金 Excel 转 JSON
│   ├── check_placeholders.py    ← 审：占位符扫描（gitignored）
│   │
│   ├── fresh_24h/               ← /scan + /push 管线
│   │   ├── temp_two_pass.sh     ← 入口：/scan 胶水脚本（temp/daily/N-hours）
│   │   ├── fresh_24h_scan.py    ← 审：多门户搜索编排（972行）、去重、过滤
│   │   ├── two_pass_score.py    ← 审：两段评分、扫描深度、保留偏好、deep JD fetch
│   │   ├── push_to_gsheet.py    ← 审：Google Sheets/本地 CSV 推送（901行）、合并/格式
│   │   ├── queries.json         ← 审：行业中立、setup-required 的空模板
│   │   ├── refresh_state.py     ← 审：刷新时间状态（原子写入、备份恢复）
│   │   ├── jd_cache.py          ← 审：URL-Keyed JD 缓存（SHA-256、TTL 60天）
│   │   ├── job_id.py            ← 审：Job-ID 格式定义 {A-F}{0-3}-{序列}
│   │   ├── batch_mark.py        ← 审：批次标记工具（新旧行管理）
│   │   ├── deep_analyze_job.py  ← 审：单职位深度分析（仅 LinkedIn）
│   │   ├── linkedin_enrich.py   ← 审：LinkedIn JD 深度获取
│   │   ├── portal_jd_browser.py ← 审：Playwright 浏览器 JD 抓取（JobsDB）
│   │   ├── careerops_quickscore.py ← 审：CareerOps 快速评分引擎
│   │   ├── local_tracker.py      ← 审：本地 CSV 主台账合并
│   │   ├── tracker_schema.py     ← 审：setup 个性化表头消费
│   │   ├── promote_fresh_to_main.py ← 审：scan 结果提升至主 tracker
│   │   ├── validate_queries.py  ← 审：查询配置验证
│   │   ├── docx_to_pdf.py       ← 审：LibreOffice 无头 PDF 转换
│   │   └── queries_local_firms_preview.json ← 预览模式查询（gitignored）
│   │
│   ├── job_materials/           ← /materials 管线
│   │   ├── __main__.py          ← 入口：argparse 子命令（base/url/jd/enrich/tailor/pipeline/resume/company/preflight）
│   │   ├── __init__.py          ← 包声明
│   │   ├── bases.py             ← 审：A-F 简历基线的同步与事实检查
│   │   ├── enrich.py            ← 审：JD 深度内容丰富（缓存→CLI→浏览器 三级fallback）
│   │   ├── tailor.py            ← 审：面向 JD 的 bullet 重排序
│   │   ├── evidence.py          ← 审：事实检查证据记录
│   │   ├── jd_store.py          ← 审：JD 存储与检索
│   │   ├── packages.py          ← 审：从本地 tracker 按 job ID 创建/解析材料包
│   │   ├── company_research.py  ← 审：公司快查、来源与缓存
│   │   ├── requirements_engine.py ← 审：确定性申请前置问题
│   │   ├── paths.py             ← 审：路径解析（package 目录、job ID 查找）
│   │   ├── resume_parse.py      ← 审：PDF 简历解析
│   │   └── url_normalize.py     ← 审：URL 标准化
│   │
│   ├── core_applications/       ← 核心投递包管理（兼容旧投递包）
│   │   ├── validate_package.py  ← 审：DOCX/PDF 投递包校验（LaTeX 源可选）
│   │   ├── sync_tracker_status.py ← 审：同步 tracker 状态
│   │   └── validate_package.py  ← 审：投递包校验
│   │
│   ├── obscura/                 ← 审：无头浏览器抓取工具（gitignored）
│   └── (no WPS runtime; LibreOffice is the documented PDF engine)
│
├── tests/                       ← 测试套件
│   ├── test_security_guards.py  ← 审（P0）：242行，安全三方测试
│   ├── test_fresh_scan_helpers.py ← 审：scan helpers 测试
│   ├── test_core_application_validator.py ← 审：package 校验测试
│   ├── test_materials_workflow_contract.py ← 审：JD/包创建/setup→pipeline 合成契约
│   ├── test_salary_lookup.py    ← 审：薪金查询测试
│   ├── test_convert_salary_excel.py ← 审：薪金转换测试
│   └── conftest.py / pytest.ini ← 缺失（需审计）
│
├── .agents/skills/              ← 门户 CLI + 技能定义（Bun/TypeScript）
│   ├── linkedin-search/         ← 审：LinkedIn public jobs-guest API
│   │   ├── SKILL.md             ← 审：技能定义
│   │   ├── url-reference.md     ← 审：API schema 参考
│   │   └── cli/                 ← 审：CLI 源码 + 测试
│   │       ├── src/helpers.ts   ← 审（P0）：htmlFetch（DoH+retry）、parseJobCards、parseJobDetail
│   │       ├── src/cli.ts       ← 审：CLI 入口
│   │       ├── src/commands/    ← 审：search/detail 命令
│   │       ├── package.json     ← 审（P0）：无 lifecycle 脚本、无 trustedDeps
│   │       ├── tsconfig.json    ← 审：TS 配置
│   │       └── tests/           ← 审：parsing、retry-backoff、CLI flags、search
│   │
│   ├── jobsdb-search/           ← 审：JobsDB HK REST API（Seek group）
│   │   ├── SKILL.md             ← 审：技能定义
│   │   ├── url-reference.md     ← 审：API schema
│   │   └── cli/                 ← 同上结构
│   │       ├── src/helpers.ts   ← 审（P0）：searchGet（fetch+retry）、toResult、jobageToDateRange
│   │       └── tests/           ← 审：smoke、retry-backoff
│   │
│   ├── ctgoodjobs-search/       ← 审：CTgoodjobs HK API（cookie 认证）
│   │   ├── SKILL.md             ← 审：技能定义（含 cookie 获取说明）
│   │   ├── url-reference.md     ← 审：API schema + cookie 机制
│   │   └── cli/                 ← 同上结构
│   │       ├── src/helpers.ts   ← 审（P0）：resolveHeaders（env→cookie 三级fallback）、searchPost（fetch+retry）
│   │       └── tests/           ← 审：smoke、retry-backoff
│   │
│   └── freehire-search/         ← 审：freehire.dev public JSON API
│       ├── SKILL.md             ← 审：技能定义
│       ├── url-reference.md     ← 审：API schema
│       └── cli/                 ← 同上结构
│           ├── src/helpers.ts   ← 审（P0）：apiGet（fetch+retry）、toResult、toDetail、cleanHtml
│           └── tests/           ← 审：parsing、CLI flags、retry-backoff、commands
│
├── .claude/                     ← Agent 规则与技能
│   ├── commands/                ← 审：斜杠命令定义
│   │   ├── setup.md             ← 审：/setup 命令
│   │   ├── scan.md              ← 审：/scan 命令（含模式说明）
│   │   ├── push.md              ← 审：/push 命令
│   │   ├── materials.md         ← 审：/materials 命令（含 STAR 重写指令）
│   │   ├── apply.md             ← 审（P0）：/apply 命令（drafter-reviewer 双 agent）
│   │   ├── interview.md         ← 审（P0）：/interview 命令
│   │   ├── rank.md              ← 审：/rank 命令
│   │   ├── outcome.md           ← 审：/outcome 命令
│   │   ├── reset.md             ← 审：/reset 命令
│   │   ├── expand.md            ← 审：/expand 命令
│   │   ├── add-portal.md        ← 审：/add-portal 命令
│   │   └── add-template.md      ← 审：/add-template 命令
│   │
│   ├── skills/                  ← 审：AI 技能定义
│   │   ├── job-application-assistant/
│   │   │   ├── SKILL.md         ← 审：技能入口
│   │   │   ├── 01-candidate-profile.md      ← 审（P0）：候选人资料
│   │   │   ├── 02-behavioral-profile.md     ← 审（P0）：行为特征
│   │   │   ├── 03-writing-style.md          ← 审：写作风格指南
│   │   │   ├── 04-job-evaluation.md         ← 审：职位评估框架
│   │   │   ├── 05-cv-templates.md           ← 审：CV 模板规范
│   │   │   ├── 06-cover-letter-templates.md ← 审：CL 模板规范
│   │   │   └── 07-interview-prep.md         ← 审：面试准备框架
│   │   │
│   │   └── upskill/             ← 审：技能提升助手
│   │
│   ├── agents/                  ← 审：agent 定义
│   │   └── gemini-research-expert.md ← 审：研究专家 agent
│   │
│   ├── settings.json            ← 审（P0）：权限白名单
│   └── settings.local.json      ← 审：本地覆盖（gitignored）
│
├── docs/                        ← 审：项目文档
│   ├── AUDIT.md                 ← 本手册
│   ├── system_rules.md          ← 审：系统规则
│   ├── tracker_defaults.md      ← 审：tracker 默认值
│   └── superpowers/             ← SDD 计划与 specs
│
├── documents/                   ← 审：文档目录（个人内容 gitignored）
├── upskill/                     ← 审：技能提升报告（个人输出 gitignored）
│
├── .github/                     ← 审：CI/CD
│   └── workflows/               ← 审：CI 流水线、dependency-review
│
└── .superpowers/                ← SDD 任务记录（gitignored）
```

### 0.2 系统架构概述

```
                          ┌──────────────────────────────────────────┐
                          │              用户交互层                   │
                          │  /setup  /scan  /push  /materials  /apply│
                          └──────┬──────┬──────┬──────┬──────┬───────┘
                                 │      │      │      │      │
              ┌──────────────────┼──────┼──────┼──────┼──────┼──────────────┐
              │                  ▼      ▼      ▼      ▼      ▼              │
              │   ┌──────────────────────────────────────────────────┐      │
              │   │              Claude Code Agent 层                 │      │
              │   │  CLAUDE.md  AGENTS.md  .claude/commands/*.md     │      │
              │   │  .claude/skills/  .claude/agents/                │      │
              │   └──────────────────────┬───────────────────────────┘      │
              │                          │                                  │
              │     ┌────────────────────┼────────────────────┐             │
              │     ▼                    ▼                    ▼             │
              │ ┌──────────┐   ┌──────────────┐   ┌──────────────────┐     │
              │ │ setup.py │   │ 扫描 + 评分   │   │ job_materials/    │     │
              │ │ 环境检查  │   │ fresh_24h/    │   │ enrich/tailor/    │     │
              │ │ 简历解析  │   │ temp_two_pass │   │ bases.py          │     │
              │ │ 配置生成  │   │ push_to_gsheet│   │ __main__.py       │     │
              │ └──────────┘   └──────┬───────┘   └──────────────────┘     │
              │                      │                                      │
              │           ┌──────────┼──────────┐                           │
              │           ▼          ▼          ▼                           │
              │   ┌──────────┐ ┌──────────┐ ┌────────────┐                  │
              │   │LinkedIn  │ │ JobsDB   │ │ CTgoodjobs │ FreeHire        │
              │   │ htmlFetch│ │searchGet │ │searchPost  │ apiGet          │
              │   │ (DoH+retry)│(retry)  │ │ (cookie+retry)│(retry)       │
              │   └──────────┘ └──────────┘ └────────────┘                  │
              │                                                            │
              │   ┌──────────────────────────────────────────┐            │
              │   │        基础设施层                        │            │
              │   │  refresh_state.py (原子时间状态)          │            │
              │   │  jd_cache.py (URL-Keyed JD 缓存)          │            │
              │   │  batch_mark.py (批次标记)                 │            │
              │   │  security_guards.py (安全三方检查)        │            │
              │   └──────────────────────────────────────────┘            │
              │                                                            │
              │   ┌──────────────────────────────────────────┐            │
              │   │        数据层                            │            │
              │   │  Google Sheets (评分 + tracker)           │            │
              │   │  本地 CSV/JSON (queries.json, 状态文件)   │            │
              │   │  本地 DOCX → LibreOffice PDF (CV/CL)    │            │
              │   │  本地 JD 缓存 (jds/*.md)                  │            │
              │   └──────────────────────────────────────────┘            │
              └──────────────────────────────────────────────────────────┘
```

### 0.3 数据流：一次完整 /scan 的数据旅程

```
1. 用户触发 /scan
2. AGENTS.md 路由到 .claude/commands/scan.md
3. scan.md 调用 tools/fresh_24h/temp_two_pass.sh <mode>
4. temp_two_pass.sh →
   a. python3 fresh_24h_scan.py --mode <mode>        # 4 门户并行搜索
      ├── 读取 refresh_state.py → 计算时间窗口
      ├── 读取 queries.json → 构造搜索参数
      ├── 调用 4 个门户 CLI (bun run ... src/cli.ts search ...)
      │   ├── linkedin-search → DoH DNS → htmlFetch → parseJobCards
      │   ├── jobsdb-search → searchGet → toResult
      │   ├── ctgoodjobs-search → resolveHeaders → searchPost
      │   └── freehire-search → apiGet → toResult
      ├── apply_rules() → 按私有 setup 的行业相关性规则过滤 + 噪声排除
      ├── load_tracker_keys() → 去重（vs 已有 tracker CSV）
      └── 写入 <timestamp>_fresh.csv + <timestamp>_run.json
   b. python3 two_pass_score.py ...                   # 两段评分
      ├── Pass 1: 对 teaser 做调度评分；3.3 直接通过，缓存/薄摘要/灰区救援
      ├── deep_enrich_hit() → 缓存不限额、网络限额的三级 fallback:
      │   ├── jd_cache.py (URL-keyed, TTL 60天)
      │   ├── LinkedIn CLI detail / JobsDB Playwright
      │   └── teaser fallback
      ├── Pass 2: 对完整 JD 重新评分并持久化 → 用户选择 3.0/3.3/3.5 保留线；未深取项明确待审
      └── 写入 <timestamp>_twopass_scored.csv
5. Agent 读取 CSV, 向用户报告 top 5, 询问是否 push
6. 用户确认 → .claude/commands/push.md →
   push_to_gsheet.py →
   ├── read_existing_rows() → 合并旧批次
   ├── batch_mark.py: demote_previous_batch + mark_new_rows
   ├── setup_status_formats() → 下拉菜单 + 条件格式
   └── 写入 Google Sheets
```

### 0.4 关键入口点索引

| 你想审计... | 从这个文件开始 |
|------------|--------------|
| 搜索机制 | `tools/fresh_24h/fresh_24h_scan.py` |
| 评分逻辑 | `tools/fresh_24h/two_pass_score.py` |
| Google Sheets 推送 | `tools/fresh_24h/push_to_gsheet.py` |
| 时间状态管理 | `tools/fresh_24h/refresh_state.py` |
| JD 缓存 | `tools/fresh_24h/jd_cache.py` |
| 材料管线 | `tools/job_materials/__main__.py` |
| 简历解析 + 配置生成 | `setup.py` |
| LinkedIn CLI | `.agents/skills/linkedin-search/cli/src/helpers.ts` |
| JobsDB CLI | `.agents/skills/jobsdb-search/cli/src/helpers.ts` |
| CTgoodjobs CLI | `.agents/skills/ctgoodjobs-search/cli/src/helpers.ts` |
| FreeHire CLI | `.agents/skills/freehire-search/cli/src/helpers.ts` |
| 安全三方检查 | `tools/security_guards.py` |
| Agent 行为规则 | `CLAUDE.md`, `AGENTS.md` |
| 隐私 gitignore 规则 | `.gitignore` |
| 技能入口 | `.claude/skills/job-application-assistant/SKILL.md` |
| 测试套件 | `tests/` |

### 0.5 文件规模速查

| 文件 | 行数 | 类型 | 关键风险面 |
|------|------|------|-----------|
| `fresh_24h_scan.py` | 972 | Python | 正则过滤、子进程调用、去重逻辑 |
| `push_to_gsheet.py` | 901 | Python | GCP 密钥、Sheet 合并、格式注入 |
| `two_pass_score.py` | 544 | Python | deep JD 策略、评分编排 |
| `setup.py` | 1150 | Python | 简历 PII 提取、配置模板注入 |
| `job_materials/__main__.py` | 667 | Python | arg 注入、路径遍历 |
| `linkedin-search/helpers.ts` | 344 | TS | DoH 依赖、429 retry、regex 解析 |
| `refresh_state.py` | 285 | Python | 状态损坏恢复 |
| `ctgoodjobs-search/helpers.ts` | 211 | TS | cookie 管理、400 错误体 |
| `freehire-search/helpers.ts` | 223 | TS | JSON 解析、base URL 注入 |
| `jobsdb-search/helpers.ts` | 163 | TS | 429 retry、API 版本 |
| `security_guards.py` | 297 | Python | 白名单完整性、PII 模式 |
| `test_security_guards.py` | 242 | Python | P0 测试覆盖 |

---

## 1. 安全与供应链审计 (Security & Supply Chain)

**审计目标**: 确保依赖项、权限模型、密钥管理无风险漏洞。

### 1.1 依赖项漏洞
- [ ] 检查 `package.json`（所有门户 CLI）是否有已知 CVE
- [ ] 检查 `pip` 依赖（如有 `requirements.txt`/`pyproject.toml`）是否有已知 CVE
- [ ] 是否存在已废弃/不再维护的依赖包
- [ ] 所有依赖是否锁定具体版本（或范围上限）

### 1.2 注入风险
- [ ] 是否有 `postinstall`/`preinstall`/`install`/`prepare`/`prepack` 生命周期脚本？（`security_guards.py:FORBIDDEN_SCRIPTS` 应拦截）
- [ ] 是否有 `trustedDependencies`？（绕过 bun 的安全默认）
- [ ] 门户 CLI 是否将用户输入拼接到 shell 命令中（命令注入）
- [ ] `temp_two_pass.sh` 及其他 shell 脚本是否存在未引用的变量展开

### 1.3 权限模型
- [ ] `.claude/settings.json` 中 `permissions.allow` 是否全在 `ALLOWED_PERMISSIONS` 白名单
- [ ] 是否存在通配符权限（`Bash(*)`、`Bash(curl:*)`）会被 fork 者继承
- [ ] `security_guards.py` 是否被 CI 调用

### 1.4 密钥与密钥管理
- [ ] `.env` 是否在 `.gitignore` 中（需验证所有后缀变体：`.env.local`、`.env.production`）
- [ ] `config.personal.json` 是否在 `.gitignore` 中
- [ ] 源代码中是否有硬编码密钥（search: `api_key`/`secret`/`token`/`password`/`Bearer`）
- [ ] `.mcp.json`（MCP 配置）是否在 `.gitignore` 中

### 必须回答问题
1. 是否存在已知 CVE 的高危依赖？（pass/fail/risk）
2. `bun install` 时是否有任意代码执行风险？（pass/fail）
3. 权限白名单是否有未审查的条目？（pass/fail）
4. 是否有硬编码密钥？（pass/fail，如有列出文件+行号）

---

## 2. 隐私与数据保护审计 (Privacy & Data Protection)

**审计目标**: 确保个人数据不会意外泄露至代码仓库。

### 2.1 .gitignore 覆盖范围
- [ ] 个人 CV/CL 通配符是否覆盖所有模板引擎：`cv/main_*.*`、`cover_letters/cover_*.*`（不是仅 `.tex`）
- [ ] 个人工作区 `JobSearch_2026/` 是否完整 gitignored
- [ ] 主 tracker（`JobSearch_2026/02_Tracker/hk_apply_list_*.csv`）是否 gitignored
- [ ] 薪金数据文件（`salary_data.json`、`job_scraper/seen_jobs.json`）是否 gitignored
- [ ] 否定规则（`!...`）是否全部在 `ALLOWED_IGNORE_NEGATIONS` 白名单中

### 2.2 数据流映射
- [ ] 追踪一条简历数据的完整流程：PDF 解析 → 文本提取 → 配置文件 → 查询模板 → JD 评分 → CV 生成 → 投递
- [ ] 识别每个步骤中个人信息的存在位置（姓名、电话、邮箱、地址、LinkedIn URL）
- [ ] 确认所有包含 PII 的文件位于 gitignored 目录

### 2.3 Git 历史审计
- [ ] 当前仓库 HEAD 是否包含以下模式：`@`+邮箱域名、手机号（8/11 位）、香港身份证、真实姓名
- [ ] 历史提交是否被 `git filter-repo` 完全清理（运行 `git log --all -S "<name>" --oneline`）
- [ ] `.git` 目录大小是否匹配 167 个跟踪文件（~1MB），而非残留大文件（当前 47MB）

### 2.4 GDPR/合规
- [ ] README/SETUP.md 是否说明数据完全本地存储
- [ ] 是否有数据导出/删除流程文档
- [ ] Google Sheets 推送是否未经用户确认自动执行

### 必须回答问题
1. `.gitignore` 覆盖是否完整？（pass/fail，如有缺失列出）
2. Git 历史是否有 PII 残留？（pass/fail，如有列出匹配行）
3. 用户是否能完全控制数据去向（本地 vs 云端）？（yes/no）
4. 是否符合 GDPR"数据最小化"原则？（pass/fail）

---

## 3. 代码质量与架构审计 (Code Quality & Architecture)

**审计目标**: 评估可维护性、耦合度、架构决策质量。

### 3.1 模块组织
- [ ] Python 工具是否按功能域分目录（`tools/fresh_24h/`、`tools/job_materials/`、`tools/core_applications/`）
- [ ] 门户 CLI 是否遵循统一结构（`src/helpers.ts`、`src/cli.ts`、`tests/`）
- [ ] 是否存在循环导入（Python）或循环依赖（TypeScript）
- [ ] 是否存在过度耦合（跨模块直接访问内部函数）

### 3.2 代码模式
- [ ] 函数是否单一职责（是否超过 200 行）
- [ ] 错误处理是否一致（try/except 模式、writeError 函数）
- [ ] 状态管理是否使用原子写入（`write_tmp + fsync + rename` 模式）
- [ ] 硬编码是否提取为常量（magic numbers、URLs、阈值）

### 3.3 代码异味
- [ ] 是否存在死代码（未被调用的函数、注释掉的代码块）
- [ ] 是否存在重复代码（跨模块或同模块内）
- [ ] 是否有 `TODO`/`FIXME`/`XXX` 未解决
- [ ] 是否存在应拆分的超大类（>500 行单文件）

### 3.4 文档与注释
- [ ] 公共 API/函数是否有文档字符串
- [ ] 注释是否是解释"为什么"而非"是什么"
- [ ] 是否存在陈旧/误导性注释

### 必须回答问题
1. 架构评分（1-5）：模块化、低耦合、高内聚
2. 最大的单文件是多少行？是否需要拆分？
3. 是否有循环依赖？
4. 列出 3 个最需要重构的模块

---

## 4. 可靠性与韧性审计 (Reliability & Resilience)

**审计目标**: 评估系统在异常条件下的行为。

### 4.1 错误恢复
- [ ] 每个门户 CLI 是否有 429/5xx 重试逻辑（backoff 500ms→8s，最多 6 次重试）
- [ ] 是否有 retry-backoff 测试验证重试契约
- [ ] 网络故障时是否快速失败（非无限制等待）
- [ ] 缓存脏数据时是否有 TTL 过期机制

### 4.2 状态完整性
- [ ] `refresh_state.py` 是否使用原子写入（tmp + fsync + rename）
- [ ] 状态文件损坏时是否有备份恢复
- [ ] Google Sheets 写入是否使用"先读后写"合并模式（非覆盖）
- [ ] `jd_cache.py` 是否有写入竞态保护

### 4.3 优雅降级
- [ ] 单个门户失败是否阻止其他门户扫描
- [ ] CTgoodjobs cookie 过期时是否有明确错误提示（而非静默失败）
- [ ] PDF 编译失败时是否有明确错误 + 修复建议
- [ ] `pdftotext` 不可用时 ATS 检查是否优雅跳过

### 4.4 速率限制
- [ ] 门户调用之间是否有适当延迟（避免被封锁）
- [ ] 是否有并发控制（避免同时发起过多请求）
- [ ] bun 进程是否有超时机制

### 必须回答问题
1. 所有门户 CLI 的 retry-backoff 契约是否一致？（pass/fail）
2. 状态写入是否原子化？（pass/fail，如有非原子操作列出）
3. 单点故障是否级联？（列出可能的级联路径）
4. 速率限制是否充足防止被门户封禁？（pass/fail）

---

## 5. 测试与验证审计 (Testing & Verification)

**审计目标**: 评估测试覆盖率和有效性。

### 5.1 测试覆盖率
- [ ] 列出每个 Python 模块的测试文件对应关系
- [ ] 识别完全没有测试覆盖的模块
- [ ] 测试是否覆盖核心管线（scan → score → push）的集成路径
- [ ] 是否有回归测试保护已修复的 bug

### 5.2 测试质量
- [ ] 测试是否验证行为而非实现细节
- [ ] 断言是否明确（避免模糊的 `assertTrue`）
- [ ] 是否有测试数据与生产数据分离
- [ ] 是否有测试依赖外部服务（网络/文件系统/Google API）

### 5.3 测试配置
- [ ] 是否有 `pytest.ini`/`pyproject.toml` 配置测试发现路径
- [ ] 是否有 CI 流水线运行测试
- [ ] 是否有 coverage 阈值
- [ ] 是否有 lint/type-check 步骤

### 5.4 边界条件测试
- [ ] 空输入（空搜索结果、空 JD、空简历）
- [ ] 极大输入（超长 JD、异常多技能）
- [ ] 编码问题（中文、繁体、emoji、特殊字符）
- [ ] 时区边界（UTC+8 转换、跨天查询）

### 5.5 Portal CLI 测试清单
| Portal | parsing | retry-backoff | CLI flags | search | detail |
|--------|---------|---------------|-----------|--------|--------|
| linkedin-search | ✅ parsing.test.ts | ✅ retry-backoff.test.ts | ✅ cli-flag-validation.test.ts | ✅ search.test.ts | ❌ |
| jobsdb-search | ❌ | ✅ retry-backoff.test.ts | ❌ | ✅ smoke.test.ts | ❌ |
| ctgoodjobs-search | ❌ | ✅ retry-backoff.test.ts | ❌ | ✅ smoke.test.ts | ❌ |
| freehire-search | ✅ parsing.test.ts | ✅ retry-backoff.test.ts | ✅ cli-flag-validation.test.ts | ✅ commands.test.ts | ❌ |

### 必须回答问题
1. 测试覆盖率估算（%）？最大盲区在哪？
2. 是否有模块零测试？列出
3. 测试套件是否需要在本地 CI-ready（无外部依赖）
4. 哪些 portal CLI 缺少 detail/parsing/CLI-flag 测试？

---

## 6. 文档与上手审计 (Documentation & Onboarding)

**审计目标**: 评估新用户/开发者能否独立使用和贡献。

### 6.1 README 质量
- [ ] 是否在 30 秒内说清楚"这是什么、给谁用"
- [ ] 是否有快速开始指南（从 clone 到第一次 scan）
- [ ] Job-ID 格式（`{A-F}{0-3}-{sequence}`）是否有解释
- [ ] 是否有英文版（README_EN.md）

### 6.2 安装指南
- [ ] 前置依赖是否列全（Python 3.10+、Bun、LibreOffice、可选 Playwright）
- [ ] `/setup` 流程是否文档化
- [ ] 门户 cookie 获取方式是否有说明（CTgoodjobs）
- [ ] 是否有已知问题/troubleshooting

### 6.3 命令/技能文档
- [ ] 每个斜杠命令（`/setup`、`/scan`、`/push`、`/materials`）是否有 `.claude/commands/*.md` 文档
- [ ] 每个公开 skill（job-application-assistant、upskill 与四个门户 skill）是否有 SKILL.md
- [ ] 每个门户技能是否有 url-reference.md（API schema）

### 6.4 架构文档
- [ ] 是否有架构决策记录（ADR）
- [ ] 是否有数据流图
- [ ] 是否有贡献指南（CONTRIBUTING.md）

### 必须回答问题
1. 新用户从 clone 到第一次 `/scan` 需要多少步？是否有缺失步骤？
2. README 是否覆盖所有核心命令？
3. 哪些文档引用指向不存在的文件（broken links）
4. 上手体验评分（1-5）

---

## 7. 工作流完整性审计 (Workflow Integrity)

**审计目标**: 端到端验证核心管线是否完整、正确。

### 7.1 /setup 管线
- [ ] `setup.py` 是否检查所有前置依赖
- [ ] 简历解析是否提取姓名/电话/邮箱/技能
- [ ] 生成 `queries.json` 时是否保留 3 个强制检索类别
- [ ] 是否询问"先做基础版还是先检索"

### 7.2 /scan 管线
- [ ] `temp_two_pass.sh` 是否处理 temp/daily/N-hours 模式
- [ ] `fresh_24h_scan.py` 是否正确去重（按 tracker CSV）
- [ ] 两段评分 gate（3.3）是否正确应用
- [ ] 扫描结果是否写入正确的目录

### 7.3 /push 管线
- [ ] Google Sheets 写入是否合并而非覆盖
- [ ] 批次标记（beige/本轮新增/入表时间）是否正确
- [ ] 旧批次降级（本轮新增→否）是否正确
- [ ] 是否有新 sheet 创建逻辑

### 7.4 /materials 管线
- [ ] `tools/job_materials` 模块是否可被 `python3 -m` 导入
- [ ] `--job-id` 解析是否跨目录搜索
- [ ] base 同步 + fact-check + tailor 管线是否完整
- [ ] 不存在的 job-id 是否有清晰错误

### 必须回答问题
1. `/setup` 到 `/apply` 的完整端到端流程是否无断裂？
2. 哪些步骤依赖手动操作（仍需自动化）
3. Job-ID 在不同模块间是否一致传递
4. 评分阈值（3.3）硬编码在了多少个文件中？是否应该集中管理

---

## 8. AI Agent 治理审计 (Agent Governance)

**审计目标**: 评估 AI agent 的指令安全性、边界控制和可审计性。

### 8.1 指令安全性
- [ ] `CLAUDE.md`/`AGENTS.md` 中是否有 prompt 注入风险（如允许从 URL 注入指令）
- [ ] Job posting 文本是否被安全处理（防止 prompt injection via job description）
- [ ] 外部数据（JD 文本、搜索结果）是否被当作可信内容直接执行

### 8.2 工具边界
- [ ] Agent 是否有不必要的文件系统写入权限
- [ ] Agent 是否可以执行任意 shell 命令（非白名单）
- [ ] Agent 是否可以发起未授权的网络请求

### 8.3 行为规则
- [ ] 是否有禁止编造履历的显式规则
- [ ] 是否有禁止自动生成材料（必须在用户命令下）的规则
- [ ] 是否有"确认事实→写回 profile"的规则
- [ ] 是否有"海投识别"规则

### 8.4 可审计性
- [ ] Agent 每次操作是否有日志
- [ ] CV 生成是否有 ATS 验证步骤
- [ ] 评分决策是否有解释（非黑盒）

### 必须回答问题
1. 是否存在 prompt injection 攻击面？列出 3 个
2. Agent 权限边界是否充分？哪些权限应加入黑名单
3. "禁止编造"规则是否在全部命令/skill 中一致执行
4. 审计日志覆盖了哪些操作？哪些缺口需补齐

---

## 审计报告模板

审计 agent 完成上述 8 个域后，按以下模板输出报告：

```markdown
# Jobsflow 外部审计报告

**审计日期**: YYYY-MM-DD
**审计 agent**: [name]
**仓库版本**: [git commit hash]

## 总览

| 域 | 评分 (1-5) | 关键风险数 | 阻断项 |
|----|-----------|-----------|-------|
| 1. 安全与供应链 | - | - | - |
| 2. 隐私与数据保护 | - | - | - |
| 3. 代码质量与架构 | - | - | - |
| 4. 可靠性与韧性 | - | - | - |
| 5. 测试与验证 | - | - | - |
| 6. 文档与上手 | - | - | - |
| 7. 工作流完整性 | - | - | - |
| 8. AI Agent 治理 | - | - | - |

## 🔴 阻断项 (Blocker - 必须修复才能发布)
1. ...
2. ...

## 🟡 高风险 (High - 建议尽快修复)
1. ...
2. ...

## 🔵 中风险 (Medium - 后续迭代修复)
1. ...
2. ...

## ⚪ 低风险/建议 (Low - 可选)
1. ...
2. ...

## 各域详细发现

### 1. 安全与供应链
...

### 2. 隐私与数据保护
...

(等等)
```

---

## 快速使用

将此手册作为审计 prompt：

```bash
# 对 Claude Code
cat docs/AUDIT.md | claude

# 对其他 agent
# 复制 AUDIT.md 全文作为 prompt，附加：
# "请对当前仓库执行此审计手册中的所有检查项。
#  对每个检查项给出 pass/fail/risk，附文件路径+行号。
#  最后输出按报告模板格式的完整审计报告。"
```
