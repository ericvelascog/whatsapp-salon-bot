import os
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import settings
from knowledge_base import BUSINESS_INFO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TIMEZONE = "Europe/Madrid"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Horario del negocio por día (0=lunes … 6=domingo, None = cerrado)
BUSINESS_HOURS: dict[int, tuple[time, time] | None] = {
    0: (time(14, 0), time(20, 0)), # lunes
    1: (time(14, 0), time(20, 0)), # martes
    2: (time(14, 0), time(20, 0)), # miércoles
    3: (time(14, 0), time(20, 0)), # jueves
    4: (time(14, 0), time(20, 0)), # viernes
    5: None,                       # sábado
    6: None,                       # domingo
}

SLOT_DURATION = timedelta(minutes=30)


def _get_service():
    credentials_path = os.path.join(BASE_DIR, settings.google_credentials_json)
    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def _tz() -> ZoneInfo:
    return ZoneInfo(TIMEZONE)


def get_free_slots(target_date: date, duration_minutes: int = 30) -> list[str]:
    """Devuelve lista de horas disponibles (HH:MM) para una fecha dada."""
    hours = BUSINESS_HOURS.get(target_date.weekday())
    if not hours:
        return []

    service = _get_service()
    tz = _tz()

    day_start = datetime.combine(target_date, hours[0], tzinfo=tz)
    day_end = datetime.combine(target_date, hours[1], tzinfo=tz)

    body = {
        "timeMin": day_start.isoformat(),
        "timeMax": day_end.isoformat(),
        "timeZone": TIMEZONE,
        "items": [{"id": settings.google_calendar_id}],
    }
    freebusy = service.freebusy().query(body=body).execute()
    busy_periods = freebusy["calendars"][settings.google_calendar_id]["busy"]

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
) -> dict:
    """Crea una cita en Google Calendar. Devuelve el evento creado."""
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

    created = service_obj.events().insert(
        calendarId=settings.google_calendar_id, body=event
    ).execute()

    return {
        "id": created["id"],
        "summary": created["summary"],
        "start": created["start"]["dateTime"],
        "end": created["end"]["dateTime"],
        "link": created.get("htmlLink", ""),
    }


def list_client_appointments(client_phone: str) -> list[dict]:
    """Lista las citas futuras de un cliente por su número de teléfono."""
    service = _get_service()
    tz = _tz()
    now = datetime.now(tz).isoformat()

    events_result = service.events().list(
        calendarId=settings.google_calendar_id,
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


def cancel_appointment(event_id: str) -> bool:
    """Cancela (elimina) una cita por su ID. Devuelve True si tuvo éxito."""
    service = _get_service()
    try:
        service.events().delete(
            calendarId=settings.google_calendar_id, eventId=event_id
        ).execute()
        return True
    except Exception:
        return False
