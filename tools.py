from datetime import date, time, datetime
import calendar_service

# Schemas de tools para Claude
TOOLS = [
    {
        "name": "check_availability",
        "description": (
            "Consulta los horarios disponibles para reservar una cita en una fecha concreta. "
            "Úsala antes de crear una cita para mostrar al cliente las horas libres."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD",
                },
                "service_type": {
                    "type": "string",
                    "description": "Tipo de servicio: 'Corte Básico', 'Corte y Cejas' o 'Corte y Barba'",
                },
            },
            "required": ["date", "service_type"],
        },
    },
    {
        "name": "create_appointment",
        "description": (
            "Crea una cita en el calendario del salón. "
            "Úsala solo cuando el cliente haya confirmado nombre, servicio, fecha y hora."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Nombre completo del cliente"},
                "client_phone": {"type": "string", "description": "Número de WhatsApp del cliente"},
                "service": {"type": "string", "description": "Nombre del servicio (ej: Corte de pelo)"},
                "date": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                "time": {"type": "string", "description": "Hora en formato HH:MM"},
                "duration_minutes": {
                    "type": "integer",
                    "description": "Duración estimada en minutos (por defecto 60)",
                },
            },
            "required": ["client_name", "client_phone", "service", "date", "time"],
        },
    },
    {
        "name": "list_client_appointments",
        "description": "Lista las próximas citas de un cliente buscando por su número de teléfono.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_phone": {"type": "string", "description": "Número de WhatsApp del cliente"}
            },
            "required": ["client_phone"],
        },
    },
    {
        "name": "cancel_appointment",
        "description": (
            "Cancela una cita existente. Primero usa list_client_appointments para obtener el ID, "
            "muéstrale la cita al cliente y pide confirmación antes de cancelar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "ID del evento de Google Calendar"}
            },
            "required": ["event_id"],
        },
    },
]


def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Ejecuta la tool correspondiente y devuelve el resultado como string."""
    try:
        if tool_name == "check_availability":
            target = date.fromisoformat(tool_input["date"])
            service_type = tool_input.get("service_type", "Corte Básico").lower().strip()
            duration = 45 if "barba" in service_type else 30
            slots = calendar_service.get_free_slots(target, duration)
            if not slots:
                return f"No hay disponibilidad el {target.strftime('%A %d/%m/%Y')} (día cerrado o sin huecos libres)."
            return f"Horas disponibles el {target.strftime('%A %d/%m/%Y')}: {', '.join(slots)}"

        elif tool_name == "create_appointment":
            target_date = date.fromisoformat(tool_input["date"])
            start_time = time.fromisoformat(tool_input["time"])
            if "duration_minutes" in tool_input:
                duration = tool_input["duration_minutes"]
            else:
                service_lower = tool_input.get("service", "").lower().strip()
                duration = 45 if "barba" in service_lower else 30
            event = calendar_service.create_appointment(
                client_name=tool_input["client_name"],
                client_phone=tool_input["client_phone"],
                service=tool_input["service"],
                target_date=target_date,
                start_time=start_time,
                duration_minutes=duration,
            )
            dt = datetime.fromisoformat(event["start"])
            return (
                f"Cita creada correctamente.\n"
                f"Servicio: {event['summary']}\n"
                f"Fecha y hora: {dt.strftime('%A %d/%m/%Y a las %H:%M')}\n"
                f"ID de la cita: {event['id']}"
            )

        elif tool_name == "list_client_appointments":
            appointments = calendar_service.list_client_appointments(tool_input["client_phone"])
            if not appointments:
                return "No se encontraron citas próximas para este cliente."
            lines = []
            for a in appointments:
                dt = datetime.fromisoformat(a["start"])
                lines.append(f"- {a['summary']} | {dt.strftime('%d/%m/%Y %H:%M')} | ID: {a['id']}")
            return "Próximas citas:\n" + "\n".join(lines)

        elif tool_name == "cancel_appointment":
            success = calendar_service.cancel_appointment(tool_input["event_id"])
            return "Cita cancelada correctamente." if success else "No se pudo cancelar la cita. Verifica el ID."

        else:
            return f"Tool desconocida: {tool_name}"

    except Exception as e:
        import traceback
        print(f"ERROR en tool {tool_name}: {traceback.format_exc()}")
        return f"Error ejecutando {tool_name}: {str(e)}"
