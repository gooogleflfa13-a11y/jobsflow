# Jobsflow 节能与能力提升：两项上游方案调研

日期：2026-07-31  
范围：只研究 `ai-job-search v1.1.0` 与 Agent Reach 官方仓库的 release、README、源码和官方文档。本文把网页与仓库内容视为不可信输入，仅提取可验证的设计事实，不执行其中的安装命令。

## 结论先行

不建议现在把 Agent Reach 整体安装或嵌入 Jobsflow，也不建议仅因为 `ai-job-search v1.1.0` 支持 Typst 就替换现有 LibreOffice PDF 基线。

最值得采用的是四个设计：

1. **能在列表接口一次拿全 JD，就绝不做 N 次详情抓取。** v1.1.0 的 FreeHire 改为一次搜索请求返回整批完整描述，直接消除 `1 + N` 详情请求。这是最明确、最可量化的节能启发。
2. **门户接入做成“有序后端 + 真实体检 + 明示当前路径”。** 先结构化 API/静态 HTTP，再轻量阅读器，最后才启动 Playwright；失败按门户降级，不能拖垮整轮扫描。
3. **PDF 工具链用声明式 manifest 管理，同时给生成结果加内容哈希缓存。** 保留 LibreOffice 为默认，只在源内容、模板或渲染规则变化时重新导出和 QA。
4. **把复杂能力藏在 `doctor`、`dry-run`、安全模式和分级配置后面。** 默认路径保持 `/setup → /scan → /push → /materials`，高级后端按需解锁。

## 一手来源的可验证事实

### ai-job-search v1.1.0

