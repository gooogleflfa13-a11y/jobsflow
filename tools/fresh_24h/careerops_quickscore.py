#!/usr/bin/env python3
"""Cross-industry, setup-driven scorer for fresh job listings.

Weights, evidence, directions and caps come from the user's private setup
profile. With no profile the scorer stays neutral instead of assuming a
profession or candidate biography.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.profile_recovery import repair_scoring_profile


@dataclass
class ScoreResult:
    score: float
    grade: str
    reason: str
    tier: str  # 核心/一级/二级/剔除
    match_points: int  # 匹配分 0-99
    resume_ver: str
    resume_note: str
    track: str
    language_requirement: str
    domain_background: str
    qualification_requirement: str
    experience_requirement: str
    match_key: str
    gaps: str
    work_time_risk: str
    map_reason: str
    confidence: str
    brief: str = ""  # 中文简述
    cap_notes: str = ""  # caps triggered, semicolon-joined
    semantic_note: str = ""  # LLM semantic-resume-match note / fallback flag


_PROFILE_NOTICES: set[str] = set()


def _zh_role_label(title: str) -> str:
    """Map common cross-industry titles to a short Chinese role label."""
    tl = title.lower()
    rules = [
        (r"backend|platform engineer|api engineer", "后端/平台工程"),
        (r"frontend|front-end|web developer", "前端开发"),
        (r"full.?stack", "全栈开发"),
        (r"devops|site reliability|\bsre\b", "DevOps/SRE"),
        (r"data engineer|data scientist|machine learning|\bml engineer", "数据/机器学习"),
        (r"product manager|product owner", "产品管理"),
        (r"financial analyst|\bfp&a\b", "财务分析"),
        (r"marketing|growth|brand|content", "市场/增长"),
        (r"operations?|operational", "运营/流程"),
        (r"project manager|program manager|programme manager", "项目/项目群管理"),
        (r"sales|account executive|business development", "销售/业务拓展"),
        (r"human resources|\bhr\b|recruiter|talent", "人力资源/招聘"),
        (r"customer success|customer support|service delivery", "客户成功/服务交付"),
        (r"accountant|accounting|finance manager", "会计/财务"),
        (r"designer|ux|ui", "设计/用户体验"),
        (r"kyc|cdd|know your customer", "KYC/客户尽职调查合规"),
        (r"financial crime|aml", "反洗钱/金融犯罪合规"),
        (r"compliance auditor", "合规审计"),
        (r"compliance assistant", "合规助理"),
        (r"compliance analyst", "合规分析"),
        (r"compliance officer", "合规主任/专员"),
        (r"compliance", "合规"),
        (r"quant|hedge fund", "量化/对冲基金"),
        (r"legal counsel|counsel", "法律顾问/Counsel"),
        (r"senior lawyer|lawyer", "律师"),
        (r"paralegal|legal executive", "律师助理/法律行政"),
        (r"litigation clerk|law clerk", "诉讼文员/书记"),
        (r"legal secretary", "法律秘书"),
        (r"section head.*legal|head of legal", "法务主管"),
        (r"vice president|vp\b", "副总裁级法务"),
        (r"research assistant", "研究助理"),
        (r"risk management", "风险管理"),
    ]
    for pat, lab in rules:
        if re.search(pat, tl):
            return lab
    return "目标岗位"


def _zh_brief(*, title: str, company: str, teaser: str, salary: str, source: str) -> str:
    """Produce a neutral summary without assuming the candidate's industry."""
    role = _zh_role_label(title)
    co = (company or "—").strip() or "—"
    parts = [f"{co}招聘「{title.strip()}」（{role}）。"]

    bits = []
    tl = f"{title} {teaser}".lower()
    if re.search(r"fintech|unicorn|digital asset|crypto|web3|gate|redot", tl):
        bits.append("偏金融科技/数字资产环境")
    if re.search(r"bank|private bank|equities|markets|investment banking", tl):
        bits.append("银行/金融市场背景")
    if re.search(r"law firm|solicitor|deacons|gallant|cooley|maples", tl):
        bits.append("律师事务所/法律专业服务")
    if re.search(r"litigation|dispute|insolvency|civil litigation", tl):
        bits.append("侧重诉讼/争议或清盘相关经验")
    if re.search(r"kyc|cdd|due diligence|pep", tl):
        bits.append("职责含客户尽调/高风险客户审查")
    if re.search(r"contract|1 year|3 month|temporary|part-time", tl):
        bits.append("合同制/短期或兼职倾向")
    if re.search(r"junior|assistant|analyst|entry", title.lower()):
        bits.append("职级偏初级或分析支持")
    if re.search(r"senior|vice president|\bvp\b|section head|manager|director", title.lower()):
        bits.append("职级偏高（资深/管理）")
    if re.search(r"recruit|michael page|hays|edge partnership|pinesearch|efinancial", co.lower()):
        bits.append("经猎头/招聘平台发布，终端雇主可能未完全披露")
    if re.search(r"software|engineer|developer|data|cloud|platform", tl):
        bits.append("技术/数字化相关")
    if re.search(r"marketing|brand|growth|content|communications", tl):
        bits.append("市场/品牌相关")

    sal = (salary or "").strip()
    if sal and sal not in {"—", "-", "N/A"}:
        bits.append(f"薪资标注：{sal}")

    if bits:
        parts.append("要点：" + "；".join(bits) + "。")
    else:
        # fallback: compress teaser keywords if any Chinese already present
        teaser_s = re.sub(r"\s+", " ", (teaser or "").strip())
        if teaser_s and re.search(r"[\u4e00-\u9fff]", teaser_s):
            parts.append(teaser_s[:180])
        else:
            parts.append(
                f"信息来源：{source or '门户'}标题级摘要；详情需打开完整JD核对职责与硬性要求。"
            )

    parts.append("（24小时扫描快评，非完整JD译文。）")
    return "".join(parts)[:420]


