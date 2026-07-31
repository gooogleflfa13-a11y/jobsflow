# Jobsflow 外部审计报告

**审计日期**: 2026-07-31  
**审计 agent**: OpenAI Codex  
**仓库版本**: `4bb72ad86ad646542cb5418a6f4ec780e8ca634f`（审计对象为含未提交改动的当前工作树）  
**审计依据**: `docs/AUDIT.md` v1.0  
**审计方法**: 全 tracked 文件静态审查、Git 历史/对象检查、Python 与 Bun 测试、四门户 typecheck、本地 lockfile `bun audit`、配置守卫与查询验证。

## 结论

当前 Jobsflow **不满足发布条件**。系统已有清晰的功能域划分、两段评分、门户降级和安全守卫基础，但存在 5 类发布阻断问题：

1. tracked 文件与 Git 历史仍含简历级个人资料和个人 tracker。
2. 全门户失败时，`/scan` 在返回失败前推进刷新游标，下一次 temp scan 可能永久漏岗。
3. 官方 `/materials --job-id` 调用与 argparse 契约冲突，核心材料命令无法按文档执行。
4. `/setup` 不生成 scan 强制需要的主 tracker，新用户选择“先检索”会直接失败。
5. `/apply` 与强制 PDF 规则在引擎和页数上正面冲突，且与 `/materials` 是两套未衔接的管线。

另外，Google Sheets/CSV 公式注入、外部 JD prompt injection、未声明 Python 依赖、CI 测试发现错误和非原子 Sheet 重写均属于高风险。

## 总览

| 域 | 评分 (1-5) | 关键风险数 | 阻断项 |
|----|-----------|-----------|-------|
| 1. 安全与供应链 | 2.0 | 6 | 0 |
| 2. 隐私与数据保护 | 1.0 | 7 | 1 |
| 3. 代码质量与架构 | 2.5 | 6 | 0 |
| 4. 可靠性与韧性 | 2.0 | 7 | 1 |
| 5. 测试与验证 | 2.0 | 7 | 0 |
| 6. 文档与上手 | 1.5 | 8 | 1 |
| 7. 工作流完整性 | 1.0 | 9 | 3 |
| 8. AI Agent 治理 | 2.0 | 6 | 0 |

## 阻断项 (Blocker)

1. **隐私基线失效**：`CLAUDE.md:23-78`、`.claude/skills/job-application-assistant/01-candidate-profile.md`、`02-behavioral-profile.md` 是 tracked 的简历级个人资料；Git 历史还包含 `JobSearch_2026/02_Tracker/*.csv|xlsx`。
2. **失败扫描推进游标**：`fresh_24h_scan.py:830-840` 先记录 refresh，`:871-873` 才返回 fatal，故障窗口职位可能被下一次 temp scan 跳过。
3. **材料命令不可用**：`.claude/commands/materials.md:16` 只传 `--job-id`，但 `job_materials/__main__.py:470` 强制 `--package`；不存在 job-id 还会在 `:326` 对 `None` 调用 `is_dir()`。
4. **首次 scan 缺主 tracker**：`setup.py:372-404` 只创建 schema；`fresh_24h_scan.py:642-649` 没有 `hk_apply_list_*.csv` 就退出。
5. **投递规范冲突**：`apply.md:66-79,178-219` 要求 LaTeX 和 2 页 CV，`system_rules.md:24-34,50-56` 要求 LibreOffice headless 和 1 页 CV/CL。

## 高风险 (High)

