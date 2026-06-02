import os
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import settings
from business_config import BUSINESS_HOURS, BARBERS, calendar_for_barber

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TIMEZONE = "Europe/Madrid"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# El horario del negocio (BUSINESS_HOURS) se carga desde business_config.
# Paso de la rejilla de huecos (cada cuánto empieza un hueco posible).
SLOT_DURATION = timedelta(minutes=30)


def _get_service():
    import json
    credentials_content = os.environ.get("GOOGLE_CREDENTIALS_CONTENT")
    if credentials_content:
        # Railway: credenciales desde variable de entorno
        info = json.loads(credentials_content)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # Local: credenciales desde archivo
        credentials_path = os.path.join(BASE_DIR, settings.google_credentials_json)
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES
        )
    return build("calendar", "v3", credentials=creds)


def _tz() -> ZoneInfo:
    return ZoneInfo(TIMEZONE)


def _all_calendars() -> list[tuple]:
    """Devuelve [(nombre_barbero, calendar_id), ...].

    Si hay barberos configurados, uno por barbero; si no, un único calendario
    (el de la variable GOOGLE_CALENDAR_ID), con nombre None.
    """
    if BARBERS:
        return [(b.get("nombre"), b["calendar_id"]) for b in BARBERS if b.get("calendar_id")]
    return [(None, settings.google_calendar_id)]


# ---------------------------------------------------------------- nivel base
def get_free_slots(target_date: date, duration_minutes: int = 30, calendar_id: str | None = None) -> list[str]:
    """Devuelve lista de horas disponibles (HH:MM) para una fecha y un calendario."""
    hours = BUSINESS_HOURS.get(target_date.weekday())
    if not hours:
        return []

    cid = calendar_id or settings.google_calendar_id
    service = _get_service()
    tz = _tz()

    day_start = datetime.combine(target_date, hours[0], tzinfo=tz)
    day_end = datetime.combine(target_date, hours[1], tzinfo=tz)

    body = {
        "timeMin": day_start.isoformat(),
        "timeMax": day_end.isoformat(),
        "timeZone": TIMEZONE,
        "items": [{"id": cid}],
    }
    freebusy = service.freebusy().query(body=body).execute()
    busy_periods = freebusy["calendars"][cid]["busy"]

    busy_ranges = [
        (datetime.fromisoformat(p["start"]), datetime.fromisoformat(p["end"]))
        for p in busy_periods
    ]

    service_duration = timedelta(minutes=duration_minutes)
    free_slots = []
    slot = day_start
    while slot + service_duration <= day_end:
        slot_end = slot + service_duration
        if not any(s < slot_end and e > slot for s, e in busy_ranges):
            free_slots.append(slot.strftime("%H:%M"))
        slot += SLOT_DURATION

    return free_slots


def create_appointment(
    client_name: str,
    client_phone: str,
    service: str,
    target_date: date,
    start_time: time,
    duration_minutes: int = 60,
    calendar_id: str | None = None,
) -> dict:
    """Crea una cita en el calendario indicado. Devuelve el evento creado."""
    cid = calendar_id or settings.google_calendar_id
    service_obj = _get_service()
    tz = _tz()

    start_dt = datetime.combine(target_date, start_time, tzinfo=tz)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    event = {
        "summary": f"{service} - {client_name} - {client_phone}",
        "description": f"Cliente: {client_name}\nTeléfono: {client_phone}\nServicio: {service}",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
    }

    created = service_obj.events().insert(calendarId=cid, body=event).execute()

    return {
        "id": created["id"],
        "summary": created["summary"],
        "start": created["start"]["dateTime"],
        "end": created["end"]["dateTime"],
        "link": created.get("htmlLink", ""),
    }


def list_client_appointments(client_phone: str, calendar_id: str | None = None) -> list[dict]:
    """Lista las citas futuras de un cliente por su teléfono, en un calendario."""
    cid = calendar_id or settings.google_calendar_id
    service = _get_service()
    tz = _tz()
    now = datetime.now(tz).isoformat()

    events_result = service.events().list(
        calendarId=cid,
        timeMin=now,
        maxResults=10,
        singleEvents=True,
        orderBy="startTime",
        q=client_phone,
    ).execute()

    events = events_result.get("items", [])
    return [
        {
            "id": e["id"],
            "summary": e.get("summary", ""),
            "start": e["start"].get("dateTime", e["start"].get("date")),
        }
        for e in events
    ]


def cancel_appointment(event_id: str, calendar_id: str | None = None) -> bool:
    """Cancela (elimina) una cita por su ID en un calendario. True si tuvo éxito."""
    cid = calendar_id or settings.google_calendar_id
    service = _get_service()
    try:
        service.events().delete(calendarId=cid, eventId=event_id).execute()
        return True
    except Exception:
        return False


# ---------------------------------------------------------- nivel multi-barbero
def get_free_slots_multi(target_date: date, duration_minutes: int = 30, barber_name: str | None = None) -> list[str]:
    """Huecos del barbero indicado, o la UNIÓN de todos si no se especifica."""
    if barber_name:
        cid = calendar_for_barber(barber_name) or settings.google_calendar_id
        return get_free_slots(target_date, duration_minutes, cid)

    all_slots: set[str] = set()
    for _, cid in _all_calendars():
        all_slots.update(get_free_slots(target_date, duration_minutes, cid))
    return sorted(all_slots)


def book(
    client_name: str,
    client_phone: str,
    service: str,
    target_date: date,
    start_time: time,
    duration_minutes: int = 30,
    barber_name: str | None = None,
) -> tuple[dict, str | None]:
    """Reserva con el barbero indicado o asigna uno libre. Devuelve (evento, barbero_asignado)."""
    cals = _all_calendars()

    if barber_name:
        cid = calendar_for_barber(barber_name) or settings.google_calendar_id
        assigned = barber_name
    elif len(cals) == 1:
        assigned, cid = cals[0]
    else:
        # Asignar al primer barbero libre a esa hora
        slot_str = start_time.strftime("%H:%M")
        assigned, cid = None, None
        for name, c in cals:
            if slot_str in get_free_slots(target_date, duration_minutes, c):
                assigned, cid = name, c
                break
        if cid is None:  # nadie libre: usar el primero (caso límite)
            assigned, cid = cals[0]

    event = create_appointment(
        client_name, client_phone, service, target_date, start_time, duration_minutes, cid
    )
    return event, assigned


def list_client_appointments_multi(client_phone: str) -> list[dict]:
    """Lista las citas del cliente en TODOS los calendarios (con el barbero)."""
    out = []
    for name, cid in _all_calendars():
        for a in list_client_appointments(client_phone, cid):
            a["barbero"] = name
            out.append(a)
    return out


def cancel_appointment_multi(event_id: str) -> bool:
    """Cancela una cita buscándola en TODOS los calendarios."""
    for _, cid in _all_calendars():
        if cancel_appointment(event_id, cid):
            return True
    return False
