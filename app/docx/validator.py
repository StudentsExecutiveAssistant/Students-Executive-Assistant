"""Перевірка тексту, чернетки клопотання перед генерацією та завантажених файлів .docx."""

from __future__ import annotations

import html
import re
from datetime import date
from io import BytesIO
from typing import Any

from app import config
from app.core.cleaners import (
	CYR,
	GROUP_RE,
	LAT,
	PLATE_RE,
	is_valid_award_group,
	norm_apos,
	normalize_plates,
)
from app.core.dates import MONTHS

Issue = tuple[str, str]
ICON = {"err": "❌", "warn": "⚠️", "info": "ℹ️"}
_ISSUE_ORDER = {"err": 0, "warn": 1, "info": 2}
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"]
RESP_EXPECTED = {
	"rooms",
	"audience",
	"sport",
	"prosvita",
	"equipment",
	"vehicles",
	"entry",
	"workroom",
	"bus",
	"placing",
}
_TIMED_EXPECTED = {
	"rooms",
	"audience",
	"sport",
	"prosvita",
	"equipment",
	"workroom",
	"placing",
}
_PURPOSE_EXPECTED = {"rooms", "audience", "sport", "prosvita", "equipment", "workroom"}

_INNER_MULTI_SPACE_RE = re.compile(r"(?<=\S) {2,}(?=\S)")
_STRAIGHT_APOS_RE = re.compile(rf"(?<=[{CYR}{LAT}])'(?=[{CYR}{LAT}])")
_SPACE_PUNCT_RE = re.compile(r" [,.;:!?]")
_COMMA_LETTER_RE = re.compile(rf",[{CYR}{LAT}]")
_DUP_WORD_RE = re.compile(r"\b([А-Яа-яІіЇїЄєҐґ]+)\s+(\1)\b(?!\.)", re.IGNORECASE)
_ZVYAZKU_DUP_Z_RE = re.compile(
	r"\b(?:у|в)\s+зв[’ʼ'`´]?язку\s+(?:з|із|зі)\s+(?:з|із|зі)\b", re.IGNORECASE
)
_ZVYAZKU_DUP_RE = re.compile(
	r"\b(?:у|в)\s+зв[’ʼ'`´]?язку\s+(?:з|із|зі)\s+(?:у|в)\s+зв[’ʼ'`´]?язку\b",
	re.IGNORECASE,
)
_ZVYAZKU_CUT_RE = re.compile(
	r"\b(?:у|в)\s+зв[’ʼ'`´]?язку\s+(?:з|із|зі)\s*[,.!?;:]|\b(?:у|в)\s+зв[’ʼ'`´]?язку\s+(?:з|із|зі)\s*$",
	re.IGNORECASE,
)
_METOYU_DLYA_WARN_RE = re.compile(
	r"\b(?:з\s+метою\s+для|для\s+з\s+метою)\b", re.IGNORECASE
)
_DLYA_CUT_RE = re.compile(r"\bдля\s*[,.!?;:]|\bдля\s*$", re.IGNORECASE)
_WORD_TOK_RE = re.compile(r"[\w’']+(?:-[\w’']+)*")
_CYR_CHAR_RE = re.compile(f"[{CYR}]")
_LAT_CHAR_RE = re.compile(f"[{LAT}]")
_RESP_TYPO_RE = re.compile(r"Відповідальн(?!і за проведення|ий за проведення)")
_LOWER_START_RE = re.compile(r"^[а-яіїєґ]")
_END_PUNCT_RE = re.compile(r"[.:!?]$")

_AUD_SPLIT_RE = re.compile(r"[,;]+|\s+(?:та|і|й)\s+|[-–]")
_AUD_TOKEN_RE = re.compile(rf"^\d{{1,4}}[{CYR}{LAT}]?$")
_DORM_NUM_RE = re.compile(r"^\d{1,3}$")
_FREE_START_RE = re.compile(r"Прос[иі]|Прошу|Звертаємось")
_DOCX_START_RE = re.compile(r"Прос[иі]|Прошу|Звертаємось|Шановн")

