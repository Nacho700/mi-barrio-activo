"""
pages/1_comparador.py
=======================
Compara hasta 3 direcciones candidatas (pisos que el usuario está
valorando) en un radar de Bienestar Urbano Personal.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium

from src.geocoding import geocode_address
from src.data_helpers import (
    load_estaciones_contaminacion,
    load_geojson_points,
    load_instalaciones_deportivas,
)
from src.interpolation import estimate_environmental_profile, get_nearest_station_info
from src.accessibility import compute_accessibility_profile
from src.index import compute_ibup, ibup_label, REFERENCE_RANGES

st.set_page_config(page_title="Comparador | Mi Barrio Activo", page_icon="📊", layout="wide")
st.title("📊 Comparador de direcciones")
st.markdown(
    "Introduce hasta 3 direcciones que estés valorando para vivir y compara "
    "su Índice de Bienestar Urbano Personal."
)

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
n_direcciones = st.slider("¿Cuántas direcciones quieres comparar?", 1, 3, 2)

direcciones_input = []
cols = st.columns(n_direcciones)
for i, col in enumerate(cols):
    with col:
        addr = st.text_input(f"Dirección {i+1}", key=f"addr_{i}", placeholder="Calle, número, Valencia")
        direcciones_input.append(addr)

st.caption(
    "ℹ️ El componente de **ruido** no está disponible todavía: el dataset "
    "de estaciones de ruido de Valencia (4 estaciones) solo da ubicación, "
    "sin valores en dB descargables de forma simple. El índice se calcula "
    "con los 5 componentes restantes."
)

st.markdown("##### Ajusta qué te importa más (opcional)")
w_cols = st.columns(5)
with w_cols[0]:
    w_no2 = st.slider("NO2", 0, 100, 25, key="w_no2")
with w_cols[1]:
    w_pm10 = st.slider("PM10", 0, 100, 20, key="w_pm10")
with w_cols[2]:
    w_deporte = st.slider("Deporte", 0, 100, 25, key="w_deporte")
with w_cols[3]:
    w_bici = st.slider("Carril bici", 0, 100, 12, key="w_bici")
with w_cols[4]:
    w_verde = st.slider("Zonas verdes", 0, 100, 18, key="w_verde")

weights = {
    "no2": w_no2,
    "pm10": w_pm10,
    "tiempo_deporte_min": w_deporte,
    "tiempo_bici_min": w_bici,
    "tiempo_verde_min": w_verde,
}

ejecutar = st.button("🔍 Calcular y comparar", type="primary")

# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
# IMPORTANTE: los resultados se guardan en st.session_state en vez de en
# una variable local. ¿Por qué? st_folium (el mapa interactivo) provoca un
# re-run completo del script en cuanto se renderiza. Si los resultados
# vivieran solo dentro de "if ejecutar:" (que depende de st.button, True
# solo en el ciclo inmediatamente posterior al clic), ese re-run los
# borraría de inmediato — es justo el bug de "aparece 1 segundo y
# desaparece". Guardándolos en session_state, sobreviven a cualquier
# re-run posterior hasta que el usuario pulse el botón otra vez.
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
            # NOTA: el ruido no se incluye porque el dataset de ruido de
            # Valencia (4 estaciones) no expone valores en dB descargables
            # de forma simple — solo ubicación. Ver aviso en pantalla.
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
                "zona_verde_detalle": perfil_acceso["verde"],
            }
        )

    if not resultados:
        st.session_state.pop("comparador_resultados", None)
        st.stop()

    # Guardar en session_state para que sobreviva al re-run de st_folium
    st.session_state["comparador_resultados"] = resultados

# ---------------------------------------------------------------------------
# Mostrar resultados (si existen en session_state, de este ciclo o de uno
# anterior) — este bloque ya NO depende de "ejecutar", así que un re-run
# disparado por st_folium no lo hace desaparecer.
# ---------------------------------------------------------------------------
if "comparador_resultados" in st.session_state:
    resultados = st.session_state["comparador_resultados"]

    mapa = folium.Map(location=[39.4699, -0.3763], zoom_start=12)
    for r in resultados:
        ibup_val = r["ibup"]["ibup"]
        folium.Marker(
            [r["lat"], r["lon"]],
            tooltip=f"{r['direccion'][:40]} — IBUP: {ibup_val}",
            icon=folium.Icon(color="green" if ibup_val and ibup_val >= 60 else "orange"),
        ).add_to(mapa)

    st.divider()
    st.subheader("Resultados")

    col_mapa, col_scores = st.columns([1, 1])

    with col_mapa:
        st_folium(mapa, width=700, height=450, key="comparador_mapa")

    with col_scores:
        for r in resultados:
            ibup_val = r["ibup"]["ibup"]
            st.metric(
                label=r["direccion"][:50],
                value=f"{ibup_val}/100" if ibup_val is not None else "Sin datos",
                help=ibup_label(ibup_val),
            )

    # ------------------------------------------------------------------
    # Contexto enriquecido: calidad del aire textual, tipo de zona/emisión
    # y detalle de la zona verde más cercana (fitness, superficie)
    # ------------------------------------------------------------------
    st.markdown("##### 🔎 Contexto detallado por dirección")
    for r in resultados:
        with st.expander(f"📍 {r['direccion'][:60]}"):
            info_est = r.get("info_estacion")
            if info_est:
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown(f"**Calidad del aire** (estación {info_est['nombre']}, a {info_est['distancia_m']:.0f} m)")
                    st.markdown(f"🟢 {info_est['calidad_aire'] or 'Sin dato'}")
                with col_b:
                    st.markdown("**Tipo de emisión dominante**")
                    st.markdown(f"🏭 {info_est['tipo_emision'] or 'Sin dato'}")
                with col_c:
                    st.markdown("**Tipo de zona**")
                    st.markdown(f"🏙️ {info_est['tipo_zona'] or 'Sin dato'}")

            zona_verde = r.get("zona_verde_detalle")
            if zona_verde:
                st.markdown("---")
                st.markdown(f"**Zona verde más cercana**: {zona_verde['nombre']} ({zona_verde['minutos']} min a pie)")
                extra = zona_verde.get("extra", {})
                fitness = extra.get("n_elementos_fitness")
                superficie = extra.get("sup_total")
                tipologia = extra.get("tipologia")
                detalles = []
                if tipologia:
                    detalles.append(f"Tipo: {tipologia}")
                if fitness and str(fitness) not in ("0", "0.0", "None"):
                    detalles.append(f"🏋️ {fitness} elementos de fitness al aire libre")
                if superficie:
                    try:
                        detalles.append(f"📐 {float(superficie):,.0f} m² de superficie")
                    except (ValueError, TypeError):
                        pass
                if detalles:
                    st.markdown(" · ".join(detalles))
                else:
                    st.caption("Sin detalles adicionales disponibles para esta zona verde.")

    # Radar chart comparativo (sin ruido: no disponible con datos reales aún)
    categorias = ["no2", "pm10", "tiempo_deporte_min", "tiempo_bici_min", "tiempo_verde_min"]
    categorias_labels = [
        "NO2", "PM10", "Acceso deporte", "Acceso bici", "Acceso verde"
    ]

    fig = go.Figure()
    for r in resultados:
        valores = [r["ibup"]["componentes"].get(c) or 0 for c in categorias]
        fig.add_trace(
            go.Scatterpolar(
                r=valores,
                theta=categorias_labels,
                fill="toself",
                name=r["direccion"][:40],
            )
        )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=True,
        title="Comparativa de componentes (0 = peor, 100 = mejor)",
    )
    st.plotly_chart(fig, width="stretch")

    # Tabla de valores crudos
    st.markdown("##### Valores estimados (sin normalizar)")
    import pandas as pd

    tabla = pd.DataFrame([r["raw"] for r in resultados], index=[r["direccion"][:30] for r in resultados])
    st.dataframe(tabla)