1. `push_to_gsheet.py:751-766` 用 `USER_ENTERED` 写入未转义的外部门户文本，Google Sheets/CSV 可发生公式注入。
2. `/apply`、reviewer prompt、外部 LLM 三处原样接收不可信 JD，缺少 prompt-injection 数据边界。
3. 仓库没有任何 Python 依赖清单或 lockfile；fork 无法复现环境或进行版本化 CVE 审计。
4. `bun.lock` 被 `.gitignore:3` 全局忽略，四门户依赖解析不可复现。
5. `push_to_gsheet.py:763-766` 先 clear 再 update，无回滚；API 中断可清空或部分覆盖 tab。
6. CI 使用 unittest，漏跑 21 个 pytest 风格测试；门户测试完全未进入 CI，typecheck matrix 还引用不存在的门户。
7. pass-2 低于 3.3 的行仍默认入表，违反 `system_rules.md:76-80`。
8. `setup.py:352-369` 把候选人姓名/意向写入 tracked `queries.json`。
9. README 的“数据留在本地”没有披露 Google Sheets 与可选外部 LLM 数据流。

## 中风险 (Medium)

1. 四门户 fetch 无请求级 timeout，且忽略 `Retry-After`。
2. JD cache、scan run log、seen file、score meta 等多处直接覆盖写，无原子性或锁。
3. `fresh_24h_scan.main`、`careerops_quickscore.score_job`、`push_to_gsheet.main` 均超过 300 行。
4. `job_materials` 通过修改 `sys.path` 反向导入 `fresh_24h` 内部模块，形成双向域耦合。
5. Google service account 申请完整 Drive scope，超出按 sheet ID 写表的常规最小权限。
6. 英文 README、SETUP、CONTRIBUTING 仍描述旧 `jobsflow`/Danish/`/scrape` 系统。
7. `.env.development`、`.env.test` 等常见变体未被 `.gitignore` 覆盖。
8. `security_guards.py` 的关键隐私规则清单不完整，不能防止未来删除 `JobSearch_2026/`、`.env*`、个人 config/MCP ignore。

## 低风险/建议 (Low)

1. 把 `3.3`、重试参数、超时和速率策略集中到单一配置。
2. 将重复的门户 retry/JSON 错误契约抽为共享、可测试组件。
3. 增加 ADR，记录为何选择三门户/四门户、teaser 降级、外部 LLM 与 Google Sheets 数据边界。
4. 为 run log、materials log 和 apply review log定义统一 schema、版本号和 retention。

---

## 1. 安全与供应链

### 检查结果

| 检查项 | 结论 | 证据 |
|--------|------|------|
| 四门户已知 CVE | PASS（本机快照）/ RISK（仓库） | 四个本地 lockfile 的 `bun audit` 均为 “No vulnerabilities found”；lockfile 未 tracked |
| Python CVE | RISK | 无 `requirements.txt`/`pyproject.toml`/lock；代码依赖 docx、pypdf、openpyxl、gspread、Google auth、Playwright |
| 已废弃依赖 | RISK | 无 manifest，无法系统确认；门户无 runtime dependencies |
| 依赖精确锁定 | FAIL | 四个 `package.json:17-18` 使用 `^5.4.0` 和 `latest`；`.gitignore:3` 忽略 lock |
| lifecycle scripts | PASS | 四 manifest 只有 start/test/typecheck；`security_guards.py:70,122-145` 拦截 install lifecycle |
| trustedDependencies | PASS | 当前无；守卫会拦截 |
| 用户输入拼 shell | PASS | scan/enrich 均以 argv list 调子进程，如 `fresh_24h_scan.py:212-236` |
| Shell 变量引用 | RISK | `temp_two_pass.sh:42` 展开未引用 `$HOURS`，但来源受数字正则限制 |
| 权限白名单 | PASS / RISK | 当前 settings 全在 `ALLOWED_PERMISSIONS`；`Bash(bun run:*)` 与 `pdftotext:*` 仍较宽 |
| 未审查全局通配符 | PASS | 无 `Bash(*)`、`Bash(curl:*)` |
| security guard 进入 CI | PASS | `.github/workflows/ci.yml:47-55` |
| `.env` 全变体 | FAIL | `.gitignore:42-44` 仅三种；动态检查显示 `.env.development`/`.env.test` 未忽略 |
| personal config / MCP | PASS | `.gitignore:45-46` |
| 硬编码密钥 | PASS（静态模式扫描） | tracked 源码命中均为 placeholder、环境变量或测试；未发现实值 credential |
| Google 权限最小化 | FAIL | `push_to_gsheet.py:620-624` 同时申请 Sheets + Drive |
| Sheet/CSV 注入 | FAIL | `push_to_gsheet.py:751-766` 未防公式并使用 `USER_ENTERED` |

