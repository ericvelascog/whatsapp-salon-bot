import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import anthropic
from config import settings
from tools import TOOLS, dispatch_tool

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _inject_date(system_prompt: str) -> str:
    """Reemplaza {{now}} o inyecta la fecha actual si no está ya."""
    now = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%A %d/%m/%Y %H:%M")
    if "{{now}}" in system_prompt:
        return system_prompt.replace("{{now}}", now)
    return system_prompt + f"\n\nFecha y hora actual: {now}"


def _openai_to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Convierte mensajes OpenAI a formato Anthropic.
    Devuelve (system_prompt, messages_list).
    """
    system_prompt = ""
    anthropic_messages = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        if role == "system":
            system_prompt += content + "\n"
        elif role in ("user", "assistant"):
            anthropic_messages.append({"role": role, "content": content})

    return _inject_date(system_prompt.strip()), anthropic_messages


def _run_agentic_loop(system: str, messages: list[dict]) -> str:
    """Ejecuta el loop Claude + tools y devuelve el texto final."""
    working_messages = list(messages)

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=working_messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            working_messages.append({"role": "assistant", "content": response.content})

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
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""


def build_streaming_response(text: str, model: str = "claude-sonnet-4-6"):
    """
    Genera chunks SSE en formato OpenAI para enviar a VAPI.
    Emite el texto en un único chunk y cierra con [DONE].
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(datetime.now().timestamp())

    # Chunk con el contenido
    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": text},
            "finish_reason": None,
        }],
    }
    yield f"data: {json.dumps(chunk)}\n\n"

    # Chunk de cierre
    closing = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop",
        }],
    }
    yield f"data: {json.dumps(closing)}\n\n"
    yield "data: [DONE]\n\n"


def build_non_streaming_response(text: str, model: str = "claude-sonnet-4-6") -> dict:
    """Respuesta OpenAI estándar (no streaming)."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
