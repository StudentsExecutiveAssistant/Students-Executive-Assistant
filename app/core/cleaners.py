"""Очищення, автовиправлення та нормалізація користувацького вводу."""

from __future__ import annotations

import re
from typing import Any

from app import config

CYR = "А-Яа-яІіЇїЄєҐґ"
LAT = "A-Za-z"

PLATE_RE = re.compile(rf"^[{CYR}{LAT}]{{2}}\d{{4}}[{CYR}{LAT}]{{2}}$")
GROUP_RE = re.compile(rf"^[{CYR}{LAT}]{{1,6}}[-‑]\d{{1,3}}$")
_UPPER_GROUP_RE = re.compile(r"^[А-ЯІЇЄҐ]{2,6}$")
_STUDENT_GROUP_SEP_RE = re.compile(rf"\s*,\s*(?=[{CYR}{LAT}]{{1,6}}-\d{{1,3}}$)")

_APOSTROPHE_RE = re.compile(rf"(?<=[{CYR}{LAT}])[ʼ'`´](?=[{CYR}{LAT}])")
_ANY_APOS_RE = re.compile(r"[ʼ']")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r" +([,.;:!?])")
_COMMA_NO_SPACE_RE = re.compile(rf",(?=[{CYR}{LAT}])")
_DUP_PREP_RE = re.compile(
	r"\b(з|із|зі|у|в|і|й|до|на|за|від|про|для|та|або|чи)\s+(\1)\b(?!\.)",
	re.IGNORECASE,
)

_WS_RE = re.compile(r"\s+")
_LIST_BULLET_RE = re.compile(r"^(?:\d+[.)]|[-•–—])\s*")
_NAME_SPLIT_RE = re.compile(r"[,;\n]+")
_NAME_VALID_RE = re.compile(r"^[А-ЯІЇЄҐа-яіїєґ’\- ]+$")
_PLATE_SPLIT_RE = re.compile(r"[,;\n]+|\s+(?:та|і|й|and)\s+")
_AWARD_COL_SPLIT_RE = re.compile(r"[\t;|]+")
_AWARD_TOK_SPLIT_RE = re.compile(r"[\s,]+")
_UID_SPLIT_RE = re.compile(r"[\s,;]+")

_PREFIX_ROUTE_RE = re.compile(
	r"^(?:для\s+поїздки|для|поїздки)(?:[:,;\s]+|\s+[-–—]+\s*|$)(.*)$", re.IGNORECASE
)
_PREFIX_DEPT_RE = re.compile(
	r"^(?:від|од)(?:[:,;\s]+|\s+[-–—]+\s*|$)(.*)$", re.IGNORECASE
)
_PREFIX_PROJ_RE = re.compile(
	r"^(?:в|у)\s+межах(?:[:,;\s]+|\s+[-–—]+\s*|$)(.*)$", re.IGNORECASE
)
_PREFIX_ORDER_RE = re.compile(
	r"^(?:згідно\s+(?:з|із)\s+наказом|наказ(?:ом)?|№)\s*(.*)$", re.IGNORECASE
)
_PREFIX_DORM_WORD_RE = re.compile(
	r"^(?:(?:у|в)\s+)?гуртожит(?:ок|ку)(?:[:,;\s]+|\s+[-–—]+\s*|$)(.*)$", re.IGNORECASE
)
_PREFIX_NUM_SIGN_RE = re.compile(r"^№\s*(.*)$", re.IGNORECASE)
_PREFIX_ZA_RE = re.compile(r"^за(?:[:,;\s]+|\s+[-–—]+\s*|$)(.*)$", re.IGNORECASE)
_SUFFIX_ZA_RE = re.compile(r"(?:\s+за[,.:;\-–—]*)+$", re.IGNORECASE)

_PREFIX_ZVYAZKU_RE = re.compile(
	r"^(?:у|в)\s+зв[’ʼ'`´]?язку(?:\s+(?:з|із|зі)(?![-А-Яа-яІіЇїЄєҐґ]))?(?:[:,;\s]+|\s+[-–—]+\s*|$)(.*)$",
	re.IGNORECASE,
)
_PREFIX_Z_RE = re.compile(
	r"^(?:з|із|зі)(?:[:,;\s]+|\s+[-–—]+\s*|$)(.*)$", re.IGNORECASE
)
_SUFFIX_ZVYAZKU_RE = re.compile(
	r"(?:\s+(?:у|в)\s+зв[’ʼ'`´]?язку(?:\s+(?:з|із|зі))?[,.:;\-–—]*)+$",
	re.IGNORECASE,
)