### 必答问题

1. **是否存在已知 CVE 的高危依赖？** `RISK`。本机四个 Bun lock 快照无已知漏洞；Python 与 clean-clone Bun 依赖因未锁定而不可验证。
2. **`bun install` 是否有任意代码执行风险？** `PASS（当前 manifest）`。无 lifecycle/trustedDependencies；仍保留普通上游供应链风险。
3. **权限白名单是否有未审查条目？** `PASS`。所有条目均在静态白名单；白名单本身仍应缩窄。
4. **是否有硬编码密钥？** `PASS`。未发现 tracked 实值密钥。

---

## 2. 隐私与数据保护

### 检查结果

| 检查项 | 结论 | 证据 |
|--------|------|------|
| CV/CL 通配符 | PASS | `.gitignore:97-102` 覆盖任意扩展与大小写前缀 |
| 个人工作区 | PASS（当前 ignore） | `.gitignore:28-31` |
| tracker / salary / seen | PASS | `.gitignore:22-23,112-116` |
| ignore negation白名单 | PASS | `security_guards.py:63-68`，当前守卫通过 |
| ignore 守卫完整性 | FAIL | `REQUIRED_IGNORE_RULES:43-56` 不含 workspace、env、config、MCP 等关键规则 |
| 简历数据流位置 | FAIL | `setup.py:322-369` 同时写 ignored config 与 tracked queries；tracked profile 文件已有简历级信息 |
| 所有 PII 均在 ignored 区域 | FAIL | `CLAUDE.md:23-78`、tracked profile skills、历史 tracker |
| 当前 tracked 邮箱/电话/HKID | PASS（模式扫描） | 当前命中为 example/placeholder；未发现实值 |
| 当前 tracked 广义 PII | FAIL | 教育、经历、资格、行为资料足以重识别个人 |
| Git 历史清理 | FAIL | 历史提交含 `JobSearch_2026/` tracker CSV/XLSX；`.git` 约 51MB |
| 历史大文件清理 | FAIL | pack 含约 70MB/67MB 的 Obscura 二进制 blob |
| 本地存储披露 | FAIL | `README.md:24-25` 与 Google Sheets、外部 LLM 实际能力不一致 |
| 数据导出/删除流程 | FAIL | `/reset` 只覆盖部分 documents；无 JobSearch/cache/config/Google Sheet 完整导出与删除手册 |
| Sheet 是否自动推送 | PASS | `scan.md:31` 要求确认；`/push` 是显式命令 |

### 数据流

```text
简历 PDF/DOCX
  -> setup.py 内存提取
  -> config.personal.json/.env（ignored）
  -> queries.json（tracked，含姓名/意向，FAIL）
  -> 本地 scan CSV/JD cache/评分
  -> Google Sheets（用户显式 /push）
  -> package + factchecked A-F base
  -> 可选外部 LLM（JD + skills + base bullets）
  -> 本地 CV/CL/PDF
```

### 必答问题

1. **`.gitignore` 覆盖是否完整？** `FAIL`。缺 `.env.*` 通配保护，且守卫的 required rule 集不完整。
2. **Git 历史是否有 PII 残留？** `FAIL`。存在个人 tracker 文件和简历级 tracked profile。
3. **用户是否能完全控制数据去向？** `YES，但披露不足`。Sheet 与 LLM 都需要显式动作/flag，但主文档误导为完全本地。
4. **是否符合 GDPR 数据最小化？** `FAIL`。tracked profile、queries 姓名、外部 LLM payload、过宽 Drive scope 均超出最小化。

