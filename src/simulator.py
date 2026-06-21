"""
src/simulator.py
==================
Simula el efecto de añadir una mejora de infraestructura (carril bici,
árbol/zona verde, instalación deportiva) cerca de un punto, y recalcula el
Índice de Bienestar Urbano Personal (IBUP) antes y después.

Importante (honestidad metodológica): esto NO predice si el ayuntamiento
construirá algo, ni modela tráfico real tras la obra. Es una estimación de
"si este punto existiera ahí, así cambiaría tu accesibilidad/exposición
estimada" — útil como evidencia cuantificada para argumentar una petición,
no como promesa de impacto exacto. Esto se explica también en el informe
generado por report.py.
"""

from src.index import compute_ibup
from src.accessibility import walking_time_to_nearest

MEJORA_TIPOS = {
    "carril_bici": {
        "nombre": "Carril bici nuevo",
        "afecta_a": "tiempo_bici_min",
    },
    "instalacion_deportiva": {
        "nombre": "Instalación deportiva nueva",
        "afecta_a": "tiempo_deporte_min",
    },
    "arbolado": {
        "nombre": "Arbolado / zona verde nueva",
        "afecta_a": "tiempo_verde_min",
    },
}


def simulate_improvement(
    lat,
    lon,
    tipo_mejora,
    punto_mejora,
    raw_values_actuales,
    carril_bici_points,
    deporte_points,
    verde_points,
    weights=None,
):
    """
    Parameters
    ----------
    lat, lon : coordenadas del piso/punto del usuario (no de la mejora)
    tipo_mejora : str, una de las claves de MEJORA_TIPOS
    punto_mejora : dict {"lat": .., "lon": ..} — dónde se simula la mejora
    raw_values_actuales : dict — perfil ambiental/accesibilidad ANTES,
        tal como lo devuelven interpolation.py y accessibility.py combinados
    carril_bici_points, deporte_points, verde_points : list of dict
        Listas actuales de infraestructura (se les añade el punto simulado
        a la lista correspondiente para recalcular el "después")
    weights : dict opcional de pesos del IBUP

    Returns
    -------
    dict con "antes", "despues", "diferencia_ibup", "diferencia_componentes"
    """
    if tipo_mejora not in MEJORA_TIPOS:
        raise ValueError(f"tipo_mejora debe ser una de {list(MEJORA_TIPOS.keys())}")

    info_mejora = MEJORA_TIPOS[tipo_mejora]
    campo_afectado = info_mejora["afecta_a"]

    resultado_antes = compute_ibup(raw_values_actuales, weights)

    # Construir la lista "después": añadimos el punto simulado a la capa que toque
    nuevo_punto = {"lat": punto_mejora["lat"], "lon": punto_mejora["lon"], "nombre": info_mejora["nombre"]}

    if tipo_mejora == "carril_bici":
        puntos_despues = carril_bici_points + [nuevo_punto]
        resultado_acceso = walking_time_to_nearest(lat, lon, puntos_despues)
    elif tipo_mejora == "instalacion_deportiva":
        puntos_despues = deporte_points + [nuevo_punto]
        resultado_acceso = walking_time_to_nearest(lat, lon, puntos_despues)
    else:  # arbolado
        puntos_despues = verde_points + [nuevo_punto]
        resultado_acceso = walking_time_to_nearest(lat, lon, puntos_despues)

    raw_values_despues = dict(raw_values_actuales)
    if resultado_acceso is not None:
        raw_values_despues[campo_afectado] = resultado_acceso["minutos"]

    resultado_despues = compute_ibup(raw_values_despues, weights)

    diff_ibup = None
    if resultado_antes["ibup"] is not None and resultado_despues["ibup"] is not None:
        diff_ibup = round(resultado_despues["ibup"] - resultado_antes["ibup"], 1)

    diff_componentes = {}
    for k in resultado_despues["componentes"]:
        v_antes = resultado_antes["componentes"].get(k)
        v_despues = resultado_despues["componentes"].get(k)
        if v_antes is not None and v_despues is not None:
            diff_componentes[k] = round(v_despues - v_antes, 1)

    return {
        "tipo_mejora": info_mejora["nombre"],
        "antes": resultado_antes,
        "despues": resultado_despues,
        "diferencia_ibup": diff_ibup,
        "diferencia_componentes": diff_componentes,
        "raw_antes": raw_values_actuales,
        "raw_despues": raw_values_despues,
    }
