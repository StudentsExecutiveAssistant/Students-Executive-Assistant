"""Формування рядків відповідальних осіб та кешоване збереження останніх вибраних."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app import config
from app.core.dates import join_uk

INST_ROLES = ["Голова", "Заступник", "Заступниця", "Секретар", "Член"]

_cache_path: str | None = None
_cache_mtime: float | None = None
_cache_data: dict[str, Any] = {}


def _load_last() -> dict[str, Any]:
	global _cache_path, _cache_mtime, _cache_data
	path = config.LAST_USED_FILE
	try:
		mtime = os.path.getmtime(path)
		if _cache_path == path and _cache_mtime == mtime:
			return _cache_data
		with open(path, encoding="utf-8") as f:
			data: dict[str, Any] = json.load(f)
		_cache_path, _cache_mtime, _cache_data = path, mtime, data
		return data
	except (OSError, ValueError):
		return {}


def last_for(uid: int) -> tuple[str, int] | None:
	v = _load_last().get(str(uid))
	if not v:
		return None
	return (v, 2) if isinstance(v, str) else (v["t"], v.get("n", 2))


def save_last(uid: int, text: str, n: int) -> None:
	global _cache_path, _cache_mtime, _cache_data
	path = config.LAST_USED_FILE
	data = dict(_load_last())
	data[str(uid)] = {"t": text, "n": n}
	os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False)
	try:
		_cache_path, _cache_mtime, _cache_data = path, os.path.getmtime(path), data
	except OSError:
		_cache_path, _cache_mtime, _cache_data = None, None, {}


def categories() -> list[str]:
	return list(config.RESPONSIBLES.keys())


def join_parts(parts: list[list[Any]]) -> str:
	return join_uk([p[0].strip().rstrip(".,") for p in parts if p[0].strip()])


def _as_text(parts_or_text: list[list[Any]] | str) -> str:
	return parts_or_text if isinstance(parts_or_text, str) else join_parts(parts_or_text)


def role_parts(role: dict[str, Any], names: list[str]) -> list[list[Any]]:
	if len(names) == 1:
		return [[f"{role['one']} – {names[0]}", 1]]
	if role.get("many"):
		return [[f"{role['many']} – {', '.join(names)}", len(names)]]
	return [[f"{role['one']} – {n}", 1] for n in names]


def institute_parts(code: str, people: list[tuple[str, ...]]) -> list[list[Any]]:
	"""Групує людей інституту в порядку: Голова -> Заступник -> Секретар -> члени -> інші посади."""
	unit = f"{config.INSTITUTE_UNIT} {code}"
	std = ("Голова", "Заступник", "Секретар", "Член")
	extra_roles = list(dict.fromkeys(p[1] for p in people if p[1] not in std))
	out: list[list[Any]] = []
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
			base = (
				("Заступниця" if allf else "Заступник")
				if n == 1
				else ("Заступниці" if allf else "Заступники")
			)
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


def has_person(parts: list[list[Any]], name: str) -> bool:
	return has_person_in_text(join_parts(parts), name)


def role_added_count(parts_or_text: list[list[Any]] | str, role: dict[str, Any]) -> int:
	txt = _as_text(parts_or_text)
	return sum(1 for p in role["people"] if has_person_in_text(txt, p))


def cat_added_count(parts_or_text: list[list[Any]] | str, cat: str) -> int:
	txt = _as_text(parts_or_text)
	names = {p for r in config.RESPONSIBLES[cat] for p in r["people"]}
	return sum(1 for p in names if has_person_in_text(txt, p))


def inst_added_status(
	parts_or_text: list[list[Any]] | str, code: str
) -> tuple[int, bool]:
	txt = _as_text(parts_or_text)
	cnt = sum(
		1 for p in config.INSTITUTE_PEOPLE.get(code, []) if has_person_in_text(txt, p[0])
	)
	has_any = cnt > 0 or f"{config.INSTITUTE_UNIT} {code}" in txt
	return cnt, has_any
