"""
src/index.py
=============
Cálculo del Índice de Bienestar Urbano Personal (IBUP): combina exposición
ambiental (contaminación, ruido) y accesibilidad (deporte, carril bici,
zonas verdes) en un único score de 0 a 100, ponderable por el usuario.

Diseño del índice
------------------
Cada componente se normaliza a una escala 0-100 donde:
    100 = mejor situación posible (poca exposición / accesibilidad inmediata)
      0 = peor situación posible

Luego se combina con pesos que el usuario puede ajustar (por defecto, pesos
iguales). Esto hace el índice transparente y explicable: no es una caja
negra, cada componente se puede inspeccionar por separado.
"""

import numpy as np

# Valores de referencia para normalizar (basados en límites legales/OMS y en
# rangos típicos observados en Valencia; ajustables si calibras con más datos)
REFERENCE_RANGES = {
    "no2": {"bueno": 10, "malo": 40},       # ug/m3 (límite anual UE: 40)
    "pm10": {"bueno": 15, "malo": 50},      # ug/m3 (límite diario UE: 50)
    "pm25": {"bueno": 5, "malo": 25},       # ug/m3 (guía OMS 2021: 5 anual)
    "ruido_db": {"bueno": 45, "malo": 70},  # dB — NOTA: sin datos reales aún
    "tiempo_deporte_min": {"bueno": 5, "malo": 25},
    "tiempo_bici_min": {"bueno": 3, "malo": 20},
    "tiempo_verde_min": {"bueno": 3, "malo": 20},
}

# Pesos por defecto. 'ruido_db' se deja definido (peso 0) porque
# REFERENCE_RANGES lo soporta y en el futuro podría alimentarse con datos
# reales; compute_ibup() ignora y renormaliza automáticamente los
# componentes ausentes, así que omitirlo de raw_values ya basta — el peso
# 0 aquí es solo documentación de que, si llegara el dato, no se
# sobrerrepresentaría sin querer.
DEFAULT_WEIGHTS = {
    "no2": 0.25,
    "pm10": 0.15,
    "pm25": 0.10,
    "ruido_db": 0.0,
    "tiempo_deporte_min": 0.25,
    "tiempo_bici_min": 0.10,
    "tiempo_verde_min": 0.15,
}


def _normalize_inverse(value, bueno, malo):
    """
    Para variables donde MENOS es MEJOR (contaminación, ruido, tiempo de
    acceso). Devuelve 100 si value <= bueno, 0 si value >= malo, e
    interpola linealmente entre medio.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if value <= bueno:
        return 100.0
    if value >= malo:
        return 0.0
    return 100.0 * (malo - value) / (malo - bueno)


def compute_component_scores(raw_values: dict) -> dict:
    """
    raw_values: dict con claves de REFERENCE_RANGES y sus valores crudos,
    p.ej. {"no2": 28, "pm10": 22, "ruido_db": 61, "tiempo_deporte_min": 12,
           "tiempo_bici_min": 6, "tiempo_verde_min": 4}

    Devuelve el mismo dict pero con cada valor normalizado a 0-100.
    Las claves ausentes o con valor None se omiten (no entran en la media).
    """
    scores = {}
    for key, ranges in REFERENCE_RANGES.items():
        if key not in raw_values:
            continue
        scores[key] = _normalize_inverse(raw_values[key], ranges["bueno"], ranges["malo"])
    return scores


def compute_ibup(raw_values: dict, weights: dict = None) -> dict:
    """
    Calcula el Índice de Bienestar Urbano Personal (IBUP) final.

    Parameters
    ----------
    raw_values : dict
        Valores crudos (ver compute_component_scores).
    weights : dict or None
        Pesos por componente. Si None, usa DEFAULT_WEIGHTS. Los pesos se
        renormalizan automáticamente para que sumen 1 entre los componentes
        realmente disponibles (así si falta un dato, no penaliza injustamente).

    Returns
    -------
    dict con:
        "ibup": float (0-100, score final)
        "componentes": dict de scores individuales (0-100)
        "pesos_usados": dict de pesos efectivamente aplicados
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    scores = compute_component_scores(raw_values)
    scores_validos = {k: v for k, v in scores.items() if v is not None}

    if not scores_validos:
        return {"ibup": None, "componentes": scores, "pesos_usados": {}}

    pesos_validos = {k: weights.get(k, 0) for k in scores_validos}
    total_peso = sum(pesos_validos.values())
    if total_peso == 0:
        # si el usuario puso todos los pesos a 0 por error, repartir igual
        pesos_validos = {k: 1 / len(scores_validos) for k in scores_validos}
        total_peso = 1.0

    pesos_norm = {k: v / total_peso for k, v in pesos_validos.items()}

    ibup = sum(scores_validos[k] * pesos_norm[k] for k in scores_validos)

    return {
        "ibup": round(ibup, 1),
        "componentes": scores,
        "pesos_usados": pesos_norm,
    }


def ibup_label(ibup_value: float) -> str:
    """Traduce el score numérico a una etiqueta interpretable."""
    if ibup_value is None:
        return "Sin datos suficientes"
    if ibup_value >= 80:
        return "Excelente"
    if ibup_value >= 60:
        return "Bueno"
    if ibup_value >= 40:
        return "Regular"
    if ibup_value >= 20:
        return "Deficiente"
    return "Muy deficiente"
