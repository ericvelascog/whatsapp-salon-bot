# Edita este archivo con la información real del negocio

BUSINESS_INFO = {
    "nombre": "Barbería Eric",
    "descripcion": "Barbería de barrio para hombres, abierta a todo tipo de públicos. Cortes clásicos y modernos en un ambiente cercano y sin pretensiones.",
    "telefono": "+34 (931) 20 85 91",
    "direccion": "Carrer del Mar 8, Badalona",
    "como_llegar": "Consulta Google Maps para la ruta más conveniente.",
    "horario": {
        "lunes": "14:00 - 20:00",
        "martes": "14:00 - 20:00",
        "miércoles": "14:00 - 20:00",
        "jueves": "14:00 - 20:00",
        "viernes": "14:00 - 20:00",
        "sábado": "Cerrado",
        "domingo": "Cerrado",
    },
    "servicios": [
        {"nombre": "Corte Básico", "precio": "11,95€", "duracion_min": 30, "descripcion": "Corte de cabello estándar a máquina o tijera."},
        {"nombre": "Corte y Cejas", "precio": "15,00€", "duracion_min": 30, "descripcion": "Corte de cabello y perfilado de cejas."},
        {"nombre": "Corte y Barba", "precio": "20,00€", "duracion_min": 45, "descripcion": "Corte de cabello y arreglo de barba."},
    ],
    "politicas": {
        "cancelacion": "Las cancelaciones deben realizarse con al menos 24 horas de antelación.",
        "retraso": "Si llegas con más de 15 minutos de retraso, puede que no podamos atenderte y debamos reprogramar tu cita.",
        "pago": "Aceptamos efectivo y tarjeta de crédito/débito.",
        "reservas": "Las citas se reservan por WhatsApp. Para hablar con nuestro asistente de voz llama al +34 (931) 20 85 91.",
    },
}


def get_business_info_text() -> str:
    """Devuelve toda la info del negocio como texto estructurado para el system prompt."""
    b = BUSINESS_INFO
    servicios = "\n".join(
        f"  - {s['nombre']}: {s['precio']} (~{s['duracion_min']} min) — {s['descripcion']}"
        for s in b["servicios"]
    )
    horario = "\n".join(f"  - {dia}: {hora}" for dia, hora in b["horario"].items())
    politicas = "\n".join(f"  - {k}: {v}" for k, v in b["politicas"].items())

    return f"""
INFORMACIÓN DEL NEGOCIO:
Nombre: {b['nombre']}
Descripción: {b['descripcion']}
Teléfono: {b['telefono']}
Dirección: {b['direccion']}
Cómo llegar: {b['como_llegar']}

HORARIO:
{horario}

SERVICIOS Y PRECIOS:
{servicios}

POLÍTICAS:
{politicas}
""".strip()
