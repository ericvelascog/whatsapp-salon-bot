from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import calendar_service
from business_config import (
    APPOINTMENT_DURATION_MIN as APPOINTMENT_DURATION,
    BUSINESS_HOURS,
    HAS_SERVICES,
    duration_for_service,
    MULTI_PROFESSIONAL,
)

TIMEZONE = ZoneInfo("Europe/Madrid")

_DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _parse_vapi_datetime(dt_str: str) -> tuple[date, time]:
    """Parsea 'YYYY/MM/DD HH:MM' de VAPI a date y time."""
    dt = datetime.strptime(dt_str.strip(), "%Y/%m/%d %H:%M")
    return dt.date(), dt.time()


def _duration(service_type: str) -> int:
    """Duración según el servicio (si la clínica los distingue) o la duración por defecto."""
    if HAS_SERVICES and service_type:
        return duration_for_service(service_type)
    return APPOINTMENT_DURATION


def _professional_arg(args: dict) -> str | None:
    """Lee el profesional del payload de VAPI ('professional', con fallback al antiguo 'barber')."""
    if not MULTI_PROFESSIONAL:
        return None
    value = (args.get("professional") or args.get("barber") or "").strip()
    return value or None


def handle_check_availability(args: dict) -> str:
    """
    Devuelve los huecos libres del día ya calculados.
    El LLM solo tiene que leerlos, sin hacer aritmética.
    """
    try:
        preferred_dt = args.get("preferredDateTime", "")
        target_date, req_time = _parse_vapi_datetime(preferred_dt)

        duration = _duration(args.get("serviceType", ""))
        professional = _professional_arg(args)
        free_slots = calendar_service.get_free_slots_multi(target_date, duration, professional)

        if not free_slots:
            # El horario sale de la configuración de la clínica, no está hardcodeado:
            # si ese día de la semana no tiene horario, está cerrado.
            if BUSINESS_HOURS.get(target_date.weekday()) is None:
                day_name = _DAY_NAMES[target_date.weekday()]
                return f"El {day_name} la clínica está cerrada. ¿Te viene bien otro día?"
            return "Lo siento, ese día no hay huecos disponibles. ¿Te viene bien otro día?"

        slots_text = ", ".join(free_slots)
        return f"Huecos disponibles: {slots_text}"

    except Exception as e:
        import traceback
        print(f"ERROR vapi check_availability: {traceback.format_exc()}")
        return f"Error al consultar disponibilidad: {str(e)}"


def handle_book_appointment(args: dict) -> str:
    try:
        name = args.get("name", "").strip()
        phone = args.get("phone", "").strip()
        service_type = args.get("serviceType", "").strip()
        preferred_dt = args.get("preferredDateTime", "")
        professional = _professional_arg(args)
        reason = (args.get("reason") or args.get("motivo") or "").strip()

        target_date, start_time = _parse_vapi_datetime(preferred_dt)

        duration = _duration(service_type)
        service_label = service_type if (HAS_SERVICES and service_type) else "Cita"

        event, assigned = calendar_service.book(
            client_name=name,
            client_phone=phone,
            service=service_label,
            target_date=target_date,
            start_time=start_time,
            duration_minutes=duration,
            professional_name=professional,
            reason=reason,
        )

        dt = datetime.fromisoformat(event["start"]).astimezone(TIMEZONE)
        con_profesional = f" con {assigned}" if (MULTI_PROFESSIONAL and assigned) else ""
        return (
            f"Cita confirmada. "
            f"{service_label} para {name}{con_profesional} el {dt.strftime('%d/%m/%Y')} a las {dt.strftime('%H:%M')}. "
            f"Teléfono registrado: {phone}."
        )

    except ValueError as e:
        # Hueco ya ocupado: el asistente de voz ofrece las alternativas.
        return str(e)
    except Exception as e:
        import traceback
        print(f"ERROR vapi book_appointment: {traceback.format_exc()}")
        return f"Error al crear la cita: {str(e)}"


def handle_cancel_appointment(args: dict) -> str:
    try:
        phone = args.get("phone", "").strip()

        appointments = calendar_service.list_client_appointments_multi(phone)

        if not appointments:
            return "No se encontró ninguna cita asociada a ese teléfono."

        # Cancelar la primera cita encontrada (la más próxima)
        event_id = appointments[0]["id"]
        summary = appointments[0]["summary"]
        success = calendar_service.cancel_appointment_multi(event_id)

        if success:
            return f"Cita cancelada correctamente: {summary}."
        else:
            return "No se pudo cancelar la cita. Por favor, inténtalo de nuevo."

    except Exception as e:
        import traceback
        print(f"ERROR vapi cancel_appointment: {traceback.format_exc()}")
        return f"Error al cancelar la cita: {str(e)}"


HANDLERS = {
    "checkAvailability": handle_check_availability,
    "bookAppointment": handle_book_appointment,
    "cancelAppointment": handle_cancel_appointment,
}


def process_vapi_request(body: dict) -> dict:
    """Punto de entrada principal. Procesa el payload de VAPI y devuelve la respuesta."""
    try:
        tool_calls = body.get("message", {}).get("toolCallList", [])

        if not tool_calls:
            # Algunos eventos de VAPI no son tool calls (status updates, etc.)
            return {}

        results = []
        for call in tool_calls:
            call_id = call.get("id", "")
            function_name = call.get("function", {}).get("name", "")
            arguments = call.get("function", {}).get("arguments", {})

            # Arguments puede venir como string JSON o como dict
            if isinstance(arguments, str):
                import json
                arguments = json.loads(arguments)

            handler = HANDLERS.get(function_name)
            if handler:
                result_text = handler(arguments)
            else:
                result_text = f"Función desconocida: {function_name}"

            results.append({"toolCallId": call_id, "result": result_text})

        return {"results": results}

    except Exception as e:
        import traceback
        print(f"ERROR procesando request VAPI: {traceback.format_exc()}")
        return {"results": []}