---

## 3. 代码质量与架构

### 检查结果

| 检查项 | 结论 | 证据 |
|--------|------|------|
| Python 按域分目录 | PASS | `fresh_24h`、`job_materials`、`core_applications` |
| 门户统一结构 | PASS | 四门户均有 cli/helpers/commands/tests |
| 循环依赖 | PASS（import-time）/ RISK（域级） | 未发现直接循环；`job_materials/enrich.py:47-65` 反向导入 fresh 内部 |
| 内部函数耦合 | RISK | 多模块 `sys.path.insert` + 无包名 sibling import |
| 单一职责 | FAIL | 327/304/301 行函数 |
| 错误处理一致性 | RISK | Python 广泛 `except Exception`；TS 错误 JSON 结构较统一 |
| 原子状态写入 | PARTIAL | refresh 正确；cache/run/meta/seen/Sheet 不原子 |
| magic numbers/URLs/阈值 | FAIL | `3.3` 分散在 14 个文件；重试参数复制四份 |
| 死代码 | RISK | 未见明显 tracked 死代码；存在 ignored deprecated WPS/Obscura 工具 |
| 重复代码 | FAIL | 四门户 retry、render、错误输出重复；URL/cache 写入重复 |
| TODO/FIXME/XXX | PASS | 未发现真实未处理注释 |
| 超大文件 | FAIL | 最大 878 行，另有 799、626、540 行 |
| 公共 API 文档 | PARTIAL | 核心函数多有 docstring，部分 helper/异常路径无契约文档 |
| 注释准确性 | FAIL | scan 仍写 3.0 旧策略；`AGENT_REFRESH.md` 有 3.5/3.3 矛盾 |

### 必答问题

1. **架构评分**：`2.5/5`。目录域清楚，但主函数过大、阈值分散、双向域依赖和脚本式 import 降低可维护性。
2. **最大单文件**：`fresh_24h_scan.py` 878 行；需要拆分为 portal runner、过滤/去重、持久化、run policy。
3. **是否有循环依赖？** 没有直接 import-time 循环；存在 `fresh_24h <-> job_materials` 域级双向依赖。
4. **最需重构模块**：`fresh_24h_scan.py`、`push_to_gsheet.py`、`careerops_quickscore.py`。

---

## 4. 可靠性与韧性

### 检查结果

| 检查项 | 结论 | 证据 |
|--------|------|------|
| 四门户 429/5xx retry | PASS | 初次 + 6 retry，500ms→8s |
| retry 测试 | PASS（工作树）/ FAIL（CI） | 四个测试均通过；文件/测试未被 CI 执行 |
| 网络快速失败 | PARTIAL | Python 父进程 90s timeout；TS fetch 本身无 AbortSignal |
| cache TTL | PASS | `jd_cache.py:47-79` 默认 60 天 |
| refresh 原子写 | PASS | `refresh_state.py:119-149` |
| 状态损坏恢复 | PASS | `refresh_state.py:92-116` 从 `.bak` 恢复 |
| 失败扫描游标 | FAIL/BLOCKER | fatal 之前写 state |
| Sheet 合并 | PASS（逻辑）/ FAIL（原子性） | 先读旧行合并，但 clear→update 无回滚 |
| JD cache 竞态 | FAIL | `jd_cache.py:43` 直接写 |
| 单门户失败降级 | PASS | 记录 error 后继续其他 query/portal |
| CT cookie 提示 | PASS | `fresh_24h_scan.py:701-714` |
| PDF 失败提示 | PASS（静态） | converter 返回清晰异常/建议；未执行真实 PDF |
| ATS 无 pdftotext | PASS（规则） | `apply.md:223-225` 明确 warning + visual fallback |
| 门户调用间延迟 | PASS（基础） | scan 默认 0.6s 串行 |
| 并发控制 | PASS | 无并发洪泛；完全串行 |
| Bun 超时 | PARTIAL | scan 父进程 90s；直接 CLI 无 fetch timeout |
| Retry-After/配额/熔断 | FAIL | 四 helper 均未读取 Retry-After，无 per-portal circuit breaker |

