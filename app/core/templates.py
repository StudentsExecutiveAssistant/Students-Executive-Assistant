"""Моделі кроків, каталог шаблонів клопотань та правила підстановки адресатів і підписантів."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.config import (
	ADDRESSEES,
	BUILDINGS,
	EQUIP_ITEMS,
	EQUIP_PLACES,
	INSTITUTES,
	PLACE_WHERE,
	PROSVITA,
	ROOMS,
	SPORT,
	UNIVERSITY,
	WORKROOMS,
)
from app.core.cleaners import (
	clean_dept,
	clean_order,
	clean_project,
	clean_reason,
	clean_route,
)

Para = dict[str, Any]
Answers = dict[str, Any]
Spec = dict[str, Any]
APPENDIX_THRESHOLD = 9
AWARD_APPENDIX_THRESHOLD = 20

_DLYA_OR_METOYU_RE = re.compile(r"^(?:з\s+метою|для)\s+", re.IGNORECASE)
_PLACING_GOAL_RE = re.compile(r"^(?:з\s+метою|для\s+того,?\s+щоб|щоб)\b", re.IGNORECASE)
_AUD_COMMA_RE = re.compile(r"\s*,\s*")
_AUD_SPLIT_RE = re.compile(r"[,;]+|\s+(?:та|і|й)\s+")
_AUD_RANGE_RE = re.compile(r"^\d+[A-Za-zА-ЯІЇЄҐа-яіїєґ]?\s*[-–]\s*\d+")
_STUDENT_GROUP_RE = re.compile(r",?\s+([A-Za-zА-ЯІЇЄҐа-яіїєґ]{1,6}[-‑]\d{1,3})$")


@dataclass
class Step:
	key: str
	prompt: str
	kind: str = "text"
	choices: list[str] = field(default_factory=list)
	custom: bool = False
	optional: bool = False
	hint: str = ""
	cond: Callable[[Answers], bool] | None = None


@dataclass
class Template:
	id: str
	category: str
	title: str
	steps: list[Step]
	build: Callable[[Answers], tuple[list[Para], dict[str, Any] | None]]
	addressees: list[str] = field(default_factory=lambda: ["helzhynskyi"])
	signers: tuple[str, ...] = ("profkom", "kolehiia")
	heading: str = "КЛОПОТАННЯ"


CATEGORIES = {
	"rooms": "🏛 Приміщення і зали",
	"sport": "⚽ Спорт",
	"prosvita": "🎭 «Просвіта»",
	"territory": "🚗 Територія і розміщення",
	"tech": "🎤 Техніка і транспорт",
	"print": "🖨 Друк і закупівля",
	"dorm": "🏠 Студмістечко",
	"absence": "📋 Звільнення від пар",
	"award": "🏆 Преміювання",
	"other": "📝 Інше",
}

DATE_HINT = (
	"Формати: <code>26.11.2026</code> · <code>26-28.11.2026</code> · <code>з 26.11 по 02.12.2026</code> · "
	"<code>26.11, 28.11.2026</code> (або з нового рядка).\n"
	"Свій текст – з «!» на початку."
)


def DATE(p: str = "Коли?", cond: Callable[[Answers], bool] | None = None) -> Step:
	return Step("date", p, "date", hint=DATE_HINT, cond=cond)


def TIME(
	p: str = "Година? (початок-кінець)",
	cond: Callable[[Answers], bool] | None = None,
) -> Step:
	return Step(
		"time",
		p,
		"time",
		optional=True,
		hint="Наприклад <code>16:25-20:30</code> або <code>7-15</code>",
		cond=cond or (lambda a: not a.get("_timed")),
	)


def PURPOSE(ex: str, p: str = "Для чого? (без слів «для»)") -> Step:
	return Step("purpose", p, hint=f"Наприклад: <i>{ex}</i>")


RESP = Step("responsible", "Відповідальні за проведення", "responsible", optional=True)
ORG = Step(
	"organizers",
	"Організатори (необовʼязково)",
	optional=True,
	hint="Наприклад: <i>Колегія та профком студентів та аспірантів</i>",
)

WEEKDAYS = ["щопонеділка", "щовівторка", "щосереди", "щочетверга", "щоп’ятниці"]


def _body(txt: str) -> Para:
	return {"t": txt, "k": "body"}


def _resp(a: Answers, suffix: str = "") -> list[Para]:
	r = (a.get("responsible") or "").strip().rstrip(".")
	if not r:
		return []
	word = "Відповідальний" if a.get("_resp_n", 2) == 1 else "Відповідальні"
	return [_body(f"{word} за проведення{suffix}: {r}.")]


def _when(a: Answers) -> str:
	if a.get("_timed"):
		return str(a.get("date", ""))
	return " ".join(x for x in (str(a.get("date", "")), str(a.get("time", ""))) if x)


def _dlya(a: Answers) -> str:
	p = (a.get("purpose") or "").strip().rstrip(".")
	if not p:
		return ""
	return f" {p}" if _DLYA_OR_METOYU_RE.match(p) else f" для {p}"


def _safe_clean(fn: Callable[..., tuple[str, list[str]]], text: str, **kw: Any) -> str:
	s = (text or "").strip().rstrip(".")
	if not s:
		return ""
	try:
		return fn(s, **kw)[0].rstrip(".")
	except ValueError:
		return s


def _zvyazku(reason: str) -> str:
	return f"у зв’язку з {_safe_clean(clean_reason, reason, mode='zvyazku')}"


def premises(
	tid: str,
	category: str,
	title: str,
	places: list[str],
	addressee: str | list[str],
	ex: str,
	extra_steps: tuple[Step, ...] = (),
	builder: Callable[[Answers], tuple[list[Para], dict[str, Any] | None]] | None = None,
) -> Template:
	def build(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
		txt = f"Просимо Вашого дозволу на використання {a['what']} {_when(a)}{_dlya(a)}."
		return [_body(txt), *_resp(a)], None

	return Template(
		tid,
		category,
		title,
		[
			Step(
				"what",
				"Що саме використовуємо?",
				"choice",
				choices=places,
				custom=True,
				hint="Фраза після «на використання»: приміщення …, укриття …",
			),
			*extra_steps,
			DATE(),
			TIME(),
			PURPOSE(ex),
			RESP,
		],
		builder or build,
		[addressee] if isinstance(addressee, str) else list(addressee),
	)


def _semesters() -> list[str]:
	t = date.today()
	y1 = t.year if t.month >= 8 else t.year - 1
	ay = f"{y1}/{y1 + 1}"
	return [
		f"осіннього семестру {ay} навчального року",
		f"весняного семестру {ay} навчального року",
	]


def weekly(a: Answers) -> bool:
	return str(a.get("when_kind", "")).startswith("Щотижня")


def weekdays_sem(a: Answers) -> bool:
	return str(a.get("when_kind", "")).startswith("У будні")


def in_semester(a: Answers) -> bool:
	return weekly(a) or weekdays_sem(a)


def once(a: Answers) -> bool:
	return not in_semester(a)


def b_audience(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	if weekly(a):
		when = " ".join(
			x for x in (f"{a['weekday']} протягом {a['sem']}", str(a.get("time", ""))) if x
		)
	elif weekdays_sem(a):
		when = " ".join(
			x for x in (f"у будні дні протягом {a['sem']}", str(a.get("time", ""))) if x
		)
	else:
		when = _when(a)
	num = _AUD_COMMA_RE.sub(", ", a["num"].strip())
	nums = [x for x in _AUD_SPLIT_RE.split(num) if x.strip()]
	rooms = (
		f"приміщень {num} аудиторій"
		if (len(nums) > 1 or _AUD_RANGE_RE.search(num))
		else f"приміщення {num} аудиторії"
	)
	paras: list[Para] = [
		_body(
			f"Просимо Вашого дозволу на використання {rooms} {a['building']} {when}{_dlya(a)}."
		)
	]
	if a.get("organizers"):
		paras.append(_body(f"Організатори: {str(a['organizers']).rstrip('.')}."))
	paras += _resp(a)
	if a.get("keys"):
		paras.append(
			_body("Видавати ключі при наявності студентського квитка/посвідчення:")
		)
		paras += [{"t": n, "k": "list"} for n in a["keys"]]
	return paras, None


def _sport_extra_inv(a: Answers) -> bool:
	return (
		str(a.get("inv", "")).startswith("Так")
		and "інвентар" not in str(a.get("what", "")).lower()
	)


def b_sport(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	inv = _sport_extra_inv(a)
	what = a["what"] + (" та спортивного інвентарю" if inv else "")
	txt = f"Просимо Вашого дозволу на використання {what} {_when(a)}{_dlya(a)}."
	return [
		_body(txt),
		*_resp(a, " заходу та використання інвентарю" if inv else ""),
	], None


def b_equipment(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	place = f" {a['place']}" if a.get("place") else ""
	paras: list[Para] = [
		_body(
			f"Просимо Вашого дозволу на використання {a['items']}{place} {_when(a)}{_dlya(a)}."
		)
	]
	if a.get("organizers"):
		paras.append(_body(f"Організатори: {str(a['organizers']).rstrip('.')}."))
	paras += _resp(a)
	return paras, None


def b_placing(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	p = (a.get("purpose") or "").strip().rstrip(".")
	goal = (f" {p}" if _PLACING_GOAL_RE.match(p) else f" з метою {p}") if p else ""
	txt = (
		f"Просимо Вашого дозволу на розміщення {a['where']} {a['what']} {_when(a)}{goal}."
	)
	return [_body(txt), *_resp(a)], None


def b_vehicles(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	txt = (
		f"Просимо Вашого дозволу на в’їзд на територію {a['building']} {a['date']} "
		f"{_zvyazku(a['reason'])} машин з номерними знаками {a['plates']}."
	)
	return [_body(txt), *_resp(a)], None


def b_entry(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	txt = f"Просимо Вашого дозволу на вхід на територію {a['building']} {a['date']} {_zvyazku(a['reason'])}."
	return [_body(txt), *_resp(a)], None


def b_bus(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	route = _safe_clean(clean_route, a["route"])
	dept = _safe_clean(clean_dept, a["dept"])
	txt = f"Просимо Вас надати автобус для поїздки {route} {a['date']} від {dept}."
	return [_body(txt), *_resp(a)], None


def b_print(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	raw_order = _safe_clean(clean_order, a.get("order") or "")
	order = f" згідно з наказом №{raw_order}" if raw_order else ""
	return [
		_body(f"Просимо Вас надрукувати {a['what']}{_dlya(a)}{order}."),
		*_resp(a),
	], None


_PURCHASE_QTY_RE = re.compile(r"^(\d+)(\*?)$")
_FUND_DEFAULT_GOAL = (
	"відповідно до кошторису студентського самоврядування за рахунок "
	"Благодійного фонду Національного університету «Львівська політехніка»"
)


def parse_purchase_item(line: str) -> tuple[str, int, str, float]:
	parts = [x.strip() for x in line.split(";")]
	if len(parts) != 3 or not parts[0]:
		raise ValueError("Рядок має виглядати так: Назва; кількість; ціна")
	name, qty_raw, price_raw = parts
	qm = _PURCHASE_QTY_RE.fullmatch(qty_raw)
	if not qm:
		raise ValueError(f"Некоректна кількість «{qty_raw}» (приклад: 2 або 2*)")
	qty = int(qm.group(1))
	if qty <= 0:
		raise ValueError("Кількість має бути більшою за 0")
	price = float(price_raw.replace(",", "."))
	if price < 0:
		raise ValueError("Ціна не може бути відʼємною")
	return name, qty, qty_raw, price


def b_purchase(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	rows: list[list[str]] = []
	total = 0.0
	for i, line in enumerate(a.get("items", []), 1):
		name, qty, qty_disp, price = parse_purchase_item(line)
		total += qty * price
		rows.append([str(i), name, qty_disp, f"{price:g}", f"{qty * price:g}"])
	appendix: dict[str, Any] = {
		"kind": "table",
		"title": "Додаток 1",
		"header": ["№", "Найменування", "К-ть", "Ціна за од., грн", "Сума, грн"],
		"rows": [*rows, ["", "Разом", "", "", f"{total:g}"]],
		"note": (a.get("note") or "").strip(),
	}
	is_fund = str(a.get("kind", "")).startswith("Сприяння")
	goal = (a.get("goal") or "").strip().rstrip(".")
	if is_fund and not goal:
		goal = _FUND_DEFAULT_GOAL
	if is_fund:
		body = (
			f"Просимо Вашого сприяння у закупівлі техніки, зазначеної у Додатку 1, {goal}."
		)
	else:
		body = (
			"Звертаємось до Вас із проханням забезпечення технікою та іншим обладнанням, "
			f"зазначеним у Додатку 1, {goal}."
		)
	return [_body(body)], appendix


def b_guest(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	raw_proj = _safe_clean(clean_project, a.get("project") or "")
	proj = f" в межах {raw_proj}" if raw_proj else ""
	names: list[str] = a.get("names") or []
	below = (
		""
		if not names
		else ", зазначеної нижче,"
		if len(names) == 1
		else ", зазначених нижче,"
	)
	txt = f"Просимо Вас забезпечити поселення {a['who']}{below} на період {a['date']}{proj} на безкоштовній основі."
	return [_body(txt), *[{"t": n, "k": "names"} for n in names]], None


def b_workroom(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	txt = f"Просимо Вашого дозволу на використання {a['what']} у гуртожитку №{a['dorm']} {_when(a)}{_dlya(a)}."
	return [_body(txt), *_resp(a)], None


def b_monthly(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	txt = (
		f"Просимо Вашого дозволу оплачувати проживання у гуртожитку №{a['dorm']} помісячно у зв’язку "
		f"з важким матеріальним становищем {a['who']} {a['course']} курсу {a['level']} "
		f"{INSTITUTES[a['inst']][0]} {a['fio']}."
	)
	return [_body(txt)], None


def _fmt_student(s: str) -> str:
	return _STUDENT_GROUP_RE.sub(r" \1", s)


def b_absence(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	studs: list[str] = a["students"]
	head = f"Просимо Вас вважати відсутність на заняттях {a['date']} як з поважних причин {_zvyazku(a['reason'])}"
	if len(studs) == 1:
		who = a.get("who") or "студента"
		return [_body(f"{head} {who} {_fmt_student(studs[0])}.")], None
	items = [_fmt_student(s) for s in studs]
	use_appendix = len(studs) >= APPENDIX_THRESHOLD or str(
		a.get("in_appendix", "")
	).startswith("У Додатку")
	if use_appendix:
		return (
			[_body(f"{head} студентів, зазначених у Додатку 1.")],
			{"kind": "students", "title": "Додаток 1", "items": items},
		)
	return [
		_body(f"{head} наступних студентів:"),
		*[{"t": s, "k": "list"} for s in items],
	], None


def b_award(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	studs: list[list[str]] = a["students"]
	reason = _safe_clean(clean_reason, a["reason"], mode="za")
	form = a["form"]
	who = "студента" if len(studs) == 1 else "таких студентів"
	base = f"Просимо Вас преміювати за {reason} {who} {form} форми навчання"
	if len(studs) < AWARD_APPENDIX_THRESHOLD:
		return [_body(f"{base}:"), {"k": "rows", "items": studs}], None
	return (
		[_body(f"{base} (Додаток 1):")],
		{"kind": "award", "title": "Додаток 1", "items": studs},
	)


def b_free(a: Answers) -> tuple[list[Para], dict[str, Any] | None]:
	return [_body(a["text"]), *_resp(a)], None


TEMPLATES: dict[str, Template] = {
	t.id: t
	for t in [
		premises(
			"rooms",
			"rooms",
			"Приміщення / зала / укриття / коридор",
			ROOMS,
			"helzhynskyi",
			"проведення події «Кіновечір»",
		),
		Template(
			"audience",
			"rooms",
			"Аудиторія (одноразово або на семестр)",
			[
				Step(
					"num",
					"Номер аудиторії?",
					hint="Наприклад: <code>214</code> або кілька: <code>401, 402, 403</code>",
				),
				Step("building", "Корпус?", "choice", choices=BUILDINGS, custom=True),
				Step(
					"when_kind",
					"Як часто?",
					"choice",
					choices=[
						"Одноразово",
						"Щотижня протягом семестру",
						"У будні дні протягом семестру",
					],
				),
				DATE(cond=once),
				Step("weekday", "Який день тижня?", "choice", choices=WEEKDAYS, cond=weekly),
				Step("sem", "Який семестр?", "choice", choices=_semesters(), cond=in_semester),
				TIME(cond=lambda a: in_semester(a) or not a.get("_timed")),
				PURPOSE("проведення засідань Колегії та профбюро студентів ІЕСК"),
				RESP,
				ORG,
				Step(
					"keys",
					"Кому видавати ключі? (по одному в рядку, необовʼязково)",
					"lines",
					optional=True,
					hint="Імена зі студентським/посвідченням",
				),
			],
			b_audience,
			["zhezhus", "institute"],
		),
		premises(
			"sport",
			"sport",
			"Спортивна зала / поле / інвентар",
			SPORT,
			["helzhynskyi", "studmistechko", "fizvykhovannia"],
			"проведення змагань з баскетболу в межах «Спортивної ліги»",
			extra_steps=(
				Step(
					"inv",
					"Потрібен спортивний інвентар?",
					"choice",
					choices=["Ні", "Так (клопотання піде завідувачу кафедри фізвиховання)"],
					cond=lambda a: "інвентар" not in str(a.get("what", "")).lower(),
				),
			),
			builder=b_sport,
		),
		premises(
			"prosvita",
			"prosvita",
			"«Просвіта»: зал / костюми / кафе",
			PROSVITA,
			"prosvita",
			"підготовки до традиційного фестивалю “Весна Політехніки”",
		),
		Template(
			"placing",
			"territory",
			"Розміщення (стійки, банери, промоакція)",
			[
				Step(
					"where",
					"Де розмістити?",
					"choice",
					choices=PLACE_WHERE,
					custom=True,
					hint="Із прийменником: <i>в коридорі навчального корпусу №4</i>",
				),
				Step(
					"what",
					"Що розмістити?",
					hint="У родовому: <i>інтерактивних стійок</i>, <i>банера</i>",
				),
				DATE(),
				TIME(),
				PURPOSE(
					"проведення промоакції в межах заходу «Red Bull Wings Cup»",
					"З якою метою? (без слів «з метою»)",
				),
				RESP,
			],
			b_placing,
		),
		Template(
			"vehicles",
			"territory",
			"В’їзд машин на територію",
			[
				Step("building", "Корпус?", "choice", choices=BUILDINGS, custom=True),
				DATE(),
				Step(
					"reason",
					"У зв’язку з чим? (без слів «у зв’язку з»)",
					hint="Наприклад: <i>організацією та підготовкою до фестивалю «Осінь Політехніки»</i>",
				),
				Step(
					"plates", "Номерні знаки (через кому)", hint="<code>ВС1640ЕР, ВС5703КО</code>"
				),
				RESP,
			],
			b_vehicles,
		),
		Template(
			"entry",
			"territory",
			"Вхід на територію (вихідні, репетиції)",
			[
				Step("building", "Корпус?", "choice", choices=BUILDINGS, custom=True),
				DATE("Коли? (напр. «!у вихідні дні з …»)"),
				Step("reason", "У зв’язку з чим? (без слів «у зв’язку з»)"),
				RESP,
			],
			b_entry,
		),
		Template(
			"equipment",
			"tech",
			"Звуковий супровід / техніка",
			[
				Step(
					"items",
					"Що саме?",
					"choice",
					choices=EQUIP_ITEMS,
					custom=True,
					hint="Для звуку обирайте «звукового супроводу» – без переліку мікрофонів і колонок.",
				),
				Step(
					"place",
					"Де проходитиме? (місце проведення)",
					"choice",
					choices=EQUIP_PLACES,
					custom=True,
					optional=True,
					hint="Своє – із прийменником: <i>в залі №40 навчального корпусу №22</i>",
				),
				DATE(),
				TIME(),
				PURPOSE("проведення змагання з баскетболу в межах «Спортивної ліги»"),
				ORG,
				RESP,
			],
			b_equipment,
			["lohoida"],
		),
		Template(
			"bus",
			"tech",
			"Автобус",
			[
				Step("route", "Маршрут?", hint="<i>у Кам’янець-Подільський та Хотин</i>"),
				DATE(),
				Step(
					"dept",
					"Від кого?",
					hint="<i>туристичного відділу Колегії та профкому студентів та аспірантів</i>",
				),
				RESP,
			],
			b_bus,
		),
		Template(
			"print",
			"print",
			"Друк (квитки, афіші, матеріали)",
			[
				Step("what", "Що друкуємо?", hint="<i>700 квитків та 15 афіш</i>"),
				PURPOSE("виступу команди на фестивалі «Весна Політехніки»"),
				Step(
					"order",
					"№ наказу (необовʼязково)",
					optional=True,
					hint="Наприклад <code>168-1-10</code>",
				),
				RESP,
			],
			b_print,
			["vydavnytstvo"],
		),
		Template(
			"purchase",
			"print",
			"Закупівля (з таблицею Додаток 1)",
			[
				Step(
					"kind",
					"Формулювання?",
					"choice",
					choices=[
						"Забезпечення технікою та обладнанням (стандартне)",
						"Сприяння у закупівлі техніки (Благодійний фонд)",
					],
				),
				Step(
					"goal",
					"З якою метою? (закінчення речення після «Додатку 1,»)",
					hint="<i>з метою розширення можливостей для проведення студентських подій</i>",
					cond=lambda a: not str(a.get("kind", "")).startswith("Сприяння"),
				),
				Step(
					"goal",
					"Підстава / мета (необовʼязково — для БФ підставиться стандартно)",
					optional=True,
					hint="Натисніть «Пропустити» для тексту про кошторис і Благодійний фонд.",
					cond=lambda a: str(a.get("kind", "")).startswith("Сприяння"),
				),
				Step(
					"items",
					"Позиції: по одній у рядку",
					"lines",
					hint="Формат: <code>Назва; кількість; ціна за одиницю</code> (у кількості можна <code>2*</code>)",
				),
				Step(
					"note",
					"Примітка під таблицею Додатку 1 (необовʼязково)",
					optional=True,
					hint="Наприклад: <i>Закупівля по 1 одиниці, однак, за можливості, у кількості 2 одиниць.</i>",
				),
			],
			b_purchase,
			["lohoida", "rector"],
		),
		Template(
			"guest",
			"dorm",
			"Поселення (гостьова кімната)",
			[
				Step(
					"who",
					"Кого селимо?",
					hint="<i>чотирьох осіб</i> або ПІБ у давальному: <i>Овдієнку Максиму Вікторовичу</i>",
				),
				DATE("На який період?"),
				Step(
					"project",
					"У межах чого? (необовʼязково)",
					optional=True,
					hint="<i>проєкту «Плацкарт»</i>",
				),
				Step(
					"names",
					"ПІБ гостей: по одному в рядку (необовʼязково)",
					"lines",
					optional=True,
					hint="Підуть списком під текстом: <code>Іваненко Олена Петрівна</code>",
				),
			],
			b_guest,
			["helzhynskyi"],
		),
		Template(
			"workroom",
			"dorm",
			"Робоча кімната / танцювальний простір у гуртожитку",
			[
				Step("what", "Що саме?", "choice", choices=WORKROOMS, custom=True),
				Step("dorm", "№ гуртожитку?"),
				DATE(),
				TIME(),
				PURPOSE("підготовки до фестивалю «Весна Політехніки»"),
				RESP,
			],
			b_workroom,
			["helzhynskyi"],
		),
		Template(
			"monthly",
			"dorm",
			"Помісячна оплата проживання",
			[
				Step("dorm", "№ гуртожитку?"),
				Step("who", "Хто?", "choice", choices=["студенту", "студентці"]),
				Step(
					"course",
					"Курс?",
					"choice",
					choices=["першого", "другого", "третього", "четвертого"],
				),
				Step("level", "Рівень?", "choice", choices=["бакалаврату", "магістратури"]),
				Step("inst", "Інститут?", "institute"),
				Step("fio", "ПІБ студента (повністю)"),
			],
			b_monthly,
			["rector"],
			signers=("profkom",),
		),
		Template(
			"absence",
			"absence",
			"Звільнення від пар",
			[
				Step("inst", "Який інститут? (кому адресуємо)", "institute"),
				DATE(),
				Step(
					"reason",
					"У зв’язку з чим? (без слів «у зв’язку з»)",
					hint="<i>проведенням виборів Голів студентських рад гуртожитків</i>",
				),
				Step(
					"students",
					"Студенти: по одному в рядку",
					"lines",
					hint=(
						"Один студент – у родовому: <code>Терещенка Нікіти ПТ-32</code>.\n"
						"Кілька – у називному: <code>Прізвище Імʼя ГРУПА</code>\n"
						"2–8 студентів – у тексті або в «Додатку»; від 9 – автоматично у «Додаток»."
					),
				),
				Step(
					"in_appendix",
					"Де розмістити список студентів?",
					"choice",
					choices=["У тексті (на одному аркуші)", "У Додатку 1"],
					cond=lambda a: 2 <= len(a.get("students", [])) <= 8,
				),
				Step(
					"who",
					"Рід у тексті (для 1 особи)?",
					"choice",
					choices=["студента", "студентки"],
					cond=lambda a: len(a.get("students", [])) == 1,
				),
			],
			b_absence,
			["institute"],
		),
		Template(
			"award",
			"award",
			"Преміювання студентів",
			[
				Step("form", "Форма навчання?", "choice", choices=["бюджетної", "комерційної"]),
				Step(
					"reason",
					"За що преміюємо? (без слова «за»)",
					hint="Наприклад: <i>активну громадську діяльність</i> або <i>організацію на «Тижні першокурсника»</i>",
				),
				Step(
					"students",
					"Студенти: по одному в рядку",
					"lines",
					hint=(
						"Формат: <code>Прізвище Імʼя По-батькові ІНСТИТУТ Група</code>\n"
						"Можна копіювати прямо з таблиці (Excel / Google Таблиць).\n"
						"До 19 студентів – у тексті, від 20 – автоматично у «Додаток»."
					),
				),
			],
			b_award,
			["rector"],
		),
		Template(
			"free",
			"other",
			"Довільне клопотання",
			[
				Step(
					"text",
					"Напишіть основний текст клопотання",
					hint="Починайте з «Просимо Вашого дозволу…»",
				),
				RESP,
			],
			b_free,
			["helzhynskyi", "zhezhus", "lohoida", "rector", "engineer", "institute"],
		),
	]
}


def addressee_key(tpl: Template, a: Answers) -> str:
	if a.get("addressee"):
		return str(a["addressee"])
	if tpl.id == "sport":
		if (
			"Лукаша, 4" in str(a.get("what", ""))
			or "футбольних полів" in str(a.get("what", "")).lower()
		):
			return "studmistechko"
		if _sport_extra_inv(a):
			return "fizvykhovannia"
	if tpl.id == "equipment" and "L.I.S." in str(a.get("place", "")):
		return "erdt"
	return tpl.addressees[0]


def addressee_lines(tpl: Template, a: Answers) -> list[str]:
	key = addressee_key(tpl, a)
	if key == "institute":
		name, who = INSTITUTES[a["inst"]]
		return ["Директору", name, *UNIVERSITY, who]
	return ADDRESSEES[key][1]


def signers_for(tpl: Template, a: Answers) -> list[str]:
	s = list(tpl.signers)
	# Приміщення простору L.I.S. додатково погоджує керівник центру тьюторства.
	if tpl.id == "rooms" and "L.I.S." in str(a.get("what", "")):
		s.append("tutor")
	return s


def visible_steps(tpl: Template, a: Answers) -> list[Step]:
	steps = [s for s in tpl.steps if s.cond is None or s.cond(a)]
	if len(tpl.addressees) > 1:
		steps.append(
			Step("addressee", "Кому адресуємо?", "addressee", choices=tpl.addressees)
		)
		if "institute" in tpl.addressees and a.get("addressee") == "institute":
			steps.append(Step("inst", "Який інститут?", "institute"))
	return steps


def addressee_label(key: str) -> str:
	return (
		"Директору інституту (як у списку)" if key == "institute" else ADDRESSEES[key][0]
	)


def has_time_step(tpl_id: str) -> bool:
	return any(s.key == "time" for s in TEMPLATES[tpl_id].steps)


def build_spec(tpl_id: str, a: Answers) -> Spec:
	tpl = TEMPLATES[tpl_id]
	paras, appendix = tpl.build(a)
	return {
		"addressee": addressee_lines(tpl, a),
		"heading": tpl.heading,
		"paras": paras,
		"appendix": appendix,
		"signers": signers_for(tpl, a),
	}
