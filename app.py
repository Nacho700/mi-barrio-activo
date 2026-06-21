"""
app.py
=======
Mi Barrio Activo y Sano — app única centrada en comparar direcciones
candidatas para vivir en Valencia, con un Índice de Bienestar Urbano
Personal (IBUP) calculado a partir de datos abiertos reales del
Ayuntamiento de València.

Ejecutar con: streamlit run app.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium

from src.geocoding import geocode_address
from src.data_helpers import (
    load_estaciones_contaminacion,
    load_geojson_points,
    load_instalaciones_deportivas,
    load_intensidad_trafico,
)
from src.interpolation import estimate_environmental_profile, get_nearest_station_info
from src.accessibility import compute_accessibility_profile, top_n_nearest
from src.noise_inference import estimate_noise_from_traffic
from src.index import compute_ibup, ibup_label, PERFILES_USUARIO

st.set_page_config(page_title="Mi Barrio Activo y Sano", page_icon="🏠", layout="wide")

# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------
st.title("🏠 Mi Barrio Activo y Sano")
st.markdown(
    "#### Decide dónde vivir en Valencia con datos reales, no solo con el precio"
)
st.markdown(
    "Cuando buscas piso miras precio y metros — pero casi nunca puedes saber "
    "objetivamente **cuánto ruido tendrás**, **cuánta contaminación vas a "
    "respirar**, o **a cuántos minutos a pie está el parque o el polideportivo "
    "más cercano**. Esta herramienta lo calcula por ti con datos abiertos "
    "reales del Ayuntamiento de València."
)

with st.expander("ℹ️ Metodología y fuentes de datos"):
    st.markdown(
        """
**Fuentes de datos** (Open Data València, Ajuntament de València):
- Estaciones de contaminación atmosférica (NO2, PM10, PM2.5) con valores actuales
- Intensidad de tráfico por tramo de calle (usada para **estimar ruido**, ver más abajo)
- Inventario de arbolado y zonas verdes (con fitness y superficie)
- Itinerarios ciclistas (carril bici)
- Equipamientos municipales (instalaciones deportivas, filtradas)
- Red de calles peatonal: OpenStreetMap (vía OSMnx)

**Métodos de Data Science aplicados:**
1. **Interpolación espacial (IDW)** para estimar contaminación en cualquier punto.
2. **Inferencia de ruido por proxy de tráfico**: el dataset oficial de ruido de
   Valencia solo tiene 4 estaciones sin valores en dB accesibles. En su lugar,
   se estima el ruido a partir de la intensidad de tráfico (IMV) en los tramos
   de calle más cercanos, usando una relación logarítmica estándar en acústica
   de tráfico (Lden ≈ A + B·log10(IMV)) con atenuación por distancia. Esto es
   una **estimación**, no una medición certificada — se indica así en la app.
3. **Grafo de calles real** (NetworkX/OSMnx) para tiempos a pie reales.
4. **Índice compuesto ponderable**, con perfiles de usuario predefinidos
   (familia, deportista, mayor) que repunderan automáticamente lo que más
   importa a cada perfil.