def _is_deep_depth(jd_depth: str) -> bool:
    """True when scorer was given fuller JD context (not teaser-only)."""
    d = (jd_depth or "teaser").strip().lower()
    return d in {"deep", "full", "jd", "fuller", "detail"}


def _zh_reason(
    *,
    company: str,
    title: str,
    dims: dict,
    raw: float,
    score: float,
    grade: str,
    cap_notes: list[str],
    role_label: str,
    jd_depth: str = "teaser",
) -> str:
    """Full Chinese CareerOps 理由."""
    co = company or "—"
    dim_zh = (
        f"六维：简历匹配{dims['resume']:.1f}、资格可行{dims['eligibility']:.1f}、"
        f"方向{dims['direction']:.1f}、行业{dims['industry']:.1f}、"
        f"工时模式{dims['work']:.1f}、薪资发展{dims['pay']:.1f}"
    )
    if cap_notes:
        score_zh = f"加权{raw:.2f}，触发上限后{score:.2f}（{'；'.join(cap_notes)}）"
    else:
        score_zh = f"加权得分{score:.2f}"

    if grade in {"A", "B"}:
        advice = "高度匹配，建议优先深入看JD并准备材料"
    elif grade == "C":
        advice = "中上匹配，值得纳入认真评估清单"
    elif grade == "D":
        advice = "中等匹配，可选投递，投前核实牌照/职级/语言"
    elif grade == "E":
        advice = "中下匹配，低优先级，仅在供给稀缺时考虑"
    else:
        advice = "匹配偏弱或不建议投入，除非另有渠道优势"

    if _is_deep_depth(jd_depth):
        disclaimer = (
            "说明：基于更完整JD/全文的深评，置信度相对更高；仍建议点开链接核对硬性门槛。"
        )
    else:
        disclaimer = "说明：基于职位名与摘要的快评，完整JD可能调整分数。"

    return (
        f"{co}｜岗位类型：{role_label}。"
        f"{dim_zh}。{score_zh}，等级{grade}。{advice}。"
        f"{disclaimer}"
    )[:500]


def _grade(score: float) -> str:
    if score >= 4.5:
        return "A"
    if score >= 4.0:
        return "B"
    if score >= 3.5:
        return "C"
    if score >= 3.0:
        return "D"
    if score >= 2.5:
        return "E"
    return "F"


