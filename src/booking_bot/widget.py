"""Интерактивный календарь записи прямо в чате — HTML-виджет Telegram (Bot API 10.4).

Как это работает:
1. Клиент выбрал услугу и мастера и нажал «🗓 Календарь». Бот отправляет виджет (sendWidget):
   HTML-шаблон один на всех, а свободное время лежит в chat_data (компактный JSON до 1 КБ).
2. Клиент листает дни и нажимает время — виджет шлёт боту запрос (widget_query) вида
   «b:<услуга>:<мастер>:<ГГГГММДД>:<минуты>».
3. Бот перепроверяет время на сервере. Если свободно — переводит клиента к вводу имени
   (дальше обычный сценарий записи), если занято — обновляет календарь в сообщении.

aiogram 3.31 ещё не знает про виджеты, поэтому методы API описаны здесь,
а widget_query перехватывается middleware на уровне Update.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.methods.base import TelegramMethod
from aiogram.types import Message, Update

from booking_bot import texts
from booking_bot.config import Service, Settings
from booking_bot.db import Database
from booking_bot.slots import ANY_MASTER, candidate_masters, days_with_slots, free_masters_at, slots_for

log = logging.getLogger(__name__)

UPDATE_TYPE = "widget_query"
CHAT_DATA_LIMIT = 1024  # байт, лимит Telegram на chat_data
REQUEST_LIMIT = 64  # байт, лимит Telegram на данные запроса из виджета
REQUEST_RE = re.compile(r"^b:([\w-]{1,24}):([\w-]{1,24}):(\d{8}):(\d{1,4})$")


# ---------- методы Bot API 10.4 ----------


class SendWidget(TelegramMethod[Message]):
    __returning__ = Message
    __api_method__ = "sendWidget"

    chat_id: int
    html: str
    chat_data: str | None = None
    allow_queries: bool | None = None
    caption: str | None = None


class AnswerWidgetQuery(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "answerWidgetQuery"

    widget_query_id: str
    data: str | None = None


class EditMessageWidgetData(TelegramMethod[Any]):
    __returning__ = Any
    __api_method__ = "editMessageWidgetData"

    chat_id: int
    message_id: int
    chat_data: str


# ---------- данные календаря ----------

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def encode_slots(slots: list[datetime], tz) -> str:
    """Время начала → по 2 символа base36 (минуты от полуночи / 5). 10:00 → «3c»."""
    out = []
    for slot in slots:
        local = slot.astimezone(tz)
        n = (local.hour * 60 + local.minute) // 5
        out.append(_ALPHABET[n // 36] + _ALPHABET[n % 36])
    return "".join(out)


def decode_slots(encoded: str) -> list[int]:
    return [int(encoded[i : i + 2], 36) * 5 for i in range(0, len(encoded), 2)]


def available(service: Service, master_id: str) -> bool:
    """Поместится ли самый длинный запрос виджета в лимит Telegram (зависит от длины id)."""
    return bool(REQUEST_RE.match(f"b:{service.id}:{master_id}:20991231:1435")) and (
        len(f"b:{service.id}:{master_id}:20991231:1435".encode()) <= REQUEST_LIMIT
    )


def calendar_title(settings: Settings, service: Service, master_id: str) -> str:
    title = service.name
    if len(settings.catalog.masters) > 1:
        master = settings.catalog.master(master_id)
        title += " · " + (master.name if master else "любой мастер")
    return title


def build_chat_data(
    db: Database,
    settings: Settings,
    service: Service,
    master_id: str,
    now: datetime,
    *,
    selected: str | None = None,
) -> str:
    """JSON со свободным временем по дням. Укорачивается по дням, чтобы влезть в 1 КБ."""
    days = [
        [d.strftime("%Y%m%d"), encode_slots(slots_for(db, settings, service, master_id, d, now), settings.tz)]
        for d in days_with_slots(db, settings, service, master_id, now)
    ]
    title = calendar_title(settings, service, master_id)
    while True:
        payload = {"t": title, "s": service.id, "m": master_id, "d": days, "sel": selected}
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(raw.encode()) <= CHAT_DATA_LIMIT or not days:
            return raw
        days = days[:-1]


# ---------- HTML-шаблон (без сети и внешних ресурсов: так требует песочница Telegram) ----------

WIDGET_HTML = """<!doctype html><meta charset=utf-8><style>
:root{font:14px/1.3 system-ui,sans-serif;color:var(--tg-theme-text-color,#111);background:var(--tg-theme-bg-color,#fff)}
body{margin:0;padding:10px}h3{margin:0 0 8px;font-size:15px}
.r{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
button{border:0;border-radius:8px;padding:7px 9px;font:inherit;color:inherit;background:var(--tg-theme-secondary-bg-color,#eee)}
.s button{min-width:58px}button.on{background:var(--tg-theme-button-color,#2a8);color:var(--tg-theme-button-text-color,#fff)}
#m{color:var(--tg-theme-hint-color,#888);font-size:13px;min-height:18px}
</style><h3 id=t>Календарь записи</h3><div class=r id=d></div><div class="r s" id=s></div><div id=m></div>
<script>
const W=window.TelegramWidget,WD=['вс','пн','вт','ср','чт','пт','сб'],$=i=>document.getElementById(i);
let st=null,day=null,busy=false;
function b(t,c,f){const e=document.createElement('button');e.textContent=t;if(c)e.className=c;e.addEventListener('click',f);return e}
function msg(t){$('m').textContent=t||''}
function lbl(k){const d=new Date(Date.UTC(+k.slice(0,4),+k.slice(4,6)-1,+k.slice(6)));return WD[d.getUTCDay()]+' '+d.getUTCDate()}
function hm(x){return String(x/60|0).padStart(2,'0')+':'+String(x%60).padStart(2,'0')}
function slots(s){const r=[];for(let i=0;i<s.length;i+=2)r.push(parseInt(s.substr(i,2),36)*5);return r}
function render(){
 try{st=W&&W.chatData?JSON.parse(W.chatData):null}catch(e){st=null}
 $('d').textContent='';$('s').textContent='';
 if(!st){msg('Откройте календарь в Telegram');return}
 $('t').textContent=st.t;
 if(!st.d.length){msg('Свободного времени нет');return}
 if(!day)day=(st.sel||'').split(':')[0];
 if(!st.d.some(x=>x[0]===day))day=st.d[0][0];
 for(const x of st.d)$('d').append(b(lbl(x[0]),x[0]===day?'on':'',()=>{day=x[0];render()}));
 for(const x of slots(st.d.find(y=>y[0]===day)[1]))$('s').append(b(hm(x),st.sel===day+':'+x?'on':'',()=>pick(x)));
 msg(st.sel?'Время выбрано — напишите имя в чат 👇':'Выберите день и время');
}
function pick(x){
 if(!W||busy)return;busy=true;msg('Проверяю…');
 W.request('b:'+st.s+':'+st.m+':'+day+':'+x).then(a=>{busy=false;let r={};try{r=JSON.parse(a.result||'{}')}catch(e){}
  msg(r.msg||'');if(W.HapticFeedback)W.HapticFeedback.notificationOccurred(r.ok?'success':'error')},
 e=>{busy=false;msg(e&&e.code==='RATE_LIMITED'?'Слишком часто, подождите пару секунд':'Не получилось, попробуйте ещё раз')});
}
if(W)W.onEvent('chatDataChanged',()=>{const m=$('m').textContent;render();if(m&&!m.startsWith('Выберите'))msg(m)});
render();
</script>"""


# ---------- отправка ----------

# Telegram включает виджеты ботам поэтапно. Пока боту отвечают «не разрешено», кнопку календаря
# не показываем, чтобы клиенты не упирались в ошибку, и раз в RETRY_AFTER пробуем снова.
NOT_ALLOWED_ERROR = "INPUT_MEDIA_WIDGET_NOT_ALLOWED"
RETRY_AFTER = timedelta(hours=6)
_blocked_until: datetime | None = None


def blocked(now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return _blocked_until is not None and now < _blocked_until


def reset_block() -> None:
    global _blocked_until
    _blocked_until = None


async def send_calendar(
    bot: Bot, chat_id: int, db: Database, settings: Settings, service: Service, master_id: str
) -> Message:
    global _blocked_until
    chat_data = build_chat_data(db, settings, service, master_id, datetime.now(settings.tz))
    try:
        return await bot(
            SendWidget(chat_id=chat_id, html=WIDGET_HTML, chat_data=chat_data, allow_queries=True)
        )
    except TelegramAPIError as error:
        if NOT_ALLOWED_ERROR in str(error):
            _blocked_until = datetime.now(UTC) + RETRY_AFTER
            log.warning(
                "Telegram пока не разрешает этому боту виджеты (%s). Кнопка календаря скрыта до %s UTC",
                NOT_ALLOWED_ERROR, f"{_blocked_until:%Y-%m-%d %H:%M}",
            )
        else:
            log.warning("Не удалось отправить календарь-виджет: %s", error)
        raise


# ---------- обработка нажатий в виджете ----------


def parse_request(raw: str) -> tuple[str, str, date, int] | None:
    match = REQUEST_RE.match(raw or "")
    if not match:
        return None
    service_id, master_id, day_raw, minutes_raw = match.groups()
    try:
        day = datetime.strptime(day_raw, "%Y%m%d").date()
    except ValueError:
        return None
    minutes = int(minutes_raw)
    if not 0 <= minutes < 24 * 60:
        return None
    return service_id, master_id, day, minutes


async def handle_query(
    query: dict, bot: Bot, db: Database, settings: Settings, storage: BaseStorage
) -> dict:
    """Обрабатывает нажатие на время в виджете. Возвращает отправленный виджету ответ."""
    from booking_bot.handlers.client import BookingForm  # здесь, чтобы не было цикла импортов

    user_id = query["from"]["id"]  # проставляет Telegram, подделать нельзя
    chat_id = (query.get("chat") or {}).get("id", user_id)
    message_id = query.get("message_id")
    now = datetime.now(settings.tz)

    # data приходит от клиента — разбираем строго и всё перепроверяем
    parsed = parse_request(query.get("data", ""))
    service = settings.service(parsed[0]) if parsed else None
    if parsed is None or service is None or not service.active:
        return await _answer(bot, query["id"], {"ok": 0, "msg": "Календарь устарел — выберите услугу заново"})

    _, master_id, day, minutes = parsed
    start = datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=settings.tz)

    if not candidate_masters(settings, service, master_id) or not free_masters_at(
        db, settings, service, master_id, start, now
    ):
        answer = await _answer(
            bot, query["id"], {"ok": 0, "msg": "Это время уже заняли — календарь обновлён"}
        )
        await _refresh(bot, chat_id, message_id, db, settings, service, master_id, now, None)
        return answer

    # Время свободно: продолжаем обычный сценарий записи с шага «имя».
    state = FSMContext(storage=storage, key=StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id))
    await state.clear()
    await state.set_state(BookingForm.name)
    await state.update_data(service_id=service.id, master_id=master_id, ts=int(start.timestamp()))

    chosen = texts.fmt_dt(start, settings.tz)
    answer = await _answer(
        bot, query["id"], {"ok": 1, "msg": f"Выбрано: {chosen}. Напишите имя в чат 👇"}
    )
    await _refresh(bot, chat_id, message_id, db, settings, service, master_id, now, f"{day:%Y%m%d}:{minutes}")
    try:
        await bot.send_message(chat_id, "Как к вам обращаться? Напишите имя.")
    except TelegramAPIError:
        log.warning("Не удалось попросить имя у %s", user_id)
    return answer


async def _answer(bot: Bot, query_id: str, answer: dict) -> dict:
    try:
        await bot(AnswerWidgetQuery(widget_query_id=query_id, data=json.dumps(answer, ensure_ascii=False)))
    except TelegramAPIError:
        log.warning("Не удалось ответить виджету", exc_info=True)
    return answer


async def _refresh(
    bot: Bot, chat_id: int, message_id: int | None, db: Database, settings: Settings,
    service: Service, master_id: str, now: datetime, selected: str | None,
) -> None:
    if message_id is None:
        return
    chat_data = build_chat_data(db, settings, service, master_id, now, selected=selected)
    try:
        await bot(EditMessageWidgetData(chat_id=chat_id, message_id=message_id, chat_data=chat_data))
    except TelegramAPIError:
        # «message is not modified» и подобное записи не мешают.
        log.info("Календарь не обновлён", exc_info=True)


class WidgetQueryMiddleware(BaseMiddleware):
    """Перехватывает widget_query, который aiogram пока не умеет разбирать сам."""

    def __init__(self, storage: BaseStorage) -> None:
        self.storage = storage

    async def __call__(self, handler, event: Update, data: dict[str, Any]) -> Any:
        query = (event.model_extra or {}).get(UPDATE_TYPE)
        if query is None:
            return await handler(event, data)
        try:
            await handle_query(query, data["bot"], data["db"], data["settings"], self.storage)
        except Exception:
            log.exception("Ошибка обработки нажатия в виджете")
        return None


__all__ = ["ANY_MASTER", "UPDATE_TYPE", "WIDGET_HTML", "WidgetQueryMiddleware", "send_calendar"]
