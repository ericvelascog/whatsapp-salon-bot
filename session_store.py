from collections import defaultdict

MAX_MESSAGES = 20

# {phone_number: [{"role": "user"|"assistant", "content": ...}]}
_sessions: dict[str, list[dict]] = defaultdict(list)


def get_history(phone: str) -> list[dict]:
    return _sessions[phone]


def add_message(phone: str, role: str, content) -> None:
    _sessions[phone].append({"role": role, "content": content})
    # Mantener solo los últimos MAX_MESSAGES para controlar tokens
    if len(_sessions[phone]) > MAX_MESSAGES:
        _sessions[phone] = _sessions[phone][-MAX_MESSAGES:]


def clear_session(phone: str) -> None:
    _sessions[phone] = []
