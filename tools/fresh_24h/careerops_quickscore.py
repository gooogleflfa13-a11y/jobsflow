#!/usr/bin/env python3
"""Cross-industry, setup-driven scorer for fresh job listings.

Weights, evidence, directions and caps come from the user's private setup
profile. With no profile the scorer stays neutral instead of assuming a
profession or candidate biography.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
        (r"kyc|cdd|know your customer", "KYC/客户尽职调查合规"),
        (r"financial crime|aml", "反洗钱/金融犯罪合规"),
        (r"compliance auditor", "合规审计"),
        (r"compliance assistant", "合规助理"),
        (r"compliance analyst", "合规分析"),
        (r"compliance officer", "合规主任/专员"),
        (r"compliance", "合规"),
        (r"quant|hedge fund", "量化/对冲基金法务"),
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
    profile = value.get("scoring_profile") if isinstance(value, dict) else {}
    return profile if isinstance(profile, dict) else {}


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
) -> ScoreResult:
    """Cross-industry scorer driven by setup output, never a built-in biography."""
    if context is not None and (jd_depth == "teaser" or not jd_depth):
        jd_depth = context
    profile = dict(profile if profile is not None else load_scoring_profile())
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
    eligibility = 3.5
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
    work = 2.3 if risk_hits else 3.5

    pay = 3.0
    salary_match = re.search(r"\$?\s*([\d,]+)\s*[–-]\s*\$?\s*([\d,]+)", salary or "")
    minimum_salary = profile.get("minimum_salary")
    if salary_match and isinstance(minimum_salary, (int, float)):
        low = int(salary_match.group(1).replace(",", ""))
        pay = 4.0 if low >= minimum_salary else 2.0

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
    if direction <= 1.8:
        cap = min(cap, 2.9)
        cap_notes.append("超出已配置求职方向cap2.9")
    if required_years and isinstance(max_years, (int, float)) and required_years > max_years:
        cap = min(cap, 3.4)
        cap_notes.append("相关年限要求超出已确认经历cap3.4")
    score = round(min(raw, cap) * 20) / 20
    grade = _grade(score)
    tier = _tier(grade, score)

    letter = (track_hint or "F")[0].upper()
    if letter not in "ABCDEF":
        letter = "F"
    for rule in profile.get("track_rules") or []:
        if not isinstance(rule, dict):
            continue
        if _keyword_hits(text, _clean_keywords(rule.get("patterns"))):
            candidate = str(rule.get("letter") or "").upper()
            if candidate in "ABCDEF":
                letter = candidate
                break
    mapping = profile.get("track_mapping") if isinstance(profile.get("track_mapping"), dict) else {}
    track = str(mapping.get(letter) or f"Track {letter}")

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