_MONTHS_RE = "|".join(MONTHS)
DATE_RE = re.compile(
	rf"(\d{{1,2}})(?:\s*[-–]\s*(\d{{1,2}}))?\s+({_MONTHS_RE})(?:\s+(\d{{4}}))?"
)
_SURNAME_WORDS_RE = re.compile(r"[А-ЯІЇЄҐ’ʼ'-]{3,}")
HEAD_START = re.compile(
	r"^\s*(проректору|ректору|директору|головному|завідувачу|голові|в\.?\s*о\.?\s+керівника)",
	re.IGNORECASE,
)
_PETITION_HEADING_RE = re.compile(r"^\s*\*{0,2}клопотання\*{0,2}\s*$", re.IGNORECASE)
_DOCX_STUDENT_LINE_RE = re.compile(rf"[{CYR}]+.*\s[{CYR}{LAT}]{{1,6}}[-‑]\d{{1,3}}\s*$")
_DOCX_PLATES_RE = re.compile(r"знаками?:?\s*([^\n]+)")


def text_issues(text: str, *, sentence: bool = True) -> list[Issue]:
	res: list[Issue] = []
	t = text.strip()
	if not t:
		return res
	if _INNER_MULTI_SPACE_RE.search(t):
		res.append(("warn", "Подвійні пробіли в тексті"))
	if '"' in t:
		res.append(("warn", 'Прямі лапки " замість «» чи “”'))
	if _STRAIGHT_APOS_RE.search(t):
		res.append(("warn", "Прямий апостроф ' (краще ’)"))
	if "ʼ" in t and "’" in t:
		res.append(("info", "Змішані апострофи (ʼ та ’)"))
	if _SPACE_PUNCT_RE.search(t):
		res.append(("warn", "Пробіл перед розділовим знаком"))
	if _COMMA_LETTER_RE.search(t):
		res.append(("warn", "Немає пробілу після коми"))
	if "..." not in t and ".." in t:
		res.append(("warn", "Подвійна крапка"))
	for o, c, nm in (("«", "»", "«»"), ("(", ")", "()"), ("“", "”", "“”")):
		if t.count(o) != t.count(c):
			res.append(("warn", f"Незакриті дужки/лапки {nm}"))
	if ("«" in t or "»" in t) and ("“" in t or "”" in t):
		res.append(("info", "Змішані лапки «» та “”"))
	for m in _DUP_WORD_RE.finditer(t):
		w1, w2 = m.group(1), m.group(2)
		if not (len(w1) == 1 and w1.islower() and w2.isupper()):
			res.append(("warn", f"Повтор слова «{w1}»"))
			break
	if _ZVYAZKU_DUP_Z_RE.search(t):
		res.append(("warn", "Зайве «з» після «у зв’язку з»"))
	if _ZVYAZKU_DUP_RE.search(t):
		res.append(("warn", "Повтор «у зв’язку з»"))
	if _ZVYAZKU_CUT_RE.search(t):
		res.append(("warn", "Обірване «у зв’язку з»"))
	if _METOYU_DLYA_WARN_RE.search(t):
		res.append(("warn", "Зайве «для» поруч із «з метою»"))
	if _DLYA_CUT_RE.search(t):
		res.append(("warn", "Зайве або обірване «для»"))
	for tok in dict.fromkeys(_WORD_TOK_RE.findall(t)):
		for part in tok.split("-"):
			if _CYR_CHAR_RE.search(part) and _LAT_CHAR_RE.search(part):
				res.append(("warn", f"«{part}» – змішано кирилицю й латиницю (схожі літери)"))
	if _RESP_TYPO_RE.search(t):
		res.append(("warn", "Схоже на помилку: має бути «Відповідальні за проведення»"))
	if sentence:
		if _LOWER_START_RE.match(t):
			res.append(("warn", "Речення починається з малої літери"))
		if not _END_PUNCT_RE.search(t):
			res.append(("warn", "Немає крапки в кінці"))
	return res


def _append_student_list_summary(
	res: list[Issue], keys: list[str], total: int, spec: dict[str, Any]
) -> None:
	if len(set(keys)) != len(keys):
		res.append(("warn", "У списку є дублікати студентів"))
	app_note = f" ({spec['appendix']['title']})" if spec.get("appendix") else ""
	res.append(("info", f"Студентів у списку: {total}{app_note}"))


