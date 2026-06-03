import anthropic
from datetime import datetime
from zoneinfo import ZoneInfo
from config import settings
from business_config import CONFIG, IS_DEMO, HAS_SERVICES, MULTI_BARBER, BARBER_NAMES
from knowledge_base import get_business_info_text
from tools import TOOLS, dispatch_tool
import session_store

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_BASE_TEMPLATE = """Eres el asistente virtual de {negocio}. \
Tu nombre es {asistente} y eres {tono}.

Tus funciones son:
1. Gestionar reservas de citas: consultar disponibilidad, crear citas y cancelarlas.
2. Responder preguntas sobre el negocio: horarios, ubicación, servicios y políticas.

REGLAS IMPORTANTES:
- {crear_necesitas}{servicios_rule}{barberos_rule}
- Antes de crear una cita, consulta siempre la disponibilidad para esa fecha.
- Antes de cancelar una cita, muéstrale al cliente la cita encontrada y pide confirmación explícita.
- Si el cliente pide un día en que el negocio está cerrado, indícaselo amablemente.
- Responde siempre en español, de forma breve y clara.
- Usa la fecha de hoy como referencia cuando el cliente diga "mañana", "el viernes", etc.
- La fecha y hora actual es: {now}
"""

# Bloque que SOLO se añade cuando el bot está en modo demostración (demo: true).
_DEMO_BLOCK = """
CONTEXTO IMPORTANTE — ESTE ES UN ASISTENTE DE DEMOSTRACIÓN:
Eres una demostración creada por {comercial} para enseñar rápidamente a negocios cómo funciona un sistema de reservas automático. Lo que se ve aquí es una demo simplificada; el producto final es bastante más detallado y se adapta por completo a cada negocio. Algunas personas que hablan contigo son dueños de negocios evaluando el producto. Sigue estas reglas:

- REGLA DE ORO: NUNCA des ninguna información como 100% segura ni cerrada (ni precios, ni condiciones, ni plazos). Preséntala SIEMPRE como orientativa y diles que lo confirmen directamente con {comercial}.

- Si te preguntan por los TIPOS DE SERVICIO o los PRECIOS: explica que esto es una demo simplificada sin servicios concretos configurados, pero que el producto real es TOTALMENTE personalizable: se puede definir cada servicio (cortes, tintes, mechas, lavados, etc.) con su propia duración, su precio y lo que se le pide al cliente, de forma que cada cita se ajusta a lo que dura ese servicio.

- Si te preguntan si funciona con VARIOS BARBEROS: sí, sin ningún problema. Cada barbero puede tener su propia agenda; el cliente puede pedir a su barbero de siempre o dejar que se le asigne uno libre.

- Tranquiliza siempre con dos cosas: (1) el dueño NO toca nada técnico (los clientes escriben o llaman y se reserva solo), y (2) se integra con su Google Calendar, sin cambiar su forma de trabajar.

- Si te preguntan sobre el PRODUCTO en sí (cuánto cuesta, cómo conseguirlo, quién lo ha creado, si pueden tenerlo para su negocio): explica que eres una demo creada por {comercial} y da una orientación de los planes (SIEMPRE como orientativo, a confirmar con {comercial}): Plan WhatsApp, desde unos 149€ de alta y 39€/mes; Plan Solo Llamada (asistente de voz por teléfono), desde unos 199€ de alta y 59€/mes; y Plan Completo (WhatsApp + voz), desde unos 259€ de alta y 79€/mes. Todos incluyen mantenimiento, cambios de precios y servicios, y ayuda con la adopción. Añade que los precios dependen del volumen del negocio y que, además, si están entre los primeros clientes de {comercial}, podría salirles GRATIS, pero que eso lo tienen que consultar con él. Para cualquier cosa, que hablen directamente con {comercial} escribiéndole al {tel_comercial}.

- IMPORTANTE: después de confirmar una reserva con éxito, añade SIEMPRE al final de tu mensaje, en una línea aparte y entre paréntesis: "(Esto es solo una demo; el producto real se adapta a tu negocio. Si te ha gustado, escríbele a {comercial} al {tel_comercial} 👍)"
"""


def _build_system_prompt() -> str:
    now = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%A %d/%m/%Y %H:%M")
    asistente = CONFIG.get("asistente", {}) or {}

    if HAS_SERVICES:
        crear_necesitas = "Para crear una cita necesitas: nombre completo del cliente, servicio, fecha y hora."
        servicios_rule = (
            "\n- IMPORTANTE: este negocio tiene varios servicios con distinta duración. "
            "Pregunta SIEMPRE qué servicio quiere el cliente ANTES de consultar la disponibilidad, "
            "ya que los huecos disponibles dependen de la duración del servicio elegido."
        )
    else:
        crear_necesitas = "Para crear una cita siempre necesitas: nombre completo del cliente, fecha y hora."
        servicios_rule = ""

    if MULTI_BARBER:
        barberos_rule = (
            "\n- Este negocio tiene varios barberos: " + ", ".join(BARBER_NAMES) + ". "
            "Pregunta SIEMPRE al cliente si quiere uno concreto o le da igual. "
            "Si elige uno, pásalo al consultar disponibilidad y al crear la cita; si le da igual, "
            "no especifiques barbero y el sistema asignará uno libre. "
            "Cuando confirmes la reserva, dile con qué barbero ha quedado."
        )
    else:
        barberos_rule = ""

    prompt = _BASE_TEMPLATE.format(
        negocio=CONFIG.get("nombre", "un negocio"),
        asistente=asistente.get("nombre", "el asistente"),
        tono=asistente.get("tono", "amable y profesional"),
        crear_necesitas=crear_necesitas,
        servicios_rule=servicios_rule,
        barberos_rule=barberos_rule,
        now=now,
    )

    if IS_DEMO:
        comercial = CONFIG.get("contacto_comercial", {}) or {}
        prompt += _DEMO_BLOCK.format(
            comercial=comercial.get("nombre", "el creador"),
            tel_comercial=comercial.get("telefono", ""),
        )

    prompt += "\n\n" + get_business_info_text() + "\n"
    return prompt


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