### 必答问题

1. **所有门户 retry-backoff 是否一致？** `PASS`。核心重试次数与退避一致。
2. **状态写入是否原子化？** `FAIL`。只有 refresh state 原子；JD cache、run/seen/meta、Sheet 均非原子。
3. **单点故障是否级联？** 有：
   - 全门户/部分门户错误 + 0 新岗 → 先推进 refresh → 下次 temp 漏岗。
   - Sheet clear 后 update 失败 → 远端 tab 数据丢失。
   - `--package` 契约错误 → materials 整段不可达。
   - Python 依赖缺失 → setup 通过但后续模块运行时失败。
4. **速率限制是否足够防封禁？** `FAIL/RISK`。串行与 0.6s 是基础保护，但没有 Retry-After、配额、熔断和直接 fetch timeout，无法保证。

---

## 5. 测试与验证

### 覆盖矩阵

| 模块域 | 测试 | 结论 |
|--------|------|------|
| security guards | `test_security_guards.py` | 较完整，unittest/CI 会跑 |
| salary / conversion | `test_salary_lookup.py`, `test_convert_salary_excel.py` | 较完整 |
| core manifest | `test_core_application_manifest.py` | pytest-only，依赖真实 ignored tracker，当前 2 fail |
| core validator | `test_core_application_validator.py` | pytest-only，离线边界覆盖较好 |
| scan/score | `test_fresh_scan_helpers.py` | 仅 4 个 helper 测试，无 orchestration |
| push/Sheet | 无 | 零覆盖 |
| refresh/job_id/batch/cache | 无直接测试 | 大盲区 |
| job_materials | 无 | 大盲区 |
| setup/PDF/browser | 无 | 大盲区 |

### 动态结果

| 命令 | 结果 |
|------|------|
| `python -m unittest discover -s tests -t . -v` | 60 passed；漏跑 pytest functions |
| `python -m pytest -q` | 86 passed, 2 failed；失败来自硬编码个人 tracker 与固定行数期望 |
| LinkedIn `bun test` | 20 passed |
| FreeHire `bun test` | 29 passed |
| JobsDB `bun test` | 6 passed, 2 live-network failed |
| CTgoodjobs `bun test` | 6 passed, 2 live-network/cookie failed |
| 四门户 `bun run typecheck` | 全通过 |
| `compileall` | 通过（pycache 定向 `/tmp`） |
| `security_guards.py` | 通过 |
| `validate_queries.py` | 27 queries / 3 mandatory buckets，通过 |
| `lint_skills.py` | 7 skills / 12 commands，通过 |

### 边界条件

| 检查项 | 结论 |
|--------|------|
| 空输入 | PARTIAL：CLI flags、空结果有部分覆盖；完整空 scan/push 无集成测试 |
| 极大输入 | FAIL：无超长 JD、大量 jobs/skills/Sheet rows 测试 |
| 编码 | PARTIAL/PASS：LinkedIn/FreeHire entity/emoji 解析有测试；Python 全链路无 |
| 时区 | FAIL：HKT/UTC 跨天、DST 无测试 |
| 外部服务隔离 | FAIL：JobsDB/CT smoke 直接访问生产门户；manifest 直接用个人 tracker |
| 回归测试 | PARTIAL：retry、entity、安全守卫有；阻断级流程缺陷无 |
| coverage threshold | FAIL：无 |
| Python lint/typecheck | FAIL：无 |

### Portal 测试清单