def _tier(grade: str, score: float) -> str:
    if grade in {"A", "B", "C"}:
        return "核心"
    if grade == "D" and score >= 3.3:
        return "一级"
    if grade in {"D", "E"}:
        return "二级"
    return "剔除"


def _clamp(x: float, lo: float = 1.0, hi: float = 5.0) -> float:
    return max(lo, min(hi, x))


def _clean_keywords(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip().casefold() for item in value if str(item).strip()]


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lowered = text.casefold()
    hits = []
    for keyword in keywords:
        if re.search(r"[\u4e00-\u9fff]", keyword):
            matched = keyword in lowered
        else:
            matched = bool(re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", lowered))
        if matched:
            hits.append(keyword)
    return hits


def load_scoring_profile(repo: Path | None = None) -> dict[str, Any]:
    """Load setup-derived scoring context from the gitignored user workspace."""
    configured_root = os.environ.get("JOBSEARCH_ROOT")
    if configured_root:
        jobsearch_root = Path(configured_root).expanduser()
    elif repo is not None:
        jobsearch_root = Path(repo) / "JobSearch_2026"
    else:
        jobsearch_root = Path(__file__).resolve().parents[2] / "JobSearch_2026"
    path = jobsearch_root / "00_Profile" / "queries.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    profile, health, changed = repair_scoring_profile(jobsearch_root, persist=True)
    notice_key = str(path.resolve())
    if changed and notice_key not in _PROFILE_NOTICES:
        print(
            "INFO: scoring profile recovered missing evidence/industry keywords "
            "from private resume evidence and existing query intent.",
            file=sys.stderr,
        )
        _PROFILE_NOTICES.add(notice_key)
    if health.get("status") != "ready" and notice_key not in _PROFILE_NOTICES:
        print(
            "WARNING: scoring profile is incomplete; scores are capped until "
            "you run /setup and confirm target roles/industry.",
            file=sys.stderr,
        )
        _PROFILE_NOTICES.add(notice_key)
    profile["_profile_health"] = health
    return profile


def _semantic_resume_match(
    *,
    title: str,
    company: str,
    jd_text: str,
    letter: str,
    repo: Path | None = None,
) -> dict[str, Any] | None:
    """Agent-in-the-loop semantic resume-match (deep-JD pass only).

    Does NOT call an external LLM API. Instead it writes a request file to
    <tracker>/semantic_matches/pending/<key>.json containing the fixed lane
    capability profile + the JD. The agent currently executing the task (the
    same model doing the job search work) reads these pending files, applies its
    own semantic understanding, and writes back resume_match (1-5) + note.

    Returns:
      - {"resume": score, "note": ...} when an already-completed verdict file
        exists for this job (re-scoring after agent filled it in).
      - None otherwise (caller falls back to keyword-hit score; the pending
        request has been created for the agent to fill in).
    """
    jobsearch_root = _jobsearch_root(repo)
    base_path = jobsearch_root / "00_Profile" / "bases_runtime"
    cap = {}
    try:
        cap = json.loads((base_path / f"{letter}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    factcheck = cap.get("factcheck") if isinstance(cap.get("factcheck"), dict) else {}
    if not cap or factcheck.get("status") not in {"passed", "capability_profile"}:
        # Semantic matching must never create a high-confidence judgement from
        # an unverified or missing base. The normal keyword score remains the
        # explicit fallback.
        return None

    facts = cap.get("facts_anchor") or cap.get("bullets") or []
    capability_upper = cap.get("capability_upper") or []
    forbidden = cap.get("forbidden_claims") or []
    semantic_profile = cap.get("semantic_profile") if isinstance(cap.get("semantic_profile"), dict) else {}
    level = str(semantic_profile.get("upper_bound_level") or "medium").casefold()
    if level not in {"low", "medium", "high"}:
        level = "medium"
    upper_cap = float(semantic_profile.get("upper_only_score_cap") or {"low": 3.5, "medium": 4.0, "high": 4.5}[level])
    transfer_cap = float(semantic_profile.get("transfer_score_cap") or {"low": 4.0, "medium": 4.5, "high": 5.0}[level])

    def profile_lines(value: Any) -> list[str]:
        lines = []
        for item in value if isinstance(value, list) else []:
            if isinstance(item, dict):
                text = str(item.get("capability") or item.get("text") or "").strip()
                if text:
                    lines.append(text)
            elif str(item).strip():
                lines.append(str(item).strip())
        return lines

    facts_anchor = profile_lines(facts)[:12]
    upper_lines = profile_lines(capability_upper)[:16]
    profile_text = "\n".join(
        [
            f"求职意向画像（{letter}）: {cap.get('label') or letter}",
            f"事实基线（真实经历）:",
        ]
        + [f"  - {b}" for b in facts_anchor[:8]]
        + [
            "能力上沿（仅可迁移潜力，不是已拥有的实操经历）:",
            *[f"  - {b}" for b in upper_lines[:10]],
        ]
        + [
            f"画像上沿幅度：{level}；能力上沿单独支撑的简历匹配最高 {upper_cap:.1f}；可迁移判断最高 {transfer_cap:.1f}",
        ]
        + [f"禁止声称: {'；'.join(forbidden)}" if forbidden else "禁止声称: 无"]
    )

    key = _semantic_task_key(title, company)
    tracker = jobsearch_root / "02_Tracker"
    done_dir = tracker / "semantic_matches" / "done"
    pending_dir = tracker / "semantic_matches" / "pending"

    # If an agent already filled in a verdict, use it.
    done_file = done_dir / f"{key}.json"
    if done_file.exists():
        try:
            verdict = json.loads(done_file.read_text(encoding="utf-8"))
            score = float(verdict.get("resume_match"))
            basis = str(verdict.get("basis") or "upper_only").casefold()
            score = _semantic_score_cap(cap, score, basis)
            note = str(verdict.get("note") or "")
            return {
                "resume": score,
                "note": f"语义简历匹配({letter})[{basis}]：{note}",
            }
        except (OSError, ValueError, TypeError):
            pass

    # Otherwise emit a pending request for the executing agent to fill in.
    try:
        pending_dir.mkdir(parents=True, exist_ok=True)
        pending = {
            "task": "semantic_resume_match",
            "key": key,
            "title": title,
            "company": company,
            "letter": letter,
            "lane_label": cap.get("label") or letter,
            "profile": profile_text,
            "semantic_profile": {
                "upper_bound_level": level,
                "upper_only_score_cap": upper_cap,
                "transfer_score_cap": transfer_cap,
            },
            "jd_snippet": jd_text[:6000],
            "instruction": (
                "用你的语义理解，判断上方「求职意向画像」对 JD 核心职责的支持度。"
                "先把依据标成 direct（事实基线直接支持）、transferable（相邻能力可迁移）、"
                "upper_only（只来自能力上沿）或 none。能力上沿不得当作已拥有实操经验；禁止夸大。"
                "写入 resume_match(1.0-5.0 一位小数)、basis 和 note(一句话中文结论)。"
            ),
            "status": "pending",
        }
        pending_file = pending_dir / f"{key}.json"
        if not pending_file.exists():
            pending_file.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return None


def _semantic_task_key(title: str, company: str) -> str:
    raw = f"{title}|{company}".strip().casefold()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _semantic_lane_classify(
    *,
    title: str,
    company: str,
    jd_text: str,
    profile: dict[str, Any],
    repo: Path | None = None,
) -> str | None:
    """Agent-in-the-loop lane classification (deep-JD pass only).

    Writes a `lane_classify` pending request containing the JD + all defined
    lane labels. The executing agent decides which lane (A-G) the job's nature
    belongs to and writes back a verdict. Returns the agent's chosen letter when
    a verdict exists, else None (caller falls back to rule-based lane).
    """
    track_mapping = profile.get("track_mapping") if isinstance(profile.get("track_mapping"), dict) else {}
    lane_labels = {k: v for k, v in track_mapping.items() if k in "ABCDEFG"}
    if not lane_labels:
        return None
    jobsearch_root = _jobsearch_root(repo)
    tracker = jobsearch_root / "02_Tracker"
    done_dir = tracker / "semantic_matches" / "done"
    pending_dir = tracker / "semantic_matches" / "pending"
    key = "lane_" + _semantic_task_key(title, company)

    done_file = done_dir / f"{key}.json"
    if done_file.exists():
        try:
            verdict = json.loads(done_file.read_text(encoding="utf-8"))
            letter = str(verdict.get("letter") or "").strip().upper()
            if letter in "ABCDEFG":
                return letter
        except (OSError, ValueError):
            pass

    try:
        pending_dir.mkdir(parents=True, exist_ok=True)
        labels_txt = "\n".join(f"  {k}: {v}" for k, v in lane_labels.items())
        pending = {
            "task": "lane_classify",
            "key": key,
            "title": title,
            "company": company,
            "lane_labels": lane_labels,
            "jd_snippet": jd_text[:6000],
            "instruction": (
                "判断上方 JD 的职位本质属于哪个求职画像类别。可选类别：\n"
                + labels_txt
                + "\n只输出最匹配的一个字母（A-G）。若职位本质偏向创新/科技/加密/数字资产业务则选 G；"
                "偏向合规/AML/风险则选 C；以此类推。写入 letter(单个字母) 和 note(一句话中文理由)。"
            ),
            "status": "pending",
        }
        pending_file = pending_dir / f"{key}.json"
        if not pending_file.exists():
            pending_file.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return None


def _jobsearch_root(repo: Path | None = None) -> Path:
    configured = os.environ.get("JOBSEARCH_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if repo is not None:
        root = Path(repo).expanduser().resolve()
        return root if root.name == "JobSearch_2026" else root / "JobSearch_2026"
    return Path(__file__).resolve().parents[2] / "JobSearch_2026"


def _semantic_score_cap(cap: dict[str, Any], score: float, basis: str) -> float:
    """Apply a deterministic upper-bound guard to an agent verdict."""
    semantic = cap.get("semantic_profile") if isinstance(cap.get("semantic_profile"), dict) else {}
    level = str(semantic.get("upper_bound_level") or "medium").casefold()
    caps = {
        "low": {"direct": 5.0, "transferable": 4.0, "upper_only": 3.5, "none": 2.5},
        "medium": {"direct": 5.0, "transferable": 4.5, "upper_only": 4.0, "none": 2.5},
        "high": {"direct": 5.0, "transferable": 5.0, "upper_only": 4.5, "none": 2.5},
    }
    cap_value = caps.get(level, caps["medium"]).get(basis, caps["medium"]["upper_only"])
    return max(1.0, min(cap_value, round(float(score), 1)))


def score_job(
    *,
    title: str,
    company: str,
    teaser: str = "",
    source: str = "",
    salary: str = "",
    track_hint: str = "F",
    soft_flags: str = "",
    jd_depth: str = "teaser",
    context: str | None = None,
    profile: dict[str, Any] | None = None,
    repo: Path | None = None,
) -> ScoreResult:
    """Cross-industry scorer driven by setup output, never a built-in biography."""
    if context is not None and (jd_depth == "teaser" or not jd_depth):
        jd_depth = context
    profile = dict(profile if profile is not None else load_scoring_profile(repo))
    text = f"{title} {teaser} {company}"

    core = _clean_keywords(profile.get("core_keywords"))
    adjacent = _clean_keywords(profile.get("adjacent_keywords"))
    evidence = _clean_keywords(profile.get("evidence_keywords"))
    industries = _clean_keywords(profile.get("preferred_industry_keywords"))
    core_hits = _keyword_hits(text, core)
    adjacent_hits = _keyword_hits(text, adjacent)
    evidence_hits = _keyword_hits(text, evidence)
    industry_hits = _keyword_hits(text, industries)

    direction = (
        min(5.0, 4.0 + 0.15 * len(core_hits))
        if core_hits
        else min(4.0, 3.1 + 0.15 * len(adjacent_hits))
        if adjacent_hits
        else 1.8
        if core
        else 3.0
    )
    resume = (
        min(5.0, 2.2 + 0.35 * len(evidence_hits))
        if evidence_hits
        else 1.8
        if evidence
        else 3.0
    )

    language_match = re.search(
        r"\b(cantonese|mandarin|english|french|german|spanish|japanese|korean)\b|"
        r"(粤语|普通话|英语|英文|法语|德语|西班牙语|日语|韩语)",
        text,
        re.I,
    )
    qualification_match = re.search(
        r"\b(certification|certificate|licen[cs]e|qualified|admitted|degree)\b|"
        r"(资格证|牌照|执业资格|学位要求|认证)",
        text,
        re.I,
    )
    years_match = re.search(
        r"\b(\d+)\+?\s*(?:years?|pqe)\b|(\d+)\s*年(?:相关)?经验",
        text,
        re.I,
    )
    neutral_scores = profile.get("neutral_scores") if isinstance(profile.get("neutral_scores"), dict) else {}
    eligibility = float(neutral_scores.get("eligibility", 3.5))
    max_years = profile.get("max_relevant_years")
    required_years = 0
    if years_match:
        required_years = int(years_match.group(1) or years_match.group(2) or 0)
        if isinstance(max_years, (int, float)):
            eligibility = 4.0 if required_years <= max_years else 2.0
        else:
            eligibility = 3.0
    if qualification_match and not _clean_keywords(profile.get("qualification_keywords")):
        eligibility = min(eligibility, 3.0)

    industry = min(5.0, 3.0 + 0.3 * len(industry_hits)) if industries else 3.0
    risk_hits = _keyword_hits(
        text,
        _clean_keywords(profile.get("schedule_risk_keywords")),
    )
    work = 2.3 if risk_hits else float(neutral_scores.get("work", 3.5))

    pay = float(neutral_scores.get("pay", 3.0))
    salary_match = re.search(r"\$?\s*([\d,]+)\s*[–-]\s*\$?\s*([\d,]+)", salary or "")
    minimum_salary = profile.get("minimum_salary")
    if salary_match and isinstance(minimum_salary, (int, float)):
        low = int(salary_match.group(1).replace(",", ""))
        pay = 4.0 if low >= minimum_salary else 2.0

    # Determine lane (letter) early so semantic resume matching can load the
    # lane-specific capability profile (A-G). Keeps eligibility rules unchanged.
    # On deep-JD pass, the executing agent classifies the lane semantically;
    # rule-based classification is the deterministic fallback.
    rules = [r for r in (profile.get("track_rules") or []) if isinstance(r, dict)]
    rule_letter = (track_hint or "F")[0].upper()
    if rule_letter not in "ABCDEFG":
        rule_letter = "F"
    # Innovation/tech lane (G) takes priority BUT only when the JD is clearly
    # crypto/web3/digital-asset flavoured (strong signals). Generic words like
    # technology/platform/fintech that appear in any modern JD must NOT trigger G,
    # otherwise traditional compliance roles get misclassified into G.
    g_rule = next((r for r in rules if str(r.get("letter") or "").upper() == "G"), None)
    if g_rule:
        g_strong = _clean_keywords(g_rule.get("strong_patterns"))
        if not g_strong or _keyword_hits(text, g_strong):
            rule_letter = "G"
    if rule_letter != "G":
        # Compliance/AML (C) signals (weak: compliance/regulatory/risk, strong:
        # aml/kyc/financial crime/cdd/sanctions) beat commercial (A/B): AML roles
        # also mention due diligence (B) or research (A), so without this
        # precedence bank/fund/investment compliance jobs get misclassified.
        c_rule = next((r for r in rules if str(r.get("letter") or "").upper() == "C"), None)
        c_weak = _clean_keywords(c_rule.get("patterns")) if c_rule else []
        c_strong = _clean_keywords(c_rule.get("strong_patterns")) if c_rule else []
        c_hits = _keyword_hits(text, c_weak) if c_weak else []
        if c_hits and (not c_strong or _keyword_hits(text, c_strong) or c_strong == c_weak):
            rule_letter = "C"
        else:
            for rule in rules:
                if str(rule.get("letter") or "").upper() in ("G", "C"):
                    continue
                if _keyword_hits(text, _clean_keywords(rule.get("patterns"))):
                    candidate = str(rule.get("letter") or "").upper()
                    if candidate in "ABCDEFG":
                        rule_letter = candidate
                        break

    letter = rule_letter
    if _is_deep_depth(jd_depth):
        agent_lane = _semantic_lane_classify(
            title=title,
            company=company,
            jd_text=teaser or "",
            profile=profile,
            repo=repo,
        )
        if agent_lane is not None:
            letter = agent_lane
    mapping = profile.get("track_mapping") if isinstance(profile.get("track_mapping"), dict) else {}
    track = str(mapping.get(letter) or f"Track {letter}")

    # Semantic resume matching: on deep-JD pass, ask the executing agent to judge how well the
    # candidate's capability profile (facts anchor + capability upper) supports the
    # JD's core duties, instead of naive keyword-hit counting. On failure falls
    # back to the keyword-hit score and flags it.
    semantic_note = None
    if _is_deep_depth(jd_depth):
        sem = _semantic_resume_match(
            title=title,
            company=company,
            jd_text=teaser or "",
            letter=letter,
            repo=repo,
        )
        if sem is not None:
            resume = sem["resume"]
            semantic_note = sem.get("note")

    dims = {
        "resume": resume,
        "eligibility": eligibility,
        "direction": direction,
        "industry": industry,
        "work": work,
        "pay": pay,
    }
    defaults = {
        "resume": 0.35,
        "eligibility": 0.20,
        "direction": 0.20,
        "industry": 0.10,
        "work": 0.10,
        "pay": 0.05,
    }
    supplied = profile.get("weights") if isinstance(profile.get("weights"), dict) else {}
    weights = {key: max(0.0, float(supplied.get(key, value))) for key, value in defaults.items()}
    total_weight = sum(weights.values()) or 1.0
    raw = sum(dims[key] * weights[key] for key in weights) / total_weight

    cap = 5.0
    cap_notes: list[str] = []
    profile_health = profile.get("_profile_health")
    if isinstance(profile_health, dict) and profile_health.get("status") != "ready":
        cap = min(cap, 2.9)
        cap_notes.append("评分配置不完整，已阻止中性高分")
    if direction <= 1.8:
        cap = min(cap, 2.9)
        cap_notes.append("超出已配置求职方向cap2.9")
    if required_years and isinstance(max_years, (int, float)) and required_years > max_years:
        cap = min(cap, 3.4)
        cap_notes.append("相关年限要求超出已确认经历cap3.4")
    score = round(min(raw, cap) * 20) / 20
    grade = _grade(score)
    tier = _tier(grade, score)

    keys = []
    gaps = []
    if core_hits:
        keys.append("目标方向匹配：" + "、".join(core_hits[:4]))
    if evidence_hits:
        keys.append("简历证据匹配：" + "、".join(evidence_hits[:4]))
    if core and not core_hits:
        gaps.append("职位未命中已配置核心方向")
    if evidence and not evidence_hits:
        gaps.append("未找到直接简历证据")
    if qualification_match:
        gaps.append("资格要求需逐项核对")
    if language_match:
        gaps.append("语言要求需逐项核对")
    if years_match:
        gaps.append("相关年限需逐项核对")
    if not keys:
        keys.append("配置或职位信息有限，保持中性评分")
    if not gaps:
        gaps.append("—")

    conf = "中" if teaser and len(teaser) > 80 else "低"
    if _is_deep_depth(jd_depth):
        conf = "中高" if conf == "中" else "中"
    reason = _zh_reason(
        company=company or "—",
        title=title,
        dims=dims,
        raw=raw,
        score=score,
        grade=grade,
        cap_notes=cap_notes,
        role_label=_zh_role_label(title),
        jd_depth=jd_depth,
    )
    brief = _zh_brief(
        title=title,
        company=company or "—",
        teaser=teaser,
        salary=salary,
        source=source,
    )
    if semantic_note:
        reason = f"{reason}｜{semantic_note}"
    return ScoreResult(
        score=score,
        grade=grade,
        reason=reason,
        tier=tier,
        match_points=int(min(99, max(5, round(score * 20 + 8)))),
        resume_ver=letter,
        resume_note=track,
        track=track,
        language_requirement=language_match.group(0) if language_match else "未说明",
        domain_background="核心匹配" if core_hits else "相邻匹配" if adjacent_hits else "未匹配/待核对",
        qualification_requirement="JD提及，需核对" if qualification_match else "未说明",
        experience_requirement=years_match.group(0) if years_match else "未说明",
        match_key="；".join(keys),
        gaps="；".join(gaps),
        work_time_risk="高" if risk_hits else "未发现已配置冲突",
        map_reason=f"配置驱动评分→简历方向{letter}（{track}）",
        confidence=conf,
        brief=brief,
        cap_notes="；".join(cap_notes),
        semantic_note=semantic_note or "",
    )


def company_brief(company: str, teaser: str, max_chars: int = 180) -> str:
    name = (company or "—").strip() or "—"
    text = re.sub(r"\s+", " ", teaser or "").strip()
    marker = re.search(
        r"(?:about us|about the company|company overview|who we are|公司简介|关于我们)"
        r"\s*[:：\-]?\s*(.+)",
        text,
        flags=re.IGNORECASE,
    )
    if marker:
        overview = re.split(
            r"\b(?:responsibilities|requirements|qualifications|what you(?:'|’)ll do|"
            r"the role|job duties)\b|(?:岗位职责|职位要求|任职要求)",
            marker.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .;；。")
        if len(overview) >= 20:
            if len(overview) > max_chars:
                overview = overview[:max_chars].rstrip(" ,.;；。") + "…"
            return f"{name}，{overview}"
    return f"{name}；当前职位页未提供明确公司背景，建议结合官网核实。"


SHEET_HEADERS = [
    "岗位编号",
    "行号",
    "本轮新增",  # 是 / 否 — 最新一次刷新写入的行，便于一眼区分
    "批次",  # 如 temp_2026-07-28_1137 或 daily_2026-07-28
    "入表时间",  # HKT 可读时间
    "层级",
    "匹配分",
    "职位",
    "公司",
    "赛道",
    "来源",
    "地点",
    "薪资",
    "链接",
    "简述",
    "语言要求",
    "领域背景",
    "资格要求",
    "经验要求",
    "匹配要点",
    "主要缺口",
    "发布日期",
    "简历版本",
    "版本说明",
    "材料状态",
    "工作时间风险",
    "公司简介",
    "CareerOps分数",
    "CareerOps等级",
    "CareerOps理由",
    "置信度",
]


_SOURCE_ZH = {
    "linkedin": "领英",
    "jobsdb": "JobsDB",
    "ctgoodjobs": "CTgoodjobs",
    "ct": "CTgoodjobs",
}


def build_tracker_row(
    job_id: str,
    row_num: int,
    hit: dict[str, Any],
    sc: ScoreResult,
    *,
    is_new_batch: bool = True,
    batch_id: str = "",
    entered_at: str = "",
) -> list[str]:
    posted = (hit.get("posted_at") or "")[:10]
    src = (hit.get("source") or "").strip().lower()
    src_zh = _SOURCE_ZH.get(src, hit.get("source") or "")
    brief = sc.brief or _zh_brief(
        title=hit.get("title") or "",
        company=hit.get("company") or "—",
        teaser=hit.get("teaser") or "",
        salary=hit.get("salary") or "",
        source=src_zh,
    )
    return [
        job_id,
        str(row_num),
        "是" if is_new_batch else "否",
        batch_id or "",
        entered_at or "",
        sc.tier,
        str(sc.match_points),
        hit.get("title") or "",
        hit.get("company") or "—",
        sc.track,
        src_zh,
        hit.get("location") or "香港",
        hit.get("salary") or "—",
        hit.get("url") or "",
        brief,
        sc.language_requirement,
        sc.domain_background,
        sc.qualification_requirement,
        sc.experience_requirement,
        sc.match_key,
        sc.gaps,
        posted,
        sc.resume_ver,
        sc.resume_note,
        "未做",
        sc.work_time_risk,
        company_brief(hit.get("company") or "—", hit.get("teaser") or ""),
        f"{sc.score:.2f}",
        sc.grade,
        sc.reason,
        sc.confidence,
    ]
