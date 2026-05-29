import anthropic
from datetime import datetime
from zoneinfo import ZoneInfo
from config import settings
from knowledge_base import get_business_info_text
from tools import TOOLS, dispatch_tool
import session_store

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_SYSTEM_PROMPT_TEMPLATE = """Eres el asistente virtual de un salón de peluquería y estética. \
Tu nombre es Bella y eres amable, profesional y concisa.

Tus funciones son:
1. Gestionar reservas de citas: consultar disponibilidad, crear citas y cancelarlas.
2. Responder preguntas sobre el salón: horarios, ubicación y políticas.

REGLAS IMPORTANTES:
- Para crear una cita siempre necesitas: nombre completo del cliente, fecha y hora.
- Antes de crear una cita, consulta siempre la disponibilidad para esa fecha.
- Antes de cancelar una cita, muéstrale al cliente la cita encontrada y pide confirmación explícita.
- Si el cliente pide un día en que el salón está cerrado, indícaselo amablemente.
- Responde siempre en español, de forma breve y clara.
- Usa la fecha de hoy como referencia cuando el cliente diga "mañana", "el viernes", etc.
- La fecha y hora actual es: {now}

{business_info}
"""


def _build_system_prompt() -> str:
    now = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%A %d/%m/%Y %H:%M")
    return _SYSTEM_PROMPT_TEMPLATE.format(now=now, business_info=get_business_info_text())


def process_message(phone: str, user_text: str) -> str:
    """Procesa un mensaje del usuario y devuelve la respuesta del bot."""
    session_store.add_message(phone, "user", user_text)
    history = session_store.get_history(phone)

    response_text = _run_agent(history)

    session_store.add_message(phone, "assistant", response_text)
    return response_text


def _run_agent(messages: list[dict]) -> str:
    """Loop agentic: Claude → tool calls → resultados → respuesta final."""
    working_messages = list(messages)

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_build_system_prompt(),
            tools=TOOLS,
            messages=working_messages,
        )

        if response.stop_reason == "end_turn":
            return _extract_text(response)

        if response.stop_reason == "tool_use":
            # Añadir respuesta del asistente con las tool calls
            working_messages.append({"role": "assistant", "content": response.content})

            # Ejecutar cada tool y recoger resultados
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            working_messages.append({"role": "user", "content": tool_results})
            continue

        # stop_reason inesperado
        return _extract_text(response)


def _extract_text(response) -> str:
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return "Lo siento, no pude procesar tu mensaje. Inténtalo de nuevo."