| Portal | parsing | retry | CLI flags | search | detail |
|--------|---------|-------|-----------|--------|--------|
| LinkedIn | PASS | PASS | PASS | mocked/offline PASS | parser PASS；command 缺 |
| JobsDB | FAIL（无离线 toResult） | PASS | 仅基础 smoke | live only | live only |
| CTgoodjobs | FAIL（无离线 toResult/header） | PASS | 仅基础 smoke | live only | live only |
| FreeHire | PASS | PASS | PASS | mocked PASS | mocked PASS |

### 必答问题

1. **测试覆盖率估算**：核心工具语句约 `20-30%`，取中值约 `25%`。最大盲区为 scan→score→push、materials、状态与 PDF/browser。
2. **零测试模块**：`setup.py`、`push_to_gsheet.py`、`refresh_state.py`、`job_id.py`、`batch_mark.py`、`portal_jd_browser.py`、PDF exporters、`promote_fresh_to_main.py`、绝大多数 `job_materials/*`。
3. **测试是否本地 CI-ready、无外部依赖？** `NO`。pytest 依赖个人文件；JobsDB/CT smoke 依赖网络/cookie；CI 还漏跑 pytest tests。
4. **Portal 缺口**：JobsDB/CT 缺离线 parsing 与完整 flag tests；LinkedIn 缺 detail command；JobsDB/CT detail 只有 live；FreeHire 最完整。

---

## 6. 文档与上手

### 检查结果

| 检查项 | 结论 |
|--------|------|
| 30 秒说清用途/用户 | PASS（中文 README） |
| 快速开始可执行 | FAIL：缺依赖、缺 tracker 初始化 |
| Job-ID 解释 | PASS：`README.md:117-159` |
| 英文版 | FAIL：文件存在但命令体系不可用 |
| 前置依赖完整 | FAIL：无 Python dependency manifest；SETUP 与 setup check 均不完整 |
| `/setup` 文档 | PARTIAL：中文命令文档正确，SETUP.md 旧 |
| CT cookie 文档 | PASS：skill/url-reference 有说明 |
| troubleshooting | PARTIAL：旧框架问题为主 |
| 4 核心 command 文档 | PASS：setup/scan/push/materials 均有 |
| `/apply` 主文档可发现性 | FAIL |
| 每个 AI skill 有 SKILL.md | PASS |
| 每门户有 url-reference | PASS |
| ADR | FAIL |
| 数据流图 | PASS：`docs/AUDIT.md` 有，但属于审计手册而非正式架构文档 |
| CONTRIBUTING | FAIL：存在但与当前系统漂移 |

### Broken/stale references

- `docs/system_rules.md:6` → 不存在的 `docs/handoff_manual.md`
- `CLAUDE.md:13` → clean clone 不存在的 `02_Tracker/README.md`
- `README_EN.md:136` → 不存在的 `requirements.txt`
- `README_EN.md:139-173` → 不存在的 `jobsflow` Python package/commands
- `SETUP.md:125-140`、CI matrix → 不存在的 Danish portal directories
- `CONTRIBUTING.md:26,42` → 不存在的 `/scrape` 主线

### 必答问题

1. **clone 到第一次 `/scan` 需要多少步？** 名义 3 步；实际至少 6 步：clone、安装系统依赖、安装未声明 Python 包、安装门户、运行 setup、手工创建主 tracker、再 scan。tracker 创建步骤缺失，故按文档无法完成。
2. **README 是否覆盖所有核心命令？** `NO`。覆盖 setup/scan/push/materials，未覆盖手册定义的 `/apply`，也未说明两条材料管线。
3. **broken links**：见上方 6 项。
4. **上手体验评分**：`1.5/5`。

---

## 7. 工作流完整性

### `/setup`

| 检查项 | 结论 |
|--------|------|
| 检查全部前置依赖 | FAIL |
| 提取姓名/电话/邮箱/技能 | PARTIAL：姓名/电话/邮箱/教育/语言；技能主要由分类/证据后续处理 |
| 保留 3 强制检索类别 | 当前 config PASS；生成器 FAIL，可能覆盖为单一 mandatory bucket |
| 问基础版还是检索 | PASS：`setup.py:482-490` |
| 生成可供 scan 的主 tracker | FAIL |
| 安装四门户 | FAIL：`PORTAL_SKILLS` 缺 FreeHire |