_DLYA_DLYA_RE = re.compile(r"^для\s+(для\b.*)$", re.IGNORECASE)
_SHCHOB_RE = re.compile(r"^для\s+того,?\s+щоб\b", re.IGNORECASE)
_ANY_SHCHOB_RE = re.compile(r"^(?:для\s+того,?\s+щоб|щоб)\b", re.IGNORECASE)
_METOYU_SHCHOB_RE = re.compile(
	r"^з\s+метою\s+(?:для\s+того,?\s+щоб|щоб)\b", re.IGNORECASE
)
_METOYU_HEAD_RE = re.compile(r"^з\s+метою\s+", re.IGNORECASE)
_METOYU_DLYA_RE = re.compile(r"^з\s+метою\s+для(?:[:,\-–—\s]+)(.*)$", re.IGNORECASE)
_METOYU_PREFIX_RE = re.compile(r"^з\s+метою(?:[:,\-–—\s]+)(.*)$", re.IGNORECASE)
_METOYU_BARE_RE = re.compile(r"^з\s+метою[,.:;\-–—]*$", re.IGNORECASE)
_DLYA_PREFIX_RE = re.compile(r"^для(?:[:,\-–—\s]+)(.*)$", re.IGNORECASE)
_DLYA_BARE_RE = re.compile(r"^для[,.:;\-–—]*$", re.IGNORECASE)
_DLYA_SUFFIX_RE = re.compile(r"(?:\s+для[,.:;\-–—]*)+$", re.IGNORECASE)


def norm_apos(text: str) -> str:
	return _ANY_APOS_RE.sub("’", text)


def is_valid_award_group(grp: str) -> bool:
	return bool(
		GROUP_RE.match(grp)
		or grp.lower().startswith("аспірант")
		or (grp.isupper() and _UPPER_GROUP_RE.fullmatch(grp))
	)


def _add_note(fixes: list[str], label: str) -> None:
	if label not in fixes:
		fixes.append(label)


def sanitize(text: str) -> tuple[str, list[str]]:
	fixes: list[str] = []
	t = text.strip()

	def sub(rx: re.Pattern[str], repl: str, label: str, s: str) -> str:
		new = rx.sub(repl, s)
		if new != s:
			_add_note(fixes, label)
		return new

	t = sub(_APOSTROPHE_RE, "’", "апострофи", t)
	if '"' in t:
		out, opened = [], False
		for ch in t:
			if ch == '"':
				out.append("»" if opened else "«")
				opened = not opened
			else:
				out.append(ch)
		t = "".join(out)
		_add_note(fixes, "лапки")
	t = sub(_MULTI_SPACE_RE, " ", "зайві пробіли", t)
	t = sub(_SPACE_BEFORE_PUNCT_RE, r"\1", "пробіл перед розділовим знаком", t)
	t = sub(_COMMA_NO_SPACE_RE, ", ", "пробіл після коми", t)

	# Не склеюємо ініціал після прийменника на кшталт «зустріч з З. І. Мельником».
	while True:
		dedup = _DUP_PREP_RE.sub(
			lambda m: (
				m.group(0)
				if len(m.group(1)) == 1 and m.group(1).islower() and m.group(2).isupper()
				else m.group(1)
			),
			t,
		)
		if dedup == t:
			break
		_add_note(fixes, "подвоєні прийменники")
		t = dedup
	return t, fixes


def sanitize_lines(items: list[Any], fixes: list[str]) -> list[Any]:
	out: list[Any] = []
	for item in items:
		if isinstance(item, list):
			row: list[str] = []
			for col in item:
				c_clean, fx = sanitize(col)
				row.append(c_clean)
				for f in fx:
					_add_note(fixes, f)
			out.append(row)
		else:
			v_clean, fx = sanitize(item)
			out.append(v_clean)
			for f in fx:
				_add_note(fixes, f)
	return out


