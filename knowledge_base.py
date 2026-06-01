# La información del negocio ya NO está aquí: vive en business_config.py
# (variable de entorno BUSINESS_CONFIG o archivo business_config.json).
from business_config import CONFIG

# Alias de compatibilidad por si algún módulo todavía lo importa.
BUSINESS_INFO = CONFIG


def get_business_info_text() -> str:
    """Devuelve toda la info del negocio como texto estructurado para el system prompt."""
    b = CONFIG
    horario = "\n".join(f"  - {dia}: {hora}" for dia, hora in b.get("horario", {}).items())
    politicas = "\n".join(f"  - {k}: {v}" for k, v in b.get("politicas", {}).items())

    # Bloque de servicios y precios (solo si el negocio los tiene configurados).
    servicios_block = ""
    servicios = b.get("servicios", []) or []
    if servicios:
        lineas = []
        for s in servicios:
            linea = f"  - {s.get('nombre', '')}: {s.get('precio', '')}".rstrip()
            if s.get("duracion_min"):
                linea += f" (~{s['duracion_min']} min)"
            if s.get("descripcion"):
                linea += f" — {s['descripcion']}"
            lineas.append(linea)
        servicios_block = "\n\nSERVICIOS Y PRECIOS:\n" + "\n".join(lineas)

    return f"""
INFORMACIÓN DEL NEGOCIO:
Nombre: {b.get('nombre', '')}
Descripción: {b.get('descripcion', '')}
Teléfono: {b.get('telefono', '')}
Dirección: {b.get('direccion', '')}
Cómo llegar: {b.get('como_llegar', '')}

HORARIO:
{horario}{servicios_block}

POLÍTICAS:
{politicas}
""".strip()