### `/scan`

| 检查项 | 结论 |
|--------|------|
| temp/daily/N-hours | PASS |
| tracker 去重 | PASS（URL + company/title） |
| pass-1 gate 3.3 | PASS |
| pass-2 低分不入表 | FAIL |
| 结果目录 | PASS |
| 四门户 | FAIL：主线实际三门户 |
| 错误时不推进状态 | FAIL/BLOCKER |

### `/push`

| 检查项 | 结论 |
|--------|------|
| 合并而非覆盖 | PASS（逻辑） |
| 批次/米色/入表时间 | PASS（静态） |
| 旧批降级 | PASS：`batch_mark.py:38-49` |
| 新建 sheet | PASS：`push_to_gsheet.py:647-653` |
| 原子/可回滚 | FAIL |
| 外部文本安全写入 | FAIL（公式注入） |

### `/materials` 与 `/apply`

| 检查项 | 结论 |
|--------|------|
| `python -m tools.job_materials` 可导入 | PASS |
| `--job-id` 跨目录搜索 | FAIL：argparse 冲突，且忽略 `JOBSEARCH_ROOT` |
| base sync/factcheck/tailor | PARTIAL：模块存在，官方命令不可达 |
| 不存在 job-id 清晰错误 | FAIL：复现 `AttributeError` |
| 生成完整 CV/CL/PDF | FAIL：materials 只生成 plan/status |
| `/apply` 接续 materials package | FAIL：无共享 contract |
| PDF 规则一致 | FAIL |

### 必答问题

1. **`/setup` 到 `/apply` 是否无断裂？** `NO`。tracker 初始化、materials 参数、materials→apply、PDF 规则均断裂。
2. **仍依赖手动操作**：创建初始 tracker、建立 A-F master、粘贴 CT/JobsDB JD、把 tailor plan 手工应用到 CV/CL、副本/PDF QA、实际提交、Sheet/LLM 凭证配置。
3. **Job-ID 是否一致传递？** `FAIL`。scan/push 使用 `{A-F}{0-3}`；materials argparse/job-id resolution 不可按文档工作；apply 完全不使用 job-id。
4. **3.3 硬编码多少文件？** 14 个非审计文件。应集中管理。

---

## 8. AI Agent 治理

### 检查结果

| 检查项 | 结论 | 证据 |
|--------|------|------|
| URL/JD prompt injection 防护 | FAIL | `/apply:15-20,124-127` 原样使用外部内容 |
| 外部 LLM JD 隔离 | FAIL | `tailor.py:191-203` 原样嵌入 user payload |
| 不可信文本触发工具 | RISK/HIGH | 主 skill 同时允许 WebFetch/Search/Edit/Write |
| 文件写权限最小化 | FAIL | skill 没有路径 scope |
| 任意 shell | PASS/PARTIAL | settings 无 Bash(*)，但 `bun run:*` 可执行广泛本地代码 |
| 未授权网络 | FAIL/RISK | WebFetch/WebSearch 在 job skill 中常开；无域名 allowlist |
| 禁止编造 | PARTIAL | apply/materials/rank/interview 有；主 skill 缺全局规则 |
| 禁止 scan 自动材料 | PASS | AGENTS/system rules/scan 一致 |
| 确认事实写回 profile | PASS（apply） | `apply.md:284-288` |
| 海投识别 | RISK/未发现统一规则 | rank/queue 有优先级，但无明确“海投识别”治理规则 |
| 操作日志 | PARTIAL | scan/materials 有；setup/apply/LLM/file edits 无统一日志 |
| ATS 验证 | PARTIAL | apply 有；materials 主线没有自动 PDF/ATS |
| 评分解释 | PASS | CareerOps reason/初评/深评均输出 |