def check(
	tid: str, a: dict[str, Any], spec: dict[str, Any], today: date | None = None
) -> list[Issue]:
	today = today or date.today()
	res: list[Issue] = []
	dates = a.get("_dates") or []
	for s_, e_ in dates:
		s, e = date.fromisoformat(s_), date.fromisoformat(e_)
		label = f"{s:%d.%m.%Y}" + (f"–{e:%d.%m.%Y}" if e != s else "")
		if e < today:
			res.append(("err", f"Дата {label} вже минула"))
			continue
		if s < today:
			res.append(("warn", f"Початок ({s:%d.%m.%Y}) вже минув"))
		elif (s - today).days <= 2:
			res.append(
				(
					"warn",
					f"До {s:%d.%m.%Y} лишилось ≤ 2 днів – клопотання можуть не встигнути розглянути",
				)
			)
		if (s - today).days > 365:
			res.append(("warn", f"Дата {label} більш ніж через рік – перевірте рік"))
		if (e - s).days > 92:
			res.append(("warn", f"Проміжок {label} понад 3 місяці"))
		if s == e and s.weekday() >= 5 and tid not in ("entry", "guest", "vehicles"):
			res.append(("info", f"{s:%d.%m.%Y} – {WEEKDAYS[s.weekday()]} (вихідний)"))
	if (
		a.get("date")
		and not dates
		and not str(a["date"]).startswith("щ")
		and tid != "audience"
	):
		res.append(("info", "Дату введено вручну (з «!») – я її не перевіряю"))
	times = [a["_time"]] if a.get("_time") else (a.get("_times") or [])
	if times:
		for st, en in times:
			if en is not None and en <= st:
				issue = ("err", "Кінець події раніше за початок або рівний йому")
				if issue not in res:
					res.append(issue)
			if st < 7 * 60 or (en is not None and en > 23 * 60):
				issue = ("warn", "Незвичний час (до 7:00 або після 23:00)")
				if issue not in res:
					res.append(issue)
			if en is not None and en - st > 14 * 60:
				issue = ("warn", "Подія триває понад 14 годин")
				if issue not in res:
					res.append(issue)
	elif tid in _TIMED_EXPECTED and not a.get("time") and not a.get("_timed"):
		res.append(("info", "Не вказано години"))
	if tid in RESP_EXPECTED and not (a.get("responsible") or "").strip():
		res.append(("warn", "Не вказано відповідальних за проведення"))
	if tid in _PURPOSE_EXPECTED and not a.get("purpose"):
		res.append(("info", "Не вказано мету («для …»)"))
	if tid == "audience":
		nums = [x.strip() for x in _AUD_SPLIT_RE.split(a.get("num", "")) if x.strip()]
		if not nums or not all(_AUD_TOKEN_RE.fullmatch(x) for x in nums):
			res.append(("warn", f"Номер аудиторії «{a.get('num')}» виглядає дивно"))
	if tid in ("workroom", "monthly") and not _DORM_NUM_RE.fullmatch(a.get("dorm", "")):
		res.append(("warn", f"№ гуртожитку «{a.get('dorm')}» – очікується число"))
	if tid == "vehicles":
		plates = normalize_plates(a.get("plates", ""))
		for p in plates:
			if not PLATE_RE.match(p):
				res.append(("warn", f"Номерний знак «{p}» не схожий на формат АА1234АА"))
		if len(set(plates)) != len(plates):
			res.append(("warn", "Є однакові номерні знаки"))
	if tid == "absence":
		studs = a.get("students", [])
		if not studs:
			res.append(("err", "Порожній список студентів"))
		for s in studs:
			w = s.split()
			if len(w) < 2 or not GROUP_RE.match(w[-1]):
				res.append(
					("warn", f"«{s}» – немає групи в кінці (формат: Прізвище Імʼя ЕЕ-11)")
				)
		_append_student_list_summary(res, [s.lower() for s in studs], len(studs), spec)
	if tid == "award":
		studs = a.get("students", [])
		if not studs:
			res.append(("err", "Порожній список студентів"))
		fios: list[str] = []
		for row in studs:
			fio, inst, grp = [*row, "", "", ""][:3]
			fios.append(fio.lower())
			if not inst or not grp:
				res.append(
					(
						"warn",
						f"«{fio}» – формат: ПІБ ІНСТИТУТ ГРУПА (напр. Оршак Максим Олександрович ІПМТ РК-31)",
					)
				)
			else:
				if inst not in config.INSTITUTES:
					res.append(("warn", f"«{fio}» – невідомий інститут «{inst}»"))
				if not is_valid_award_group(grp):
					res.append(("warn", f"«{fio}» – група «{grp}» не схожа на формат ЕЕ-11"))
		_append_student_list_summary(res, fios, len(studs), spec)
	app = spec.get("appendix")
	if tid == "purchase" and app and app.get("kind") == "table":
		names = [r[1].lower() for r in app["rows"][:-1]]
		if len(set(names)) != len(names):
			res.append(("warn", "Є однакові позиції в таблиці"))
	if tid == "free" and not _FREE_START_RE.search(a.get("text", "")):
		res.append(("info", "Зазвичай текст починається з «Просимо…» / «Звертаємось…»"))
	seen: set[tuple[str, str]] = set()
	for p in spec["paras"]:
		if p["k"] == "body":
			for lv, msg in text_issues(p["t"]):
				if (lv, msg) not in seen:
					seen.add((lv, msg))
					res.append((lv, msg))
	extra_txt = " ".join(
		p["t"]
		if p["k"] in ("list", "names")
		else " ".join(" ".join(r) for r in p["items"])
		if p["k"] == "rows"
		else " ".join(p["items"])
		for p in spec["paras"]
		if p["k"] in ("list", "names", "rows")
	)
	for lv, msg in text_issues(extra_txt, sentence=False):
		if (lv, msg) not in seen and "Подвійні" not in msg:
			seen.add((lv, msg))
			res.append((lv, msg))
	for fx in a.get("_fixes", []):
		res.append(("info", f"Автоматично виправлено: {fx}"))
	return sorted(res, key=lambda x: _ISSUE_ORDER[x[0]])