Proyecto académico — UPV, Grado en Ciencia de Datos.
        """
    )

st.divider()

# ---------------------------------------------------------------------------
# Selector de perfil de usuario
# ---------------------------------------------------------------------------
st.markdown("### 👤 ¿Qué tipo de persona eres?")
st.caption("Esto repondera automáticamente el índice según lo que más te importa. Siempre puedes ajustarlo a mano después.")

perfil_keys = list(PERFILES_USUARIO.keys())
perfil_labels = [PERFILES_USUARIO[k]["nombre"] for k in perfil_keys]

perfil_idx = st.radio(
    "Perfil",
    options=range(len(perfil_keys)),
    format_func=lambda i: perfil_labels[i],
    horizontal=True,
    label_visibility="collapsed",
)
perfil_seleccionado = perfil_keys[perfil_idx]
st.caption(f"💡 {PERFILES_USUARIO[perfil_seleccionado]['descripcion']}")

# ---------------------------------------------------------------------------
# Inputs de direcciones
# ---------------------------------------------------------------------------
st.markdown("### 📍 Direcciones a comparar")
n_direcciones = st.slider("¿Cuántas direcciones quieres comparar?", 1, 3, 2)

direcciones_input = []
cols = st.columns(n_direcciones)
for i, col in enumerate(cols):
    with col:
        addr = st.text_input(f"Dirección {i+1}", key=f"addr_{i}", placeholder="Calle, número, Valencia")
        direcciones_input.append(addr)

# ---------------------------------------------------------------------------
# Pesos: predefinidos por perfil, o sliders si el perfil es "personalizado"
# ---------------------------------------------------------------------------
if perfil_seleccionado == "personalizado":
    st.markdown("##### 🎛️ Ajusta qué te importa más")
    w_cols = st.columns(6)
    with w_cols[0]:
        w_no2 = st.slider("NO2", 0, 100, 20, key="w_no2")
    with w_cols[1]:
        w_pm10 = st.slider("PM10", 0, 100, 12, key="w_pm10")
    with w_cols[2]:
        w_ruido = st.slider("Ruido", 0, 100, 20, key="w_ruido")
    with w_cols[3]:
        w_deporte = st.slider("Deporte", 0, 100, 18, key="w_deporte")
    with w_cols[4]:
        w_bici = st.slider("Carril bici", 0, 100, 8, key="w_bici")
    with w_cols[5]:
        w_verde = st.slider("Zonas verdes", 0, 100, 14, key="w_verde")

    weights = {
        "no2": w_no2,
        "pm10": w_pm10,
        "pm25": 8,
        "ruido_db": w_ruido,
        "tiempo_deporte_min": w_deporte,
        "tiempo_bici_min": w_bici,
        "tiempo_verde_min": w_verde,
    }
else:
    weights = PERFILES_USUARIO[perfil_seleccionado]["weights"]

ejecutar = st.button("🔍 Calcular y comparar", type="primary")

# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
# NOTA TÉCNICA: los resultados se guardan en st.session_state porque
# st_folium (el mapa interactivo) dispara un re-run completo del script en
# cuanto se renderiza. Si los resultados solo vivieran dentro de
# "if ejecutar:" (True solo en el ciclo inmediatamente posterior al clic),
# ese re-run los borraría de inmediato.
if ejecutar:
    direcciones_validas = [d for d in direcciones_input if d.strip()]
    if not direcciones_validas:
        st.warning("Introduce al menos una dirección.")
        st.stop()

    with st.spinner("Cargando capas de datos..."):
        stations_with_values = load_estaciones_contaminacion()
        carril_bici_points = load_geojson_points("carril_bici.geojson")
        verde_points = load_geojson_points(
            "zonas_verdes.geojson",
            extra_props=["n_elementos_fitness", "sup_total", "tipologia"],
        ) + load_geojson_points("arbolado.geojson")
        deporte_points = load_instalaciones_deportivas()
        traffic_segments = load_intensidad_trafico()

    if stations_with_values.empty:
        st.error(
            "No se han encontrado datos de estaciones de contaminación. "
            "Ejecuta `python src/data_loader.py --download-all` primero."
        )
        st.stop()

    resultados = []

    for direccion in direcciones_validas:
        geo = geocode_address(direccion)
        if geo is None:
            st.warning(f"No se pudo localizar: '{direccion}'. Prueba a ser más específico.")
            continue

        lat, lon = geo["lat"], geo["lon"]

        perfil_ambiental = estimate_environmental_profile(lat, lon, stations_with_values)
        info_estacion = get_nearest_station_info(lat, lon, stations_with_values)
        ruido_info = estimate_noise_from_traffic(lat, lon, traffic_segments)

        try:
            perfil_acceso = compute_accessibility_profile(
                lat, lon, carril_bici_points, deporte_points, verde_points
            )
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()

        raw_values = {
            "no2": perfil_ambiental.get("no2"),
            "pm10": perfil_ambiental.get("pm10"),
            "pm25": perfil_ambiental.get("pm25"),
            "ruido_db": ruido_info["ruido_db"] if ruido_info else None,
            "tiempo_deporte_min": perfil_acceso["deporte"]["minutos"] if perfil_acceso["deporte"] else None,
            "tiempo_bici_min": perfil_acceso["carril_bici"]["minutos"] if perfil_acceso["carril_bici"] else None,
            "tiempo_verde_min": perfil_acceso["verde"]["minutos"] if perfil_acceso["verde"] else None,
        }

        ibup_result = compute_ibup(raw_values, weights)

        resultados.append(
            {
                "direccion": geo["direccion_completa"],
                "lat": lat,
                "lon": lon,
                "raw": raw_values,
                "ibup": ibup_result,
                "info_estacion": info_estacion,
                "ruido_info": ruido_info,
                "zona_verde_detalle": perfil_acceso["verde"],
            }
        )

    if not resultados:
        st.session_state.pop("resultados", None)
        st.stop()

    st.session_state["resultados"] = resultados
    st.session_state["perfil_usado"] = PERFILES_USUARIO[perfil_seleccionado]["nombre"]

# ---------------------------------------------------------------------------
# Mostrar resultados
# ---------------------------------------------------------------------------
def _es_valido(valor):
    """True si el valor es un dato real, no None/NaN/vacío."""
    if valor is None:
        return False
    try:
        import math
        if isinstance(valor, float) and math.isnan(valor):
            return False
    except TypeError:
        pass
    if isinstance(valor, str) and valor.strip().lower() in ("", "nan", "none"):
        return False
    return True


if "resultados" in st.session_state:
    resultados = st.session_state["resultados"]

    st.divider()
    st.subheader(f"📋 Resultados (perfil: {st.session_state.get('perfil_usado', '')})")

    # --- Mapa + métricas principales -----------------------------------
    mapa = folium.Map(location=[39.4699, -0.3763], zoom_start=12)
    for r in resultados:
        ibup_val = r["ibup"]["ibup"]
        folium.Marker(
            [r["lat"], r["lon"]],
            tooltip=f"{r['direccion'][:40]} — IBUP: {ibup_val}",
            icon=folium.Icon(color="green" if ibup_val and ibup_val >= 60 else "orange"),
        ).add_to(mapa)

    col_mapa, col_scores = st.columns([1, 1])
    with col_mapa:
        st_folium(mapa, width=700, height=420, key="mapa_principal")
    with col_scores:
        for r in resultados:
            ibup_val = r["ibup"]["ibup"]
            st.metric(
                label=r["direccion"][:50],
                value=f"{ibup_val}/100" if ibup_val is not None else "Sin datos",
                help=ibup_label(ibup_val),
            )

    # --- Radar comparativo ----------------------------------------------
    st.markdown("##### 📊 Comparativa visual")
    categorias = ["no2", "pm10", "ruido_db", "tiempo_deporte_min", "tiempo_bici_min", "tiempo_verde_min"]
    categorias_labels = ["NO2", "PM10", "Ruido (estimado)", "Acceso deporte", "Acceso bici", "Acceso verde"]

    fig = go.Figure()
    for r in resultados:
        valores = [r["ibup"]["componentes"].get(c) or 0 for c in categorias]
        fig.add_trace(
            go.Scatterpolar(r=valores, theta=categorias_labels, fill="toself", name=r["direccion"][:40])
        )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True,
        title="0 = peor, 100 = mejor",
        height=420,
    )
    st.plotly_chart(fig, width="stretch")

    # --- Contexto detallado por dirección --------------------------------
    st.markdown("##### 🔎 Contexto detallado por dirección")
    for r in resultados:
        with st.container(border=True):
            st.markdown(f"#### 📍 {r['direccion'][:70]}")

            info_est = r.get("info_estacion")
            ruido_info = r.get("ruido_info")

            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                st.markdown("**Calidad del aire**")
                if info_est:
                    st.markdown(f"🟢 {info_est['calidad_aire'] or 'Sin dato'}")
                    st.caption(f"Estación {info_est['nombre']}, a {info_est['distancia_m']:.0f} m")
                else:
                    st.caption("Sin dato")
            with col_b:
                st.markdown("**Tipo de emisión**")
                st.markdown(f"🏭 {info_est['tipo_emision'] if info_est else 'Sin dato'}")
            with col_c:
                st.markdown("**Tipo de zona**")
                st.markdown(f"🏙️ {info_est['tipo_zona'] if info_est else 'Sin dato'}")
            with col_d:
                st.markdown("**Ruido estimado**")
                if ruido_info:
                    st.markdown(f"🔊 {ruido_info['ruido_db']:.0f} dB(A)")
                    st.caption(f"Cerca de: {ruido_info['tramo_nombre']}")
                else:
                    st.caption("Sin dato")

            zona_verde = r.get("zona_verde_detalle")
            if zona_verde:
                st.markdown("---")
                nombre_zona = zona_verde["nombre"]
                if not _es_valido(nombre_zona) or str(nombre_zona).lower() == "sin nombre":
                    nombre_zona = "Árbol o zona verde sin nombre registrado"
                st.markdown(f"**🌳 Zona verde más cercana**: {nombre_zona} ({zona_verde['minutos']} min a pie)")

                extra = zona_verde.get("extra", {})
                tipologia = extra.get("tipologia")
                fitness = extra.get("n_elementos_fitness")
                superficie = extra.get("sup_total")

                detalles = []
                if _es_valido(tipologia):
                    detalles.append(f"Tipo: {tipologia}")
                if _es_valido(fitness) and float(fitness) > 0:
                    detalles.append(f"🏋️ {int(float(fitness))} elementos de fitness al aire libre")
                if _es_valido(superficie):
                    try:
                        detalles.append(f"📐 {float(superficie):,.0f} m² de superficie")
                    except (ValueError, TypeError):
                        pass

                if detalles:
                    st.markdown(" · ".join(detalles))
                else:
                    st.caption(
                        "Este punto verde más cercano es un árbol individual del "
                        "inventario de arbolado, sin ficha de zona verde asociada."
                    )

            # --- Top 5 ---------------------------------------------------
            st.markdown("---")
            key_top5 = f"top5_{r['direccion'][:20]}_{r['lat']}_{r['lon']}"
            if st.button("🏆 Ver Top 5 zonas verdes e instalaciones deportivas cercanas", key=f"btn_{key_top5}"):
                with st.spinner("Calculando rankings..."):
                    verde_points_top5 = load_geojson_points(
                        "zonas_verdes.geojson",
                        extra_props=["n_elementos_fitness", "sup_total", "tipologia"],
                    ) + load_geojson_points("arbolado.geojson")
                    deporte_points_top5 = load_instalaciones_deportivas()

                    top5_verde = top_n_nearest(r["lat"], r["lon"], verde_points_top5, n=5)
                    top5_deporte = top_n_nearest(r["lat"], r["lon"], deporte_points_top5, n=5)
                    st.session_state[key_top5] = {"verde": top5_verde, "deporte": top5_deporte}

            if key_top5 in st.session_state:
                top5_data = st.session_state[key_top5]
                col_top_verde, col_top_deporte = st.columns(2)
                with col_top_verde:
                    st.markdown("**🌳 Top 5 zonas verdes**")
                    if top5_data["verde"]:
                        for i, z in enumerate(top5_data["verde"], 1):
                            nombre_z = z["nombre"] if _es_valido(z["nombre"]) and str(z["nombre"]).lower() != "sin nombre" else "Árbol/zona sin nombre"
                            st.markdown(f"{i}. {nombre_z} — {z['minutos']} min a pie")
                    else:
                        st.caption("Sin datos disponibles.")
                with col_top_deporte:
                    st.markdown("**🏋️ Top 5 instalaciones deportivas**")
                    if top5_data["deporte"]:
                        for i, d in enumerate(top5_data["deporte"], 1):
                            st.markdown(f"{i}. {d['nombre']} — {d['minutos']} min a pie")
                    else:
                        st.caption("Sin datos disponibles.")

    # --- Tabla de valores crudos ------------------------------------------
    with st.expander("📐 Ver valores numéricos sin normalizar"):
        tabla = pd.DataFrame([r["raw"] for r in resultados], index=[r["direccion"][:30] for r in resultados])
        st.dataframe(tabla)
