"""Формування рядків відповідальних осіб та кешоване збереження останніх вибраних."""
from __future__ import annotations

import json
import os
import re

from app import config
from app.core.dates import join_uk

INST_ROLES = ["Голова", "Заступник", "Заступниця", "Секретар", "Член"]

_CACHE_PATH: str | None = None
_CACHE_MTIME: float | None = None
_CACHE_DATA: dict = {}


def _load_last() -> dict:
    global _CACHE_PATH, _CACHE_MTIME, _CACHE_DATA
    path = config.LAST_USED_FILE
    try:
        mtime = os.path.getmtime(path)
        if _CACHE_PATH == path and _CACHE_MTIME == mtime:
            return _CACHE_DATA
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        _CACHE_PATH, _CACHE_MTIME, _CACHE_DATA = path, mtime, data
        return data
    except (OSError, ValueError):
        return {}


def last_for(uid: int) -> tuple[str, int] | None:
    v = _load_last().get(str(uid))
    if not v:
        return None
    return (v, 2) if isinstance(v, str) else (v["t"], v.get("n", 2))


def save_last(uid: int, text: str, n: int) -> None:
    global _CACHE_PATH, _CACHE_MTIME, _CACHE_DATA
    path = config.LAST_USED_FILE
    data = dict(_load_last())
    data[str(uid)] = {"t": text, "n": n}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    try:
        _CACHE_PATH, _CACHE_MTIME, _CACHE_DATA = path, os.path.getmtime(path), data
    except OSError:
        _CACHE_PATH, _CACHE_MTIME, _CACHE_DATA = None, None, {}


def categories() -> list[str]:
    return list(config.RESPONSIBLES.keys())


def join_parts(parts: list) -> str:
    return join_uk([p[0].strip().rstrip(".,") for p in parts if p[0].strip()])


def _as_text(parts_or_text: list | str) -> str:
    return parts_or_text if isinstance(parts_or_text, str) else join_parts(parts_or_text)


def role_parts(role: dict, names: list[str]) -> list[list]:
    if len(names) == 1:
        return [[f"{role['one']} – {names[0]}", 1]]
    if role.get("many"):
        return [[f"{role['many']} – {', '.join(names)}", len(names)]]
    return [[f"{role['one']} – {n}", 1] for n in names]


def institute_parts(code: str, people: list[tuple]) -> list[list]:
    """Групує людей інституту в порядку: Голова -> Заступник -> Секретар -> члени -> інші посади."""
    unit = f"{config.INSTITUTE_UNIT} {code}"
    std = ("Голова", "Заступник", "Секретар", "Член")
    extra_roles = list(dict.fromkeys(p[1] for p in people if p[1] not in std))
    out = []
    for role in (*std, *extra_roles):
        ps = [p for p in people if p[1] == role]
        if not ps:
            continue
        n = len(ps)
        names = ", ".join(p[0] for p in ps)
        allf = all(len(p) > 2 and p[2] == "ж" for p in ps)
        if role == "Голова":
            label = ("Голова" if n == 1 else "Голови") + f" {unit}"
        elif role == "Заступник":
            base = ("Заступниця" if allf else "Заступник") if n == 1 else ("Заступниці" if allf else "Заступники")
            label = f"{base} Голови {unit}"
        elif role == "Секретар":
            label = ("Секретар" if n == 1 else "Секретарі") + f" {unit}"
        elif role == "Член":
            label = ("член" if n == 1 else "члени") + f" {unit}"
        else:
            label = f"{role} {unit}"
        out.append([f"{label} – {names}", n])
    return out


def has_person_in_text(joined_text: str, name: str) -> bool:
    if not joined_text or name not in joined_text:
        return False
    return bool(re.search(rf"(?<![\w’']){re.escape(name)}(?![\w’'])", joined_text))


def has_person(parts: list, name: str) -> bool:
    return has_person_in_text(join_parts(parts), name)


def role_added_count(parts_or_text: list | str, role: dict) -> int:
    txt = _as_text(parts_or_text)
    return sum(1 for p in role["people"] if has_person_in_text(txt, p))


def cat_added_count(parts_or_text: list | str, cat: str) -> int:
    txt = _as_text(parts_or_text)
    names = {p for r in config.RESPONSIBLES[cat] for p in r["people"]}
    return sum(1 for p in names if has_person_in_text(txt, p))


def inst_added_status(parts_or_text: list | str, code: str) -> tuple[int, bool]:
    txt = _as_text(parts_or_text)
    cnt = sum(1 for p in config.INSTITUTE_PEOPLE.get(code, []) if has_person_in_text(txt, p[0]))
    has_any = cnt > 0 or f"{config.INSTITUTE_UNIT} {code}" in txt
    return cnt, has_any