def format_issues(issues: list[Issue]) -> str:
	if not issues:
		return "🔍 <b>Перевірка:</b> ✅ усе гаразд"
	return "🔍 <b>Перевірка:</b>\n" + "\n".join(
		f"{ICON[lv]} {html.escape(m)}" for lv, m in issues
	)


def _surname(line: str) -> str:
	m = _SURNAME_WORDS_RE.findall(line)
	return norm_apos(m[-1]) if m else ""


def _known_surnames() -> set[str]:
	out = {_surname(lines[-1]) for _, lines in config.ADDRESSEES.values()}
	out.update(_surname(who) for _, who in config.INSTITUTES.values())
	return out


def _signer_surnames() -> list[str]:
	return [n.split()[-1] for _, n in config.SIGNERS.values()]


def _header_start(
	paras: list[str], m: int, sign_names: list[str], addr_names: set[str] | None = None
) -> int | None:
	"""Шукає назад від «КЛОПОТАННЯ» перший рядок шапки адресата."""
	if addr_names is None:
		addr_names = {lines[-1].strip() for _, lines in config.ADDRESSEES.values()}
	j, seen, empties = m - 1, 0, 0
	while j >= 0 and seen < 8:
		t = paras[j].strip()
		if not t:
			empties += 1
			if empties >= 4:
				return None
		else:
			if len(t) > 80 or (t not in addr_names and any(n in t for n in sign_names)):
				return None
			empties, seen = 0, seen + 1
			if HEAD_START.match(t):
				return j
		j -= 1
	return None


def _split_petitions(
	paras: list[str], sign_names: list[str]
) -> list[tuple[list[str], list[str]]]:
	addr_names = {lines[-1].strip() for _, lines in config.ADDRESSEES.values()}
	marks = [i for i, p in enumerate(paras) if _PETITION_HEADING_RE.match(p)]
	starts = [_header_start(paras, m, sign_names, addr_names) for m in marks]
	blocks: list[tuple[list[str], list[str]]] = []
	for k, m in enumerate(marks):
		nxt = next(
			(
				starts[x] if starts[x] is not None else marks[x]
				for x in range(k + 1, len(marks))
			),
			len(paras),
		)
		head = (
			[p for p in paras[starts[k] : m] if p.strip()] if starts[k] is not None else []
		)
		blocks.append((head, paras[m + 1 : nxt]))
	return blocks


