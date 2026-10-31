"""Skill matching against free text, with the exact excerpt that supports each match."""

import re
from dataclasses import dataclass
from functools import lru_cache

from app.seed.skills import SKILLS

SKILL_BY_ID = {s["id"]: s for s in SKILLS}


@dataclass
class SkillMatch:
    skill_id: str
    alias: str
    excerpt: str
    line_index: int


@lru_cache
def _patterns() -> list[tuple[str, str, re.Pattern[str]]]:
    out = []
    for s in SKILLS:
        for a in s["aliases"]:
            out.append((s["id"], a, re.compile(r"(?<![\w.+#-])" + re.escape(a) + r"(?![\w+#])", re.IGNORECASE)))
    # Longer aliases first so "machine learning" wins over shorter overlaps.
    out.sort(key=lambda t: -len(t[1]))
    return out


def split_units(text: str) -> list[str]:
    """Lines and sentences, which become the citable excerpts."""
    units: list[str] = []
    for line in text.splitlines():
        line = line.strip(" \t•-*·▪●")
        if not line:
            continue
        parts = re.split(r"(?<=[.!?;])\s+(?=[A-Z])", line) if len(line) > 220 else [line]
        units.extend(p.strip() for p in parts if p.strip())
    return units


def find_skills(text: str) -> dict[str, list[SkillMatch]]:
    found: dict[str, list[SkillMatch]] = {}
    for i, unit in enumerate(split_units(text)):
        for skill_id, alias, pat in _patterns():
            if pat.search(unit):
                lst = found.setdefault(skill_id, [])
                if not any(m.line_index == i for m in lst):
                    lst.append(SkillMatch(skill_id, alias, unit[:400], i))
    return found


def skill_name(skill_id: str) -> str:
    s = SKILL_BY_ID.get(skill_id)
    return s["name"] if s else skill_id


def prerequisites(skill_id: str) -> list[str]:
    s = SKILL_BY_ID.get(skill_id)
    return list(s["prereqs"]) if s else []


def related(skill_id: str) -> list[str]:
    s = SKILL_BY_ID.get(skill_id)
    return list(s.get("related", [])) if s else []


def normalize_excerpt(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def excerpt_in(excerpt: str, source: str) -> bool:
    """Grounding check: an AI-provided excerpt must literally appear in the source."""
    e = normalize_excerpt(excerpt)
    return bool(e) and e in normalize_excerpt(source)