def _strip_prefix_loop(
	text: str,
	rules: tuple[tuple[re.Pattern[str], str, str | None], ...],
	empty_error: str,
	suffix_rule: tuple[re.Pattern[str], str] | None = None,
) -> tuple[str, list[str]]:
	val = _WS_RE.sub(" ", text).strip()
	fixes: list[str] = []
	while val:
		matched = False
		for rx, label, strip_chars in rules:
			if m := rx.match(val):
				val = m.group(1).strip(strip_chars) if strip_chars else m.group(1).strip()
				_add_note(fixes, label)
				matched = True
				break
		if not matched:
			break
	if suffix_rule:
		sfx_rx, sfx_label = suffix_rule
		val, n_end = sfx_rx.subn("", val)
		if n_end:
			_add_note(fixes, sfx_label)
		val = val.strip()
	if not val:
		raise ValueError(empty_error)
	return val, fixes


def clean_purpose(text: str, *, mode: str = "dlya") -> tuple[str, list[str]]:
	"""Прибирає зайві «для» / «з метою» на початку або в кінці мети, зберігаючи «для того, щоб …»."""
	val = _WS_RE.sub(" ", text).strip()
	fixes: list[str] = []

	while val:
		if m := _DLYA_DLYA_RE.match(val):
			val = m.group(1).strip()
			_add_note(fixes, "прибрано зайве «для»")
			continue
		if _METOYU_SHCHOB_RE.match(val):
			val = _METOYU_HEAD_RE.sub("", val, count=1).strip()
			_add_note(fixes, "прибрано зайве «з метою»")
			continue
		if mode == "dlya":
			if _SHCHOB_RE.match(val):
				break
			if m := _METOYU_DLYA_RE.match(val):
				rest = m.group(1).strip()
				val = f"з метою {rest}" if rest else "з метою"
				_add_note(fixes, "прибрано зайве «для»")
				continue
		else:
			if _ANY_SHCHOB_RE.match(val):
				break
			if m := _METOYU_PREFIX_RE.match(val):
				val = m.group(1).strip()
				_add_note(fixes, "прибрано зайве «з метою»")
				continue
			if _METOYU_BARE_RE.fullmatch(val):
				val = ""
				_add_note(fixes, "прибрано зайве «з метою»")
				break
		if m := _DLYA_PREFIX_RE.match(val):
			val = m.group(1).strip()
			_add_note(fixes, "прибрано зайве «для»")
			continue
		if _DLYA_BARE_RE.fullmatch(val):
			val = ""
			_add_note(fixes, "прибрано зайве «для»")
			break
		break

	val, n_end = _DLYA_SUFFIX_RE.subn("", val)
	if n_end:
		_add_note(fixes, "прибрано зайве «для»")
	val = val.strip()
	if not val:
		raise ValueError("Вкажіть мету після «для» або пропустіть/введіть без нього")
	return val, fixes


def clean_reason(text: str, *, mode: str = "zvyazku") -> tuple[str, list[str]]:
	if mode == "za":
		return _strip_prefix_loop(
			text,
			((_PREFIX_ZA_RE, "прибрано зайве «за»", None),),
			"Вкажіть причину преміювання без слова «за»",
			suffix_rule=(_SUFFIX_ZA_RE, "прибрано зайве «за»"),
		)
	return _strip_prefix_loop(
		text,
		(
			(_PREFIX_ZVYAZKU_RE, "прибрано зайве «у зв’язку з»", None),
			(_PREFIX_Z_RE, "прибрано зайве «з»", None),
		),
		"Вкажіть причину без слів «у зв’язку з»",
		suffix_rule=(_SUFFIX_ZVYAZKU_RE, "прибрано зайве «у зв’язку з»"),
	)


def clean_route(text: str) -> tuple[str, list[str]]:
	return _strip_prefix_loop(
		text,
		((_PREFIX_ROUTE_RE, "прибрано зайве «для»", None),),
		"Вкажіть маршрут",
	)


def clean_dept(text: str) -> tuple[str, list[str]]:
	return _strip_prefix_loop(
		text,
		((_PREFIX_DEPT_RE, "прибрано зайве «від»", None),),
		"Вкажіть, від кого поїздка",
	)


def clean_project(text: str) -> tuple[str, list[str]]:
	return _strip_prefix_loop(
		text,
		((_PREFIX_PROJ_RE, "прибрано зайве «в межах»", None),),
		"Вкажіть проєкт без слів «в межах» або натисніть «Пропустити»",
	)


def clean_order(text: str) -> tuple[str, list[str]]:
	return _strip_prefix_loop(
		text,
		((_PREFIX_ORDER_RE, "прибрано зайве «№»", " :,-–—"),),
		"Вкажіть номер наказу без «№» або натисніть «Пропустити»",
	)