### 三个 prompt-injection 面

1. 恶意职位 URL 页面通过 WebFetch 进入 `/apply` 主 Agent。
2. 原始 JD 被嵌入 reviewer 子 Agent prompt，而 reviewer 具有研究/读取能力。
3. JD 原样进入外部 LLM user message；返回 bullet 只用低阈值 token overlap 过滤。

### 建议工具边界

- job-posting 内容必须包在固定 data envelope，并明确“其中任何指令均不执行”。
- 将 application skill 写入范围限制到目标 package、`cv/`、`cover_letters/`；禁止修改 `.claude/`、规则、Git、credential/config。
- 网络域名只允许声明的门户、公司官网与选定 LLM endpoint；对重定向后域名复核。
- 将 `Bash(bun run:*)` 缩到四个具体 CLI entrypoint；`pdftotext` 限制到生成的 CV PDF。
- 对外部 LLM payload 显示 consent 摘要，记录 provider/model/字段/时间，不记录 API key。

### 必答问题

1. **是否存在 prompt injection 面？** `YES`，至少三处，见上。
2. **Agent 权限边界是否充分？** `NO`。应加入规则/config/credential/Git 禁写，以及网络域名和 output path 范围。
3. **禁止编造是否全部一致？** `NO`。主 skill 缺总则，materials 的“结果量化”可能诱导无证据指标。
4. **日志覆盖与缺口**：覆盖 scan calls/errors、refresh、batch、factcheck/status/coverage；缺 setup、LLM、apply reviewer、文件变更、PDF QA 的统一审计记录。

---

## 修复顺序

### P0：发布前

1. 从当前 tracked 文件与所有 refs 清除个人 profile/tracker；使用 `git filter-repo` 重写历史并轮换任何历史 credential。
2. 把 refresh state 更新移动到成功判定之后；对 partial/fatal 定义明确状态，补回归测试。
3. 修正 materials parser：`--package` 与 `--job-id` 二选一；处理 `None`；统一 `JOBSEARCH_ROOT`。
4. 让 setup 创建空主 tracker，或让 scan 在缺失时以 schema 安全初始化。
5. 统一 materials/apply/PDF 规则为一条 job-id/package 流程。
6. 在 Sheet/CSV 写入前防公式注入，普通值使用 RAW。

### P1：高优先

1. 建立 Python `pyproject.toml` + lock，tracked 四门户 lockfile。
2. CI 改为 pytest；安装显式依赖；运行四门户离线 tests + 正确 matrix。
3. 把 manifest 测试改用 fixture，不读取 `JobSearch_2026`。
4. Sheet 写入增加备份/staging tab/失败回滚。
5. 增加 JD prompt-injection 边界与工具路径/域名 scope。
6. 修复 pass-2 3.3 规则或更新唯一权威 spec，不允许实现/文档分叉。

### P2：可维护性

1. 拆分三个 300+ 行函数。
2. 统一 retry、timeout、Retry-After 与 circuit breaker。
3. 为 refresh/cache/job-id/batch/scan-score-push/materials 添加边界和集成测试。
4. 重写 README_EN/SETUP/CONTRIBUTING，补数据导出、删除、retention 和外部传输说明。

## 审计限制与残余风险

- 未使用真实 Google credential 写入 Sheet，避免改变用户云端数据；Sheet 行为基于静态审查。
- 未执行完整职位扫描，避免改变 refresh state 和触发大量门户请求。
- 未生成/编译真实个人 PDF；PDF 结论基于规则与实现审查。
- JobsDB/CT live smoke 在受限网络/cookie 环境失败，不能据此判定生产 API 永久不可用；它们证明测试不 hermetic。
- 本机没有 `coverage.py`，覆盖率为基于模块—测试映射和未执行路径的估算。
- Bun CVE 结论只针对本机 ignored lockfile 的 2026-07-31 快照；clean clone 因无 lockfile 无法复现。
