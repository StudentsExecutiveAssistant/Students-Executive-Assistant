"""Налаштування середовища, керування адмінами та завантаження довідників із JSON-файлів у data/."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

LAST_USED_FILE = os.getenv("LAST_USED_FILE", str(DATA_DIR / "last_used.json"))
ADMINS_FILE = os.getenv("ADMINS_FILE", str(DATA_DIR / "admins.json"))


def _load_admins() -> set[int]:
	try:
		with open(ADMINS_FILE, encoding="utf-8") as f:
			raw = json.load(f)
		items = raw.get("admins", raw) if isinstance(raw, dict) else raw
		return {int(x) for x in items if str(x).lstrip("-").isdigit()}
	except (OSError, ValueError, TypeError):
		return set()


def _save_admins(ids: set[int]) -> None:
	os.makedirs(os.path.dirname(ADMINS_FILE) or ".", exist_ok=True)
	with open(ADMINS_FILE, "w", encoding="utf-8") as f:
		json.dump({"admins": sorted(ids)}, f, ensure_ascii=False, indent=2)


def all_admin_ids() -> set[int]:
	return _load_admins()


def add_admin_id(uid: int) -> None:
	admins = _load_admins()
	admins.add(uid)
	_save_admins(admins)


def remove_admin_id(uid: int) -> bool:
	admins = _load_admins()
	if uid not in admins:
		return False
	admins.remove(uid)
	_save_admins(admins)
	return True


def is_admin(uid: int | None) -> bool:
	return uid is not None and uid in all_admin_ids()


def _read_json(filename: str) -> dict[str, Any]:
	path = DATA_DIR / filename
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def _load_officials() -> tuple[
	list[str], dict[str, tuple[list[str], str]], dict[str, tuple[str, list[str]]]
]:
	raw = _read_json("officials.json")
	university: list[str] = list(raw.get("university", []))
	signers: dict[str, tuple[list[str], str]] = {
		k: (list(v["lines"]), str(v["name"]))
		if isinstance(v, dict)
		else (list(v[0]), str(v[1]))
		for k, v in raw.get("signers", {}).items()
	}
	addressees: dict[str, tuple[str, list[str]]] = {}
	for k, v in raw.get("addressees", {}).items():
		if isinstance(v, dict):
			title = list(v["title"])
			name = str(v["name"])
			label_prefix = str(v.get("label") or " ".join(title))
			addressees[k] = (f"{label_prefix} {name}", [*title, *university, name])
		else:
			addressees[k] = (str(v[0]), list(v[1]))
	return university, signers, addressees


def _load_responsibles() -> tuple[str, dict[str, list[dict[str, Any]]]]:
	raw = _read_json("responsibles.json")
	unit = str(raw.get("unit", ""))
	categories: dict[str, list[dict[str, Any]]] = {}
	for cat, roles in raw.get("categories", {}).items():
		parsed_roles: list[dict[str, Any]] = []
		for r in roles:
			entry: dict[str, Any] = {
				"one": str(r["one"]).format(unit=unit),
				"people": list(dict.fromkeys(str(p) for p in r.get("people", []))),
			}
			if r.get("many"):
				entry["many"] = str(r["many"]).format(unit=unit)
			parsed_roles.append(entry)
		categories[cat] = parsed_roles
	return unit, categories


def _load_institutes() -> tuple[
	str,
	set[str],
	dict[str, tuple[str, str]],
	dict[str, str],
	dict[str, list[tuple[str, ...]]],
]:
	raw = _read_json("institutes.json")
	unit = str(raw.get("unit", ""))
	legacy = {str(x) for x in raw.get("legacy_codes", [])}
	institutes: dict[str, tuple[str, str]] = {}
	inst_titles: dict[str, str] = {}
	inst_people: dict[str, list[tuple[str, ...]]] = {}
	for code, info in raw.get("institutes", {}).items():
		institutes[code] = (str(info["name"]), str(info["director"]))
		inst_titles[code] = str(info.get("director_title") or "Директору")
		people_tuples = [tuple(str(x) for x in p) for p in info.get("people", [])]
		inst_people[code] = list(dict.fromkeys(people_tuples))
	return unit, legacy, institutes, inst_titles, inst_people


def _load_places() -> dict[str, list[str]]:
	raw = _read_json("places.json")
	return {
		k: list(dict.fromkeys(str(x) for x in v))
		for k, v in raw.items()
		if isinstance(v, list)
	}


UNIVERSITY, SIGNERS, ADDRESSEES = _load_officials()
ORG_UNIT, RESPONSIBLES = _load_responsibles()
INSTITUTE_UNIT, LEGACY_INSTITUTES, INSTITUTES, INSTITUTE_TITLES, INSTITUTE_PEOPLE = (
	_load_institutes()
)

_PLACES = _load_places()
ROOMS: list[str] = _PLACES.get("rooms", [])
SPORT: list[str] = _PLACES.get("sport", [])
PROSVITA: list[str] = _PLACES.get("prosvita", [])
BUILDINGS: list[str] = _PLACES.get("buildings", [])
EQUIP_ITEMS: list[str] = _PLACES.get("equip_items", [])
EQUIP_PLACES: list[str] = _PLACES.get("equip_places", [])
PLACE_WHERE: list[str] = _PLACES.get("place_where", [])
WORKROOMS: list[str] = _PLACES.get("workrooms", [])
