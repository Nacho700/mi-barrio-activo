"""
src/noise_inference.py
========================
Infiere un nivel de ruido aproximado (en dB) a partir de la intensidad de
tráfico real (IMV — Intensidad Media de Vehículos) en los tramos de calle
más cercanos a un punto.

¿Por qué inferir en vez de medir directamente?
El dataset de estaciones de ruido de Valencia (4 estaciones) solo da
ubicación, sin valores en dB accesibles de forma simple. En cambio, sí hay
un dataset de tráfico por tramo de calle con cobertura mucho mayor
(cientos de tramos en toda la ciudad). El tráfico rodado es la fuente
dominante de ruido urbano (más del 80% del ruido ambiental en ciudades,
según la OMS), así que usar IMV como proxy es una aproximación razonable
y mucho más rica espacialmente que las 4 estaciones de ruido.

Metodología (transparente, no es una caja negra):
1. Se localiza el tramo de calle más cercano al punto (línea, no punto).
2. Se convierte su IMV (vehículos/día) a un nivel de ruido aproximado
   usando una relación logarítmica estándar en acústica de tráfico:
   Lden ≈ a + b * log10(IMV), calibrada con valores de referencia típicos
   de literatura de ruido de tráfico urbano (no es una medición certificada,
   es una ESTIMACIÓN).
3. Se aplica una atenuación simple por distancia a la calle (el ruido cae
   con la distancia a la fuente).

Esto se declara explícitamente como estimación en la UI — no se presenta
como medición oficial.
"""

import math

import numpy as np
from geopy.distance import geodesic

# Calibración aproximada Lden = A + B * log10(IMV), basada en relaciones
# estándar de ruido de tráfico urbano: una vía con ~2.000 veh/día arroja
# ~55 dB(A) de fondo, una vía con ~20.000 veh/día ~70 dB(A). Esto da:
#   log10(2000) ≈ 3.30 -> 55 = A + B*3.30
#   log10(20000) ≈ 4.30 -> 70 = A + B*4.30
# Resolviendo: B = 15, A = 55 - 15*3.30 = 5.5
_A = 5.5
_B = 15.0

# Atenuación con la distancia a la calle: el ruido de tráfico cae
# aproximadamente 3 dB cada vez que se dobla la distancia a la fuente
# (atenuación de fuente lineal, típica en literatura acústica de carreteras).
_DIST_REFERENCIA_M = 10.0  # distancia a la que se calibra el nivel base


def imv_to_db(imv):
    """Convierte IMV (vehículos/día) a un nivel de ruido aproximado en dB(A)."""
    if imv is None or imv <= 0:
        return None
    return _A + _B * math.log10(imv)


def _atenuacion_por_distancia(db_base, distancia_m):
    """Aplica atenuación logarítmica simple por distancia a la fuente."""
    distancia_m = max(distancia_m, 1.0)
    atenuacion = 3.0 * math.log2(distancia_m / _DIST_REFERENCIA_M)
    return db_base - max(atenuacion, 0)


def estimate_noise_from_traffic(lat, lon, traffic_segments, max_candidates=5):
    """
    Estima el nivel de ruido en (lat, lon) a partir de los tramos de
    tráfico más cercanos.

    Parameters
    ----------
    traffic_segments : list of dict
        [{"lat": .., "lon": .., "imv": .., "nombre": ..}, ...]
        Se espera un punto representativo por tramo (p.ej. el primer
        vértice de la línea), con su IMV asociado.

    Returns
    -------
    dict con {"ruido_db": float, "tramo_nombre": str, "imv": float,
    "distancia_m": float} o None si no hay tramos disponibles.
    """
    if not traffic_segments:
        return None

    candidatos = []
    for seg in traffic_segments:
        imv = seg.get("imv")
        if imv is None:
            continue
        try:
            imv_val = float(imv)
        except (ValueError, TypeError):
            continue
        if imv_val <= 0:
            continue
        dist = geodesic((lat, lon), (seg["lat"], seg["lon"])).meters
        candidatos.append({**seg, "imv_val": imv_val, "distancia_m": dist})

    if not candidatos:
        return None

    candidatos.sort(key=lambda c: c["distancia_m"])
    candidatos = candidatos[:max_candidates]

    # Combinamos varios tramos cercanos con ponderación inversa a la
    # distancia (tramos más cercanos pesan más), en vez de usar solo el
    # tramo más próximo — esto suaviza el resultado en cruces de calles.
    pesos = np.array([1.0 / max(c["distancia_m"], 1.0) for c in candidatos])
    pesos /= pesos.sum()

    niveles_db = []
    for c in candidatos:
        db_base = imv_to_db(c["imv_val"])
        if db_base is None:
            niveles_db.append(0)
            continue
        niveles_db.append(_atenuacion_por_distancia(db_base, c["distancia_m"]))

    ruido_estimado = float(np.sum(pesos * np.array(niveles_db)))
    mas_cercano = candidatos[0]

    return {
        "ruido_db": round(ruido_estimado, 1),
        "tramo_nombre": mas_cercano.get("nombre", "Tramo sin nombre"),
        "imv": mas_cercano["imv_val"],
        "distancia_m": round(mas_cercano["distancia_m"], 0),
    }