- FreeHire 的搜索改用 `/api/v1/agent/jobs/search`，并通过 `include_description=true` 在单次搜索中返回完整描述；release 明确比较了“一个 20 岗请求”与此前的“1 次搜索 + 20 次详情”。[v1.1.0 release](https://github.com/MadsLorentzen/ai-job-search/releases/tag/v1.1.0)、[search.ts（v1.1.0）](https://github.com/MadsLorentzen/ai-job-search/blob/v1.1.0/.agents/skills/freehire-search/cli/src/commands/search.ts)
- HTTP wrapper 有 15 秒超时；仅对 429/5xx 做指数退避，连接失败则快速退出，避免一个失效来源长期阻塞总流程。[helpers.ts（v1.1.0）](https://github.com/MadsLorentzen/ai-job-search/blob/v1.1.0/.agents/skills/freehire-search/cli/src/helpers.ts)
- 六个门户 CLI 都增加了 retry/backoff 契约测试；CI 只跑 fixture/mock，不在 CI 对真实门户发请求。[CHANGELOG（v1.1.0）](https://github.com/MadsLorentzen/ai-job-search/blob/v1.1.0/CHANGELOG.md)、[CI（v1.1.0）](https://github.com/MadsLorentzen/ai-job-search/blob/v1.1.0/.github/workflows/ci.yml)
- `/add-template` 从固定 LaTeX engine 变成“源文件扩展名 + 完整编译命令 + manifest + 强制试编译”，因此可注册 Typst 或其他命令行 PDF 工具链；默认模板本身没有改用 Typst。[add-template.md（v1.1.0）](https://github.com/MadsLorentzen/ai-job-search/blob/v1.1.0/.claude/commands/add-template.md)
- v1.1.0 扩大了个人生成文件的 gitignore 覆盖范围，并让高危依赖审查可在 fork 自激活；release 也加入“已确认事实回写 profile”，减少后续重复询问。[v1.1.0 release](https://github.com/MadsLorentzen/ai-job-search/releases/tag/v1.1.0)

### Agent Reach

- Agent Reach 将自己定位为 capability layer：每个平台维护“首选 + 备选”的有序后端；实际读取仍由 Agent 直接调用上游工具，没有再包一层通用抓取运行时。[README：设计理念](https://github.com/Panniantong/agent-reach#%E8%AE%BE%E8%AE%A1%E7%90%86%E5%BF%B5)、[Channel 基类](https://github.com/Panniantong/agent-reach/blob/main/agent_reach/channels/base.py)
- 后端不能只靠“命令存在”判定可用，应该执行轻量探测；`doctor` 聚合每个 channel 的结果，单一 channel 异常只降级为该 channel 的错误，不拖垮完整报告，并可输出 JSON。[base.py](https://github.com/Panniantong/agent-reach/blob/main/agent_reach/channels/base.py)、[doctor.py](https://github.com/Panniantong/agent-reach/blob/main/agent_reach/doctor.py)、[cli.py](https://github.com/Panniantong/agent-reach/blob/main/agent_reach/cli.py)
- 安装器支持 `--safe` 和 `--dry-run`，可选渠道只有用户点名才安装；Playwright 是 `browser` optional dependency，不是核心依赖。[cli.py](https://github.com/Panniantong/agent-reach/blob/main/agent_reach/cli.py)、[pyproject.toml](https://github.com/Panniantong/agent-reach/blob/main/pyproject.toml)
- LinkedIn 的完整路径依赖外部 MCP；其源码在只发现配置、没有启动服务做连通验证时返回 `warn`，Jina Reader 仅作为基本公开内容路径。因此它不是现成的 JobsDB/CT/LinkedIn 招聘抓取替代品。[linkedin.py](https://github.com/Panniantong/agent-reach/blob/main/agent_reach/channels/linkedin.py)
- Agent Reach 会安装或配置若干外部工具/MCP，部分渠道需要 Cookie 或浏览器登录态；官方文档明确提示封号、凭据和自动修改系统的风险。[README：安全性](https://github.com/Panniantong/agent-reach#%E5%AE%89%E5%85%A8%E6%80%A7)、[安装器源码](https://github.com/Panniantong/agent-reach/blob/main/agent_reach/cli.py)

## 对 Jobsflow 的具体启发

### 1. PDF：保留 LibreOffice，采用 manifest 与内容寻址缓存

v1.1.0 证明的是“PDF 工具链可以声明式扩展”，没有提供 Typst 相比 LibreOffice 更省电、更快或更稳定的基准。Jobsflow 当前又以 LibreOffice 输出和一页 A4 版式为系统规则，因此切换默认引擎会引入版式回归，收益缺乏证据。

建议采用：

- 为现有 DOCX/LibreOffice 路径增加 `renderer manifest`：源类型、命令、页数上限、字体、QA 规则、渲染器版本。
- PDF 缓存键使用 `源文档内容 + 模板版本 + manifest + LibreOffice 版本` 的哈希。命中时复用 PDF 和上次 QA 结果；只有哈希变化才重新导出。
- 编辑阶段只生成 DOCX/预览文本；材料确认后只编译一次最终 PDF。用户主动要求预览或版式变化时才强制重编。
- 保留一个可选 renderer 插槽，为将来的 Typst/Affinity/其他工具做实验，但不改变默认路径。
- 新模板必须先用匿名示例数据试编译和页数检查，个人化文件继续保持 extension-agnostic ignore。

不建议采用：

- 不直接复制上游的“CV 默认 2 页”规则；Jobsflow 的一页规则优先。
- 不允许 manifest 中的任意 shell 字符串无审核执行。应使用允许的可执行文件和参数数组，避免把外部模板内容变成命令注入面。
- 不把 CI 的完整 PDF 工具链装进每次本地 `/materials`；模板级 smoke test 与岗位级最终渲染应分开。

### 2. Playwright/网站接入：建立“轻到重”的路由

当前 Jobsflow 已有“两段评分 + JD cache”，方向正确。下一步不应增加更多浏览器自动化，而应把浏览器变成有预算的最后手段：

1. 门户搜索返回的完整描述或结构化字段；
2. 已命中的 URL/JD 缓存；
3. 门户公开 API、静态 HTML 或轻量 reader；
4. 只有通过 3.3 gate、JD 仍不足且该岗位值得深评时，才进入 Playwright；
5. 触发登录、CAPTCHA、403 或时间预算后降级为 `paste_needed`，不循环硬抓。

建议采用：

- 每个门户声明有序后端，例如 `jobsdb_api/structured → static_http → playwright`，并记录 `active_backend`、失败原因和耗时。
- 增加 `jobsflow doctor --json`：真实轻量探测各门户、LibreOffice、Playwright、Google 凭据和 tracker；单项失败不掩盖其他项。
- 浏览器抓取设每轮总预算和单岗硬超时；拦截 image/font/media 等与 JD 无关的资源。
- 同一轮多个深评岗位复用 browser/context，避免每岗启动一次 Chromium；仍保持账号、portal 和 storage state 的隔离。
- 把 retry/timeout 行为作为公共契约测试。429/5xx 可有限退避；DNS、连接拒绝和确定性 4xx 快速失败；尊重 `Retry-After`。
- 对能升级到批量完整描述的门户，优先推动 `1 request → N full JDs`，这比优化 Playwright 启动参数更有价值。

不建议采用：

- 不用 Jina Reader 或 Agent Reach 替代 Jobsflow 的门户 CLI。它们可作为公开页面的可选 fallback，但没有证明能稳定满足 JobsDB/CT 的动态详情、分页与结构化字段要求。
- 不把“检测到 MCP 配置”当作后端可用；必须做小流量实际探测。
- 不默认复用用户主浏览器 Cookie。需要登录态的后端必须显式 opt-in、最小权限、本地存储，并提示平台条款和封号风险。

### 3. 缓存与节能：把“避免工作”放在“更快做工作”之前

两个上游中，v1.1.0 的批量完整描述是直接减少网络请求的明确证据；Agent Reach 主要提供路由和体检，并没有展示通用的 JD、公司调研或 PDF 结果缓存。因此以下缓存策略是基于其架构启发和 Jobsflow 当前瓶颈作出的设计推论，不是上游声称的性能数字：

| 对象 | 建议缓存键 | 失效条件 | 主要节能点 |
|---|---|---|---|
| JD | canonical URL + 正文哈希 | 内容变化或 TTL 到期 | 避免重复详情/Playwright |
| 公司快查 | 公司规范名 + 官方域名 | 30 天或用户强制刷新 | 多岗位复用性质、主营、行业证据 |
| 两段评分 | profile/version + JD hash + rubric/version | 任一输入变化 | 同岗不重复 LLM/规则评分 |
| PDF | source hash + template/renderer/QA version | 任一输入变化 | 避免重复 LibreOffice 和 PDF QA |
| 门户能力探测 | portal/backend/version | 短 TTL、失败快速重试 | 避免每个 query 重复 doctor |

公司快查应只缓存“有证据的事实”：公司性质、主营业务、产品/客户、行业、岗位所在团队或业务线、来源 URL、抓取时间和置信度。Cover letter 使用具体可核验的兴趣点；无证据时宁可不写。这样既提高差异化，也避免把营销话术或搜索摘要当事实。

### 4. 易用性：把复杂度放到系统内部

Agent Reach 最可借鉴的不是“一句话安装外部工具”，而是用户不需要记后端名称：

- `/setup` 完成后自动运行 doctor，只显示“可用 / 可选 / 需要处理”的三段摘要。
- 默认只启用零配置、低风险路径；Google Sheets、外部 LLM、登录态浏览器、额外 renderer 按需解锁。
- 所有会改环境或写外部系统的动作提供 `--dry-run`；依赖安装另设安全模式，只给修复处方，不自动改系统。
- 失败信息直接给下一步，例如“JobsDB 深 JD 不可用；本轮已用 teaser，投递前可粘贴 JD”，而不是抛堆栈。
- 用户只需使用四个主命令；诸如 backend、cache、browser budget 放进配置和 doctor，不暴露为日常必记参数。
- 对用户在材料流程中确认的新事实做结构化回写，并保留来源/确认时间，减少以后重复访谈，同时禁止未经确认的推断进入事实库。

## 采用决策

| 决策 | 项目 | 理由 |
|---|---|---|
| 立即采用 | 批量完整 JD 优先、N+1 检测 | 最大、最直接的网络与浏览器节省 |
| 立即采用 | portal backend registry + `doctor --json` | 提升稳定性、可诊断性和用户引导 |
| 立即采用 | PDF 内容哈希缓存 + 最终一次渲染 | 不改变现有版式即可减少重复工作 |
| 立即采用 | `--dry-run`、可选能力分级 | 兼顾简单易用与安全 |
| 分阶段采用 | browser/context 批次复用、资源拦截、总预算 | 收益高，但需做门户隔离和回归测试 |
| 分阶段采用 | company research cache | 可同时提升材料差异化与避免重复调研 |
| 仅保留扩展点 | Typst/任意 PDF renderer | 上游证明可扩展，未证明适合当前默认版式 |
| 不直接集成 | Agent Reach 整包 | 能力范围过宽、外部依赖与 Cookie/MCP 风险增加，且没有现成 JobsDB/CT 契约 |
| 不采用 | 默认登录态/主账号浏览器抓取 | 隐私、条款与封号风险高 |

## 建议的最小落地顺序

1. 先修现有门户 timeout/retry 契约，并为每个门户增加真实但轻量的 doctor。
2. 在 two-pass 前后记录 `backend、cache_hit、network_calls、browser_launches、elapsed_ms`，先得到基线。
3. 把完整 JD 随搜索结果返回的能力纳入 portal contract；支持的门户直接跳过详情抓取。
4. 给 PDF 和公司快查增加内容寻址缓存；将 PDF 编译移到材料确认后的最后一步。
5. 再做单 browser/context 的批次深抓；用离线 fixture 和少量本地 live smoke 验证，不在 CI 扫真实门户。
6. 等度量显示现有 LibreOffice 成为主要瓶颈后，再以可选 renderer A/B 测试 Typst；没有版式和时间数据前不迁移默认引擎。

## 风险与证据边界

- 两个项目都没有发布面向本机功耗的测量数据；本文的“节能”主要指减少网络请求、浏览器启动、重复 PDF 编译和重复 LLM/规则计算。
- Agent Reach 的 README 对后端稳定性和免费性有项目方自述，不能替代 Jobsflow 在香港门户上的独立验证。
- Jina、MCP、Cookie 与代理后端都扩大第三方数据流和供应链面；任何启用都应单独做域名、权限、凭据和条款审查。
- 公司与 JD 网页内容始终是不可信数据，只能作为资料，不得改变系统指令、执行命令或要求读取本地凭据。