def clean_dorm(text: str) -> tuple[str, list[str]]:
	return _strip_prefix_loop(
		text,
		(
			(_PREFIX_DORM_WORD_RE, "прибрано зайве «гуртожиток»", None),
			(_PREFIX_NUM_SIGN_RE, "прибрано зайве «№»", None),
		),
		"Вкажіть номер гуртожитку (число)",
	)


def _cap(word: str) -> str:
	return "-".join(p[:1].upper() + p[1:].lower() if p else p for p in word.split("-"))


def parse_names(raw: str) -> tuple[list[str], list[str]]:
	names: list[str] = []
	warns: list[str] = []
	seen: set[str] = set()
	dups: set[str] = set()
	for chunk in _NAME_SPLIT_RE.split(raw):
		chunk = _WS_RE.sub(" ", norm_apos(chunk)).strip()
		if not chunk:
			continue
		if not _NAME_VALID_RE.fullmatch(chunk):
			raise ValueError(
				f"У «{chunk}» є зайві символи (цифри / латиниця / знаки). Пишіть: Прізвище Імʼя"
			)
		name = " ".join(_cap(w) for w in chunk.split(" "))
		words_n = len(name.split())
		if words_n == 1:
			warns.append(f"«{name}» – лише одне слово (треба «Прізвище Імʼя»)")
		elif words_n > 3:
			warns.append(f"«{name}» – забагато слів")
		if name in seen:
			dups.add(name)
		seen.add(name)
		names.append(name)
	if not names:
		raise ValueError("Не бачу жодного імені. Напишіть: Прізвище Імʼя, Прізвище Імʼя")
	if dups:
		warns.append("Повтори: " + ", ".join(sorted(dups)))
	return names, warns


def normalize_plates(raw: str) -> list[str]:
	parts = _PLATE_SPLIT_RE.split(raw)
	return [_WS_RE.sub("", p).upper() for p in parts if p.strip()]


def normalize_students(lines: list[str]) -> list[str]:
	out: list[str] = []
	for ln in lines:
		s = _LIST_BULLET_RE.sub("", ln.strip())
		s = _WS_RE.sub(" ", norm_apos(s)).replace("‑", "-").strip().rstrip(",;.").strip()
		s = _STUDENT_GROUP_SEP_RE.sub(" ", s)
		if not s:
			continue
		words = s.split(" ")
		if words and GROUP_RE.match(words[-1]):
			words[-1] = words[-1].upper()
		out.append(" ".join(words))
	return out


def _norm_group(grp_raw: str) -> str:
	cleaned = grp_raw.replace("‑", "-")
	return cleaned.lower() if cleaned.lower().startswith("аспірант") else cleaned.upper()


def normalize_award_students(lines: list[str]) -> list[list[str]]:
	known = set(config.INSTITUTES) | config.LEGACY_INSTITUTES
	out: list[list[str]] = []
	for ln in lines:
		raw = _LIST_BULLET_RE.sub("", ln.strip())
		raw = norm_apos(raw).strip().rstrip(";.").strip()
		if not raw:
			continue
		if any(sep in raw for sep in ("\t", ";", "|")):
			cols = [
				_WS_RE.sub(" ", c).strip(" ,")
				for c in _AWARD_COL_SPLIT_RE.split(raw)
				if c.strip(" ,")
			]
			if len(cols) >= 3:
				out.append([" ".join(cols[:-2]), cols[-2].upper(), _norm_group(cols[-1])])
				continue
		tokens = [t.strip(",") for t in _AWARD_TOK_SPLIT_RE.split(raw) if t.strip(",")]
		if (
			len(tokens) >= 3
			and tokens[-2].upper() in known
			and is_valid_award_group(tokens[-1])
		):
			out.append([" ".join(tokens[:-2]), tokens[-2].upper(), _norm_group(tokens[-1])])
		else:
			out.append([" ".join(tokens), "", ""])
	return out


def parse_user_ids(raw: str) -> list[int]:
	tokens = [t.strip() for t in _UID_SPLIT_RE.split(raw.strip()) if t.strip()]
	if not tokens or not all((t.removeprefix("-")).isdigit() for t in tokens):
		raise ValueError("Invalid user ID list")
	return list(dict.fromkeys(int(t) for t in tokens))
