from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import calendar_service

TIMEZONE = ZoneInfo("Europe/Madrid")

APPOINTMENT_DURATION = 30


def _parse_vapi_datetime(dt_str: str) -> tuple[date, time]:
    """Parsea 'YYYY/MM/DD HH:MM' de VAPI a date y time."""
    dt = datetime.strptime(dt_str.strip(), "%Y/%m/%d %H:%M")
    return dt.date(), dt.time()


def handle_check_availability(args: dict) -> str:
    """
    Devuelve los huecos libres del día ya calculados.
    El LLM solo tiene que leerlos, sin hacer aritmética.
    """
    try:
        preferred_dt = args.get("preferredDateTime", "")
        target_date, req_time = _parse_vapi_datetime(preferred_dt)

        free_slots = calendar_service.get_free_slots(target_date, APPOINTMENT_DURATION)

        if not free_slots:
            day_name = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][target_date.weekday()]
            if target_date.weekday() >= 5:
                return f"El {day_name} está cerrado. El salón abre de lunes a viernes de 14:00 a 20:00."
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
        preferred_dt = args.get("preferredDateTime", "")

        target_date, start_time = _parse_vapi_datetime(preferred_dt)

        event = calendar_service.create_appointment(
            client_name=name,
            client_phone=phone,
            service="Cita",
            target_date=target_date,
            start_time=start_time,
            duration_minutes=APPOINTMENT_DURATION,
        )

        dt = datetime.fromisoformat(event["start"]).astimezone(TIMEZONE)
        return (
            f"Cita confirmada. "
            f"Cita para {name} el {dt.strftime('%d/%m/%Y')} a las {dt.strftime('%H:%M')}. "
            f"Teléfono registrado: {phone}."
        )

    except Exception as e:
        import traceback
        print(f"ERROR vapi book_appointment: {traceback.format_exc()}")
        return f"Error al crear la cita: {str(e)}"


def handle_cancel_appointment(args: dict) -> str:
    try:
        phone = args.get("phone", "").strip()

        appointments = calendar_service.list_client_appointments(phone)

        if not appointments:
            return "No se encontró ninguna cita asociada a ese teléfono."

        # Cancelar la primera cita encontrada (la más próxima)
        event_id = appointments[0]["id"]
        summary = appointments[0]["summary"]
        success = calendar_service.cancel_appointment(event_id)

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