def check_docx(data: bytes, today: date | None = None) -> list[str]:
	from docx import Document

	today = today or date.today()
	doc = Document(BytesIO(data))
	paras = [p.text for p in doc.paragraphs]
	sign_names = _signer_surnames()
	blocks = _split_petitions(paras, sign_names)
	if not blocks:
		return [
			"Не знайшов у файлі слово «КЛОПОТАННЯ» окремим рядком – нічого перевіряти 🤷"
		]
	known = _known_surnames()
	all_text = "".join(doc.element.body.itertext())
	out = [f"📄 Знайшов клопотань: <b>{len(blocks)}</b>"]
	for k, (head, body) in enumerate(blocks, 1):
		issues: list[Issue] = []
		main = next((b for b in body if len(b.strip()) > 25), "")
		title = html.escape(re.sub(r"\s+", " ", main.strip())[:70])
		sn = _surname(head[-1]) if head else ""
		if not head:
			issues.append(("err", "Немає шапки (кому адресовано)"))
		else:
			if "університету" not in " ".join(head).lower():
				issues.append(
					("warn", "У шапці немає «Національного університету «Львівська політехніка»»")
				)
			if sn and sn not in known:
				issues.append(
					(
						"info",
						f"Адресата «{head[-1].strip()}» немає в data/officials.json – перевірте прізвище й відмінок",
					)
				)
		joined = "\n".join(body)
		expected_signers = [config.SIGNERS["profkom"][1].split()[-1]]
		if "помісячно" not in joined.lower():
			expected_signers.append(config.SIGNERS["kolehiia"][1].split()[-1])
		if "L.I.S." in joined:
			expected_signers.append(config.SIGNERS["tutor"][1].split()[-1])
		for n in expected_signers:
			if n not in joined and all_text.count(n) < len(blocks):
				issues.append(("info", f"Не бачу підпису з прізвищем {n}"))
		shown = 0
		for p in body:
			ms = list(DATE_RE.finditer(p))
			for idx, m in enumerate(ms):
				y = m.group(4) or next((x.group(4) for x in ms[idx:] if x.group(4)), None)
				if not y:
					continue
				try:
					month_num = MONTHS.index(m.group(3)) + 1
					d1 = date(int(y), month_num, int(m.group(1)))
					if m.group(2) is not None:
						date(int(y), month_num, int(m.group(2)))
				except ValueError:
					issues.append(("err", f"Неіснуюча дата «{m.group(0)}»"))
					continue
				if int(y) > today.year + 1:
					issues.append(("err", f"Дивний рік у даті «{m.group(0)} {y}»"))
				elif d1 < today and shown < 2:
					issues.append(("warn", f"Дата {d1:%d.%m.%Y} вже минула (застарілий шаблон?)"))
					shown += 1
				elif m.group(2) is None and d1.weekday() >= 5 and d1 >= today:
					issues.append(("info", f"{d1:%d.%m.%Y} – {WEEKDAYS[d1.weekday()]}"))
		seen: set[tuple[str, str]] = set()
		students: list[str] = []
		for p in body:
			ps = p.strip()
			if (
				not ps
				or any(n in p for n in sign_names)
				or p.lstrip().startswith(("Голова профкому", "студентів"))
			):
				continue
			is_sentence = len(ps) > 60
			for lv, msg in text_issues(p.lstrip(), sentence=is_sentence):
				if (lv, msg) not in seen:
					seen.add((lv, msg))
					issues.append((lv, msg))
			if _DOCX_STUDENT_LINE_RE.search(ps) and not is_sentence:
				students.append(ps)
		if main and not _DOCX_START_RE.search(main):
			issues.append(
				("info", "Основне речення не починається з «Просимо…» / «Звертаємось…»")
			)
		if len({s.lower() for s in students}) != len(students):
			issues.append(("warn", "У списку студентів є дублікати"))
		for plate in _DOCX_PLATES_RE.findall(joined):
			for p in normalize_plates(plate.rstrip(".")):
				if not PLATE_RE.match(p):
					issues.append(("warn", f"Номерний знак «{p}» не схожий на формат АА1234АА"))
		issues.sort(key=lambda x: _ISSUE_ORDER[x[0]])
		if issues:
			out.append(
				f"\n<b>№{k}</b> <i>{title}…</i>\n"
				+ "\n".join(f"{ICON[lv]} {html.escape(m)}" for lv, m in issues)
			)
		else:
			out.append(f"\n<b>№{k}</b> <i>{title}…</i>\n✅ зауважень немає")
	return out
