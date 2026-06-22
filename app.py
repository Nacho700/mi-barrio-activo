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

from src.geocoding import geocode_address, GeocodingServiceError
from src.data_helpers import (
    load_estaciones_contaminacion,
    load_geojson_points,
    load_instalaciones_deportivas,
    load_intensidad_trafico,
    load_mercados,
    load_centros_salud,
    load_paradas_emt,
    load_estaciones_fgv,
    load_valenbisi,
)
from src.interpolation import estimate_environmental_profile, get_nearest_station_info, compute_city_averages
from src.accessibility import compute_accessibility_profile, top_n_nearest, count_within_minutes, walking_time_to_nearest
from src.noise_inference import estimate_noise_from_traffic
from src.index import compute_ibup, ibup_label, PERFILES_USUARIO
from src.clustering import load_cluster_grid, get_cluster_for_point, validate_cluster_grid, CLUSTER_LABELS
from src.report_export import generar_informe_comparativo

st.set_page_config(page_title="Mi Barrio Activo y Sano", page_icon="🏠", layout="wide")

# ---------------------------------------------------------------------------
# Estilos — paleta mediterránea inspirada en Valencia: crema cálido,
# terracota de teja, verde Turia, azul cerámica. Tipografía display con
# carácter (Fraunces) para títulos, sans-serif limpia para el cuerpo.
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Inter:wght@400;500;600&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    h1, h2, h3 {
        font-family: 'Fraunces', serif !important;
        font-weight: 600 !important;
        color: #2B2620 !important;
        letter-spacing: -0.01em;
    }

    /* Hero */
    .hero-wrap {
        background: linear-gradient(135deg, #F2E9D8 0%, #FBF6EE 60%);
        border-radius: 18px;
        padding: 2.2rem 2.4rem;
        margin-bottom: 1.4rem;
        border: 1px solid rgba(43,38,32,0.08);
        position: relative;
        overflow: hidden;
    }
    .hero-wrap::before {
        content: "";
        position: absolute;
        top: -40px; right: -40px;
        width: 180px; height: 180px;
        background: #E8B4A0;
        border-radius: 50%;
        opacity: 0.35;
    }
    .hero-eyebrow {
        display: inline-block;
        font-family: 'Inter', sans-serif;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #C65D3B;
        background: rgba(198,93,59,0.10);
        padding: 0.25rem 0.7rem;
        border-radius: 100px;
        margin-bottom: 0.8rem;
    }
    .hero-title {
        font-family: 'Fraunces', serif;
        font-weight: 700;
        font-size: 2.3rem;
        line-height: 1.1;
        color: #2B2620;
        margin: 0 0 0.5rem 0;
        position: relative;
        z-index: 1;
    }
    .hero-sub {
        font-size: 1.05rem;
        color: #54493e;
        max-width: 62ch;
        position: relative;
        z-index: 1;
        line-height: 1.5;
    }

    /* Feature pills row */
    .feature-row { display: flex; gap: 0.9rem; margin-top: 1.4rem; flex-wrap: wrap; position: relative; z-index: 1; }
    .feature-pill {
        flex: 1; min-width: 200px;
        background: white;
        border: 1px solid rgba(43,38,32,0.08);
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        box-shadow: 0 1px 2px rgba(43,38,32,0.04);
    }
    .feature-pill .icon { font-size: 1.4rem; margin-bottom: 0.3rem; display: block; }
    .feature-pill .label { font-weight: 600; font-size: 0.92rem; color: #2B2620; }
    .feature-pill .desc { font-size: 0.82rem; color: #7a6f60; margin-top: 0.15rem; }

    /* Cluster badge */
    .cluster-badge {
        display: inline-block;
        background: #CFE0D3;
        color: #3D6B4F;
        font-weight: 600;
        font-size: 0.85rem;
        padding: 0.3rem 0.8rem;
        border-radius: 100px;
        margin-bottom: 0.6rem;
    }

    /* Address card top accent */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px !important;
    }

    /* Section dividers spacing */
    hr { margin: 1.2rem 0 !important; opacity: 0.25; }

    /* Perfil selector chips */
    div[role="radiogroup"] {
        gap: 0.6rem;
    }
    div[role="radiogroup"] label {
        background: white;
        border: 1.5px solid rgba(43,38,32,0.12);
        border-radius: 10px;
        padding: 0.55rem 1rem !important;
        transition: all 0.15s ease;
    }
    div[role="radiogroup"] label:hover {
        border-color: #C65D3B;
        background: rgba(198,93,59,0.05);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero-wrap">
        <span class="hero-eyebrow">Open Data València · UPV Project</span>
        <p class="hero-title">Decide where to live in Valencia<br>with data, not just price</p>
        <p class="hero-sub">
            When you're looking for a flat you check price and square metres — but you
            can almost never know objectively how much noise you'll get, how much
            pollution you'll breathe, or how many minutes away on foot the nearest park
            or sports centre is. This tool calculates it for you using real open data
            from the Valencia City Council.
        </p>
        <div class="feature-row">
            <div class="feature-pill">
                <span class="icon">🌬️</span>
                <div class="label">Air and noise</div>
                <div class="desc">Real pollution + noise estimated from traffic</div>
            </div>
            <div class="feature-pill">
                <span class="icon">🌳</span>
                <div class="label">Green space and sports</div>
                <div class="desc">Real walking minutes, not straight-line distance</div>
            </div>
            <div class="feature-pill">
                <span class="icon">🏷️</span>
                <div class="label">Neighbourhood type</div>
                <div class="desc">Automatic clustering by similarity</div>
            </div>
            <div class="feature-pill">
                <span class="icon">👤</span>
                <div class="label">Tailored to you</div>
                <div class="desc">Profiles that reweight what matters to you</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("ℹ️ Methodology and data sources"):
    st.markdown(
        """
**Data sources** (Open Data València, Ajuntament de València):
- Air pollution monitoring stations (NO2, PM10, PM2.5) with current values
- Traffic intensity per street segment (used to **estimate noise**, see below)
- Tree and green space inventory (with fitness equipment and surface area)
- Cycling routes (bike lanes)
- Municipal facilities (sports facilities, filtered)
- Pedestrian street network: OpenStreetMap (via OSMnx)

**Data Science methods applied:**
1. **Spatial interpolation (IDW)** to estimate pollution at any point.
2. **Noise inference via traffic proxy**: Valencia's official noise dataset only
   has 4 stations with no accessible dB values. Instead, noise is estimated from
   traffic intensity (IMV) at the nearest street segments, using a standard
   logarithmic relationship in traffic acoustics (Lden ≈ A + B·log10(IMV)) with
   distance attenuation. This is an **estimate**, not a certified measurement —
   it is labelled as such throughout the app.
3. **Real street graph** (NetworkX/OSMnx) for real walking times.
4. **Weighted composite index**, with predefined user profiles (family, athlete,
   older adult) that automatically reweight what matters most to each profile.

Academic project — UPV, Data Science degree.
        """
    )

st.divider()

# ---------------------------------------------------------------------------
# Selector de perfil de usuario
# ---------------------------------------------------------------------------
st.markdown("### 👤 What type of person are you?")
st.caption("This automatically reweights the index based on what matters most to you. You can always adjust it manually afterwards.")

perfil_keys = list(PERFILES_USUARIO.keys())
perfil_labels = [PERFILES_USUARIO[k]["nombre"] for k in perfil_keys]

perfil_idx = st.radio(
    "Profile",
    options=range(len(perfil_keys)),
    format_func=lambda i: perfil_labels[i],
    horizontal=True,
    label_visibility="collapsed",
)
perfil_seleccionado = perfil_keys[perfil_idx]
st.caption(f"💡 {PERFILES_USUARIO[perfil_seleccionado]['descripcion']}")

# --- Visualizar los pesos del perfil elegido (antes de calcular nada) ----
if perfil_seleccionado != "personalizado":
    pesos_perfil = PERFILES_USUARIO[perfil_seleccionado]["weights"]
    nombres_componentes_pesos = {
        "no2": "NO2", "pm10": "PM10", "pm25": "PM2.5", "ruido_db": "Noise",
        "tiempo_deporte_min": "Sports", "tiempo_bici_min": "Bike lane",
        "tiempo_verde_min": "Green space", "tiempo_transporte_min": "Transport",
    }
    paleta_componentes_pesos = {
        "no2": "#C65D3B", "pm10": "#D98C6F", "pm25": "#E8B4A0", "ruido_db": "#8C4A3A",
        "tiempo_deporte_min": "#3D6B4F", "tiempo_bici_min": "#6B9C7A",
        "tiempo_verde_min": "#A8C9AE", "tiempo_transporte_min": "#2F6E8C",
    }
    with st.expander("📐 See how this profile distributes importance"):
        fig_pesos = go.Figure(
            data=[
                go.Pie(
                    labels=[nombres_componentes_pesos[k] for k in pesos_perfil],
                    values=[v * 100 for v in pesos_perfil.values()],
                    hole=0.55,
                    marker=dict(colors=[paleta_componentes_pesos[k] for k in pesos_perfil]),
                    textinfo="label+percent",
                    textfont=dict(family="Inter", size=12),
                )
            ]
        )
        fig_pesos.update_layout(
            height=320,
            showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=10, b=10, l=10, r=10),
        )
        st.plotly_chart(fig_pesos, width="stretch")

# ---------------------------------------------------------------------------
# Inputs de direcciones
# ---------------------------------------------------------------------------
st.markdown("### 📍 Addresses to compare")
n_direcciones = st.slider("How many addresses do you want to compare?", 1, 3, 2)
st.caption("💶 Optionally add the asking price of each flat to see which one gives you the best value for money.")

direcciones_input = []
precios_input = []
cols = st.columns(n_direcciones)
for i, col in enumerate(cols):
    with col:
        addr = st.text_input(f"Address {i+1}", key=f"addr_{i}", placeholder="Street, number, Valencia")
        direcciones_input.append(addr)
        precio = st.number_input(
            f"Price (€) — optional",
            key=f"precio_{i}",
            min_value=0,
            value=0,
            step=5000,
            help="Leave at 0 if you don't want to compare value for money for this address.",
        )
        precios_input.append(precio if precio > 0 else None)

# ---------------------------------------------------------------------------
# Pesos: predefinidos por perfil, o sliders si el perfil es "personalizado"
# ---------------------------------------------------------------------------
if perfil_seleccionado == "personalizado":
    st.markdown("##### 🎛️ Adjust what matters most to you")
    w_cols = st.columns(7)
    with w_cols[0]:
        w_no2 = st.slider("NO2", 0, 100, 17, key="w_no2")
    with w_cols[1]:
        w_pm10 = st.slider("PM10", 0, 100, 10, key="w_pm10")
    with w_cols[2]:
        w_ruido = st.slider("Noise", 0, 100, 18, key="w_ruido")
    with w_cols[3]:
        w_deporte = st.slider("Sports", 0, 100, 15, key="w_deporte")
    with w_cols[4]:
        w_bici = st.slider("Bike lane", 0, 100, 7, key="w_bici")
    with w_cols[5]:
        w_verde = st.slider("Green space", 0, 100, 12, key="w_verde")
    with w_cols[6]:
        w_transporte = st.slider("Public transport", 0, 100, 14, key="w_transporte")

    weights = {
        "no2": w_no2,
        "pm10": w_pm10,
        "pm25": 7,
        "ruido_db": w_ruido,
        "tiempo_deporte_min": w_deporte,
        "tiempo_bici_min": w_bici,
        "tiempo_verde_min": w_verde,
        "tiempo_transporte_min": w_transporte,
    }
else:
    weights = PERFILES_USUARIO[perfil_seleccionado]["weights"]

ejecutar = st.button("🔍 Calculate and compare", type="primary")

# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
# NOTA TÉCNICA: los resultados se guardan en st.session_state porque
# st_folium (el mapa interactivo) dispara un re-run completo del script en
# cuanto se renderiza. Si los resultados solo vivieran dentro de
# "if ejecutar:" (True solo en el ciclo inmediatamente posterior al clic),
# ese re-run los borraría de inmediato.
if ejecutar:
    direcciones_con_precio = [
        (d, p) for d, p in zip(direcciones_input, precios_input) if d.strip()
    ]
    if not direcciones_con_precio:
        st.warning("Enter at least one address.")
        st.stop()

    with st.spinner("Loading data layers..."):
        stations_with_values = load_estaciones_contaminacion()
        carril_bici_points = load_geojson_points("carril_bici.geojson")
        verde_points = load_geojson_points(
            "zonas_verdes.geojson",
            extra_props=["n_elementos_fitness", "sup_total", "tipologia"],
        ) + load_geojson_points("arbolado.geojson")
        deporte_points = load_instalaciones_deportivas()
        traffic_segments = load_intensidad_trafico()
        cluster_grid = load_cluster_grid()
        city_averages = compute_city_averages(stations_with_values)

        # Transporte público: combinamos EMT (bus), FGV (metro/tranvía) y
        # Valenbisi (bici pública) en una sola lista — el usuario quiere
        # saber "¿qué tan cerca tengo transporte público?" en general, sin
        # tener que mirar 3 cosas distintas por separado.
        paradas_emt = load_paradas_emt()
        estaciones_fgv = load_estaciones_fgv()
        valenbisi_points = load_valenbisi()
        transporte_points = paradas_emt + estaciones_fgv + valenbisi_points

    if stations_with_values.empty:
        st.error(
            "No air pollution monitoring station data found. "
            "Run `python src/data_loader.py --download-all` first."
        )
        st.stop()

    resultados = []

    for direccion, precio in direcciones_con_precio:
        try:
            geo = geocode_address(direccion)
        except GeocodingServiceError:
            st.error(
                f"⚠️ The geocoding service (Nominatim/OpenStreetMap) did not respond "
                f"while searching for '{direccion}'. **This does not mean the address "
                f"is misspelled** — it's a free external service that sometimes gets "
                f"overloaded. Wait a few seconds and try again.",
                icon="⚠️",
            )
            continue
        if geo is None:
            st.warning(f"Could not locate: '{direccion}'. Try being more specific.")
            continue

        lat, lon = geo["lat"], geo["lon"]

        perfil_ambiental = estimate_environmental_profile(lat, lon, stations_with_values)
        info_estacion = get_nearest_station_info(lat, lon, stations_with_values)
        ruido_info = estimate_noise_from_traffic(lat, lon, traffic_segments)
        cluster_info = get_cluster_for_point(lat, lon, cluster_grid)

        try:
            perfil_acceso = compute_accessibility_profile(
                lat, lon, carril_bici_points, deporte_points, verde_points
            )
            conteo_verde_15min = count_within_minutes(lat, lon, verde_points, minutos_max=15)
            conteo_deporte_15min = count_within_minutes(lat, lon, deporte_points, minutos_max=15)
            transporte_cercano = walking_time_to_nearest(lat, lon, transporte_points)
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
            "tiempo_transporte_min": transporte_cercano["minutos"] if transporte_cercano else None,
        }

        ibup_result = compute_ibup(raw_values, weights)

        # Value score: cuántos puntos de IBUP se "compran" por cada
        # 100.000€ de precio. Solo se calcula si el usuario introdujo un
        # precio real — no inventamos ningún dato de mercado inmobiliario,
        # ya que no existe un dataset abierto de precios de vivienda en
        # venta para Valencia (los portales privados no tienen API pública).
        value_score = None
        if precio and precio > 0 and ibup_result["ibup"] is not None:
            value_score = round(ibup_result["ibup"] / (precio / 100000), 2)

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
                "cluster_info": cluster_info,
                "conteo_verde_15min": conteo_verde_15min,
                "conteo_deporte_15min": conteo_deporte_15min,
                "transporte_cercano": transporte_cercano,
                "precio": precio,
                "value_score": value_score,
            }
        )

    if not resultados:
        st.session_state.pop("resultados", None)
        st.stop()

    st.session_state["resultados"] = resultados
    st.session_state["perfil_usado"] = PERFILES_USUARIO[perfil_seleccionado]["nombre"]
    st.session_state["city_averages"] = city_averages

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

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, #F2E9D8 0%, #FBF6EE 100%);
                    border-radius:16px; padding:1.6rem 1.8rem; margin-bottom:1.2rem;
                    border:1px solid rgba(43,38,32,0.08);">
            <span class="hero-eyebrow">Analysis complete</span>
            <p style="font-family:'Fraunces',serif; font-weight:700; font-size:1.7rem;
                      color:#2B2620; margin:0.3rem 0 0.2rem 0;">
                📊 Analysis results
            </p>
            <p style="color:#7a6f60; margin:0; font-size:0.95rem;">
                Profile applied: <strong>{st.session_state.get('perfil_usado', '')}</strong>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
            if ibup_val is None:
                color = "#9a9088"
            elif ibup_val >= 60:
                color = "#3D6B4F"
            elif ibup_val >= 40:
                color = "#C68A2E"
            else:
                color = "#C65D3B"
            pct = ibup_val if ibup_val is not None else 0

            valor_extra_html = ""
            if r.get("precio"):
                value_score = r.get("value_score")
                precio_fmt = f"{r['precio']:,.0f}"
                valor_extra_html = (
                    '<div style="display:flex; justify-content:space-between; '
                    'align-items:baseline; margin-top:0.5rem; padding-top:0.5rem; '
                    'border-top:1px dashed rgba(43,38,32,0.12);">'
                    f'<span style="font-size:0.78rem; color:#7a6f60;">\u20ac{precio_fmt}</span>'
                    '<span style="font-size:0.78rem; color:#7a6f60;">'
                    f'Value score: <strong style="color:#2F6E8C;">{value_score}</strong> IBUP pts / \u20ac100k'
                    '</span></div>'
                )

            ibup_texto = f"{ibup_val:.0f}" if ibup_val is not None else "\u2014"
            tarjeta_html = (
                '<div style="background:white; border:1px solid rgba(43,38,32,0.10); '
                'border-radius:12px; padding:0.9rem 1.1rem; margin-bottom:0.7rem;">'
                '<div style="display:flex; justify-content:space-between; align-items:baseline;">'
                f'<span style="font-weight:600; font-size:0.92rem;">{r["direccion"][:48]}</span>'
                f'<span style="font-family:\'Fraunces\',serif; font-weight:700; font-size:1.4rem; color:{color};">'
                f'{ibup_texto}<span style="font-size:0.85rem; color:#9a9088;">/100</span></span>'
                '</div>'
                f'<div style="background:rgba(43,38,32,0.07); border-radius:100px; height:6px; margin-top:0.5rem;">'
                f'<div style="background:{color}; width:{pct}%; height:6px; border-radius:100px;"></div></div>'
                f'<div style="font-size:0.8rem; color:#7a6f60; margin-top:0.3rem;">{ibup_label(ibup_val)}</div>'
                f'{valor_extra_html}'
                '</div>'
            )
            st.markdown(tarjeta_html, unsafe_allow_html=True)

    precios_disponibles = [r for r in resultados if r.get("precio")]
    if len(precios_disponibles) >= 2:
        mejor_valor = max(precios_disponibles, key=lambda r: r["value_score"] or 0)
        st.info(
            f"💶 **Best value for money**: {mejor_valor['direccion'][:50]} "
            f"({mejor_valor['value_score']} IBUP points per €100k)",
            icon="💶",
        )

    # --- Mapa de tipos de barrio (clusters) ------------------------------
    cluster_grid_mapa = load_cluster_grid()
    if not cluster_grid_mapa.empty and "cluster" in cluster_grid_mapa.columns:
        st.markdown("##### 🗺️ Neighbourhood type map of Valencia")
        st.caption(
            "Each point represents a grid cell from the analysis, coloured by "
            "neighbourhood type (K-means clustering). Your addresses are marked with a pin."
        )

        # Paleta consistente con CLUSTER_LABELS — colores con buen contraste
        # entre sí, en línea con la paleta mediterránea del resto de la app.
        COLORES_CLUSTER = {
            0: "#C65D3B",  # terracota — Céntrico y dinámico
            1: "#3D6B4F",  # verde Turia — Residencial equilibrado
            2: "#9a9088",  # gris cálido — Periferia, poco conectado
            3: "#2F6E8C",  # azul cerámica — Bien conectado, más tráfico
        }

        mapa_clusters = folium.Map(location=[39.4699, -0.3763], zoom_start=12, tiles="CartoDB positron")

        for _, fila in cluster_grid_mapa.iterrows():
            cluster_id = int(fila["cluster"])
            color = COLORES_CLUSTER.get(cluster_id, "#9a9088")
            etiqueta = CLUSTER_LABELS.get(cluster_id, f"Cluster {cluster_id}")
            folium.CircleMarker(
                [fila["lat"], fila["lon"]],
                radius=6,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.55,
                stroke=False,
                tooltip=etiqueta,
            ).add_to(mapa_clusters)

        # Marcamos las direcciones del usuario por encima, bien visibles
        for r in resultados:
            folium.Marker(
                [r["lat"], r["lon"]],
                tooltip=r["direccion"][:40],
                icon=folium.Icon(color="black", icon="home"),
            ).add_to(mapa_clusters)

        # Leyenda simple como HTML superpuesto
        leyenda_html = '<div style="background:white; padding:0.6rem 0.8rem; border-radius:8px; font-size:0.8rem; line-height:1.5; box-shadow:0 1px 4px rgba(0,0,0,0.15);">'
        for cluster_id, etiqueta in CLUSTER_LABELS.items():
            color = COLORES_CLUSTER.get(cluster_id, "#9a9088")
            etiqueta_limpia = etiqueta
            leyenda_html += f'<span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:{color}; margin-right:6px;"></span>{etiqueta_limpia}<br>'
        leyenda_html += "</div>"

        st_folium(mapa_clusters, width=900, height=480, key="mapa_clusters", returned_objects=[])
        st.markdown(leyenda_html, unsafe_allow_html=True)

    # --- Radar comparativo ----------------------------------------------
    st.markdown("##### 📊 Visual comparison")
    categorias = ["no2", "pm10", "ruido_db", "tiempo_deporte_min", "tiempo_bici_min", "tiempo_verde_min", "tiempo_transporte_min"]
    categorias_labels = ["NO2", "PM10", "Noise (estimated)", "Sports access", "Bike lane access", "Green space access", "Public transport"]
    paleta_radar = ["#C65D3B", "#3D6B4F", "#2F6E8C"]

    fig = go.Figure()
    for i, r in enumerate(resultados):
        valores = [r["ibup"]["componentes"].get(c) or 0 for c in categorias]
        color = paleta_radar[i % len(paleta_radar)]
        fig.add_trace(
            go.Scatterpolar(
                r=valores, theta=categorias_labels, fill="toself", name=r["direccion"][:40],
                line=dict(color=color, width=2),
                opacity=0.75,
            )
        )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], gridcolor="rgba(43,38,32,0.12)"),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        title=dict(text="0 = worst, 100 = best", font=dict(family="Inter", size=13, color="#7a6f60")),
        font=dict(family="Inter"),
        height=420,
    )
    st.plotly_chart(fig, width="stretch")

    # --- Barras apiladas: contribución de cada componente al IBUP --------
    st.markdown("##### 🧱 What weighs most in each IBUP?")
    st.caption(
        "Each bar adds up to the total IBUP. The segments show how much each "
        "component contributes, combining its score (0-100) with the weight your "
        "profile gives it — so you see not just the final result, but what's driving it."
    )

    nombres_componentes = {
        "no2": "NO2", "pm10": "PM10", "pm25": "PM2.5", "ruido_db": "Noise",
        "tiempo_deporte_min": "Sports", "tiempo_bici_min": "Bike lane",
        "tiempo_verde_min": "Green space", "tiempo_transporte_min": "Transport",
    }
    paleta_componentes = {
        "no2": "#C65D3B", "pm10": "#D98C6F", "pm25": "#E8B4A0", "ruido_db": "#8C4A3A",
        "tiempo_deporte_min": "#3D6B4F", "tiempo_bici_min": "#6B9C7A",
        "tiempo_verde_min": "#A8C9AE", "tiempo_transporte_min": "#2F6E8C",
    }

    fig_barras = go.Figure()
    direcciones_cortas = [r["direccion"][:30] for r in resultados]
    ibup_totales = [r["ibup"]["ibup"] or 1 for r in resultados]  # evitar división por 0

    for comp_key, comp_nombre in nombres_componentes.items():
        valores_aporte = []
        textos_pct = []
        for r, ibup_total in zip(resultados, ibup_totales):
            score = r["ibup"]["componentes"].get(comp_key)
            peso = r["ibup"]["pesos_usados"].get(comp_key, 0)
            aporte = (score * peso) if (score is not None) else 0
            valores_aporte.append(aporte)
            pct_sobre_total = (aporte / ibup_total * 100) if ibup_total else 0
            # Solo mostramos el % si el segmento es suficientemente grande
            # como para que el texto no se solape (umbral visual, no de datos)
            textos_pct.append(f"{pct_sobre_total:.0f}%" if pct_sobre_total >= 6 else "")

        if all(v == 0 for v in valores_aporte):
            continue  # este componente no tiene datos en ninguna dirección, no lo dibujamos

        fig_barras.add_trace(
            go.Bar(
                name=comp_nombre,
                x=direcciones_cortas,
                y=valores_aporte,
                text=textos_pct,
                textposition="inside",
                textfont=dict(color="white", size=11, family="Inter"),
                marker_color=paleta_componentes.get(comp_key, "#9a9088"),
                hovertemplate=f"{comp_nombre}: %{{y:.1f}} points<extra></extra>",
            )
        )

    fig_barras.update_layout(
        barmode="stack",
        height=400,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter"),
        yaxis=dict(title="IBUP (points contributed)", gridcolor="rgba(43,38,32,0.08)"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.3),
        uniformtext=dict(minsize=9, mode="hide"),
    )
    st.plotly_chart(fig_barras, width="stretch")
    st.caption("The percentages inside each segment show what share of that address's total IBUP comes from that component.")

    # --- Contexto detallado por dirección --------------------------------
    st.markdown("##### 🔎 Detailed context by address")
    city_averages = st.session_state.get("city_averages", {})
    for r in resultados:
        with st.container(border=True):
            st.markdown(
                f'<p style="font-family:\'Fraunces\',serif; font-weight:600; '
                f'font-size:1.25rem; margin-bottom:0.3rem;">📍 {r["direccion"][:70]}</p>',
                unsafe_allow_html=True,
            )

            cluster_info = r.get("cluster_info")
            if cluster_info:
                st.markdown(
                    f'<span class="cluster-badge">🏷️ {cluster_info["etiqueta"]}</span>',
                    unsafe_allow_html=True,
                )

            info_est = r.get("info_estacion")
            ruido_info = r.get("ruido_info")

            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                st.markdown("**Air quality**")
                if info_est:
                    st.markdown(f"🟢 {info_est['calidad_aire'] or 'No data'}")
                    st.caption(f"Station {info_est['nombre']}, {info_est['distancia_m']:.0f} m away")
                    no2_val = r["raw"].get("no2")
                    media_no2 = city_averages.get("no2")
                    if no2_val is not None and media_no2 is not None:
                        diff = no2_val - media_no2
                        comparacion = "below" if diff < 0 else "above"
                        st.caption(f"NO2: {no2_val:.0f} µg/m³ — {abs(diff):.0f} {comparacion} Valencia's average ({media_no2:.0f})")
                else:
                    st.caption("No data")
            with col_b:
                st.markdown("**Emission type**")
                st.markdown(f"🏭 {info_est['tipo_emision'] if info_est else 'No data'}")
            with col_c:
                st.markdown("**Zone type**")
                st.markdown(f"🏙️ {info_est['tipo_zona'] if info_est else 'No data'}")
            with col_d:
                st.markdown("**Estimated noise**")
                if ruido_info:
                    st.markdown(f"🔊 {ruido_info['ruido_db']:.0f} dB(A)")
                    st.caption(f"Near: {ruido_info['tramo_nombre']}")
                else:
                    st.caption("No data")

            zona_verde = r.get("zona_verde_detalle")
            if zona_verde:
                st.markdown("---")
                nombre_zona = zona_verde["nombre"]
                if not _es_valido(nombre_zona) or str(nombre_zona).lower() == "sin nombre":
                    nombre_zona = "Unnamed tree or green space"
                st.markdown(f"**🌳 Nearest green space**: {nombre_zona} ({zona_verde['minutos']} min on foot)")

                extra = zona_verde.get("extra", {})
                tipologia = extra.get("tipologia")
                fitness = extra.get("n_elementos_fitness")
                superficie = extra.get("sup_total")

                detalles = []
                if _es_valido(tipologia):
                    detalles.append(f"Type: {tipologia}")
                if _es_valido(fitness) and float(fitness) > 0:
                    detalles.append(f"🏋️ {int(float(fitness))} outdoor fitness elements")
                if _es_valido(superficie):
                    try:
                        detalles.append(f"📐 {float(superficie):,.0f} m² of surface area")
                    except (ValueError, TypeError):
                        pass

                if detalles:
                    st.markdown(" · ".join(detalles))
                else:
                    st.caption(
                        "This nearest green point is an individual tree from the "
                        "tree inventory, with no associated green space record."
                    )

            # --- Qué hay a 15 minutos andando -----------------------------
            conteo_verde = r.get("conteo_verde_15min")
            conteo_deporte = r.get("conteo_deporte_15min")
            if conteo_verde or conteo_deporte:
                st.markdown("---")
                st.markdown(
                    f"**🚶 Within 15 min on foot**: "
                    f"{conteo_verde['conteo'] if conteo_verde else 0} green spaces/trees, "
                    f"{conteo_deporte['conteo'] if conteo_deporte else 0} sports facilities"
                )

            # --- Transporte público ---------------------------------------
            transporte_cercano = r.get("transporte_cercano")
            if transporte_cercano:
                st.markdown("---")
                extra_transporte = transporte_cercano.get("extra", {})
                detalle_extra = []

                lineas = extra_transporte.get("lineas") or extra_transporte.get("linea")
                if _es_valido(lineas):
                    detalle_extra.append(f"Lines: {lineas}")

                bicis = extra_transporte.get("bicis_disponibles")
                huecos = extra_transporte.get("huecos_libres")
                if _es_valido(bicis) and _es_valido(huecos):
                    detalle_extra.append(f"🚲 {int(float(bicis))} bikes available now, {int(float(huecos))} free slots")

                texto_extra = " · " + " · ".join(detalle_extra) if detalle_extra else ""
                st.markdown(
                    f"**🚌 Nearest public transport**: {transporte_cercano['nombre']} "
                    f"({transporte_cercano['minutos']} min on foot){texto_extra}"
                )

            # --- Top 5 ---------------------------------------------------
            st.markdown("---")
            key_top5 = f"top5_{r['direccion'][:20]}_{r['lat']}_{r['lon']}"
            if st.button("🏆 View Top 5 nearby green spaces, sports, markets and health centres", key=f"btn_{key_top5}"):
                with st.spinner("Calculating rankings..."):
                    verde_points_top5 = load_geojson_points(
                        "zonas_verdes.geojson",
                        extra_props=["n_elementos_fitness", "sup_total", "tipologia"],
                    ) + load_geojson_points("arbolado.geojson")
                    deporte_points_top5 = load_instalaciones_deportivas()
                    mercados_points_top5 = load_mercados()
                    salud_points_top5 = load_centros_salud()

                    top5_verde = top_n_nearest(r["lat"], r["lon"], verde_points_top5, n=5)
                    top5_deporte = top_n_nearest(r["lat"], r["lon"], deporte_points_top5, n=5)
                    top5_mercados = top_n_nearest(r["lat"], r["lon"], mercados_points_top5, n=5)
                    top5_salud = top_n_nearest(r["lat"], r["lon"], salud_points_top5, n=5)
                    st.session_state[key_top5] = {
                        "verde": top5_verde,
                        "deporte": top5_deporte,
                        "mercados": top5_mercados,
                        "salud": top5_salud,
                    }

            if key_top5 in st.session_state:
                top5_data = st.session_state[key_top5]
                col_top_verde, col_top_deporte, col_top_mercados, col_top_salud = st.columns(4)
                with col_top_verde:
                    st.markdown("**🌳 Green spaces**")
                    if top5_data["verde"]:
                        for i, z in enumerate(top5_data["verde"], 1):
                            nombre_z = z["nombre"] if _es_valido(z["nombre"]) and str(z["nombre"]).lower() != "sin nombre" else "Unnamed tree/space"
                            st.markdown(f"{i}. {nombre_z} — {z['minutos']} min")
                    else:
                        st.caption("No data.")
                with col_top_deporte:
                    st.markdown("**🏋️ Sports**")
                    if top5_data["deporte"]:
                        for i, d in enumerate(top5_data["deporte"], 1):
                            st.markdown(f"{i}. {d['nombre']} — {d['minutos']} min")
                    else:
                        st.caption("No data.")
                with col_top_mercados:
                    st.markdown("**🛒 Markets**")
                    if top5_data["mercados"]:
                        for i, m in enumerate(top5_data["mercados"], 1):
                            st.markdown(f"{i}. {m['nombre']} — {m['minutos']} min")
                    else:
                        st.caption("No data.")
                with col_top_salud:
                    st.markdown("**🏥 Health centres**")
                    if top5_data["salud"]:
                        for i, s in enumerate(top5_data["salud"], 1):
                            st.markdown(f"{i}. {s['nombre']} — {s['minutos']} min")
                    else:
                        st.caption("No data available.")

    # --- Ranking narrativo automático --------------------------------------
    if len(resultados) >= 2:
        st.markdown("##### 🏅 Which one wins where?")

        COMPONENTE_NOMBRES = {
            "no2": "air quality (NO2)",
            "pm10": "air quality (PM10)",
            "pm25": "air quality (PM2.5)",
            "ruido_db": "quietness",
            "tiempo_deporte_min": "sports access",
            "tiempo_bici_min": "bike lane access",
            "tiempo_verde_min": "green space access",
            "tiempo_transporte_min": "public transport",
        }

        # Comparamos cada par de direcciones componente a componente, usando
        # los scores ya normalizados (0-100, donde más alto = mejor) en vez
        # de los valores crudos, porque así "menos ruido" y "más cerca del
        # parque" se comparan en la misma escala sin lógica especial por
        # componente.
        for i in range(len(resultados)):
            for j in range(i + 1, len(resultados)):
                r1, r2 = resultados[i], resultados[j]
                comp1 = r1["ibup"]["componentes"]
                comp2 = r2["ibup"]["componentes"]

                gana_r1, gana_r2 = [], []
                for clave, nombre_legible in COMPONENTE_NOMBRES.items():
                    v1, v2 = comp1.get(clave), comp2.get(clave)
                    if v1 is None or v2 is None:
                        continue
                    diferencia = v1 - v2
                    if abs(diferencia) < 3:
                        continue  # diferencia pequeña, no merece destacarse
                    if diferencia > 0:
                        gana_r1.append(nombre_legible)
                    else:
                        gana_r2.append(nombre_legible)

                nombre1 = r1["direccion"][:35]
                nombre2 = r2["direccion"][:35]

                with st.container(border=True):
                    col_izq, col_der = st.columns(2)
                    with col_izq:
                        st.markdown(f"**📍 {nombre1}** wins on:")
                        if gana_r1:
                            st.markdown(" · ".join(f"`{c}`" for c in gana_r1))
                        else:
                            st.caption("No clear advantages")
                    with col_der:
                        st.markdown(f"**📍 {nombre2}** wins on:")
                        if gana_r2:
                            st.markdown(" · ".join(f"`{c}`" for c in gana_r2))
                        else:
                            st.caption("No clear advantages")

    # --- Validación del modelo --------------------------------------------
    st.markdown("##### 🔬 Model validation")
    with st.expander("How do we know these calculations are reasonable, not made up?"):
        validacion = validate_cluster_grid()
        if validacion:
            col_v1, col_v2, col_v3 = st.columns(3)
            with col_v1:
                st.metric("Silhouette coefficient", f"{validacion['silhouette_score']:.2f}")
                st.caption("Measures how well separated the 4 neighbourhood types are (range -1 to +1; >0.25 is already reasonable for real urban data, not synthetic)")
            with col_v2:
                st.metric("Grid points analysed", validacion["n_puntos"])
                st.caption("~400-point grid covering the whole municipality of Valencia")
            with col_v3:
                st.metric("Neighbourhood types (k)", validacion["n_clusters"])
                st.caption("Chosen with the elbow method on K-means inertia")
        else:
            st.caption("Clustering validation not available (generate `barrios_clusters.geojson` first).")

        st.markdown(
            """
---
**Pollution interpolation (IDW)**: NO2/PM10/PM2.5 at any point is estimated by
weighting nearby real stations by the inverse square of their distance — a
standard method in geostatistics when there are few measurement points
(~11 stations in Valencia) and estimates are needed in areas without a sensor.

**Traffic-based noise estimate**: Valencia's official noise dataset only has 4
stations with no downloadable dB values. Instead, noise is inferred from
traffic intensity (IMV) at the nearest street segments, using a standard
logarithmic relationship in traffic acoustics (more vehicles/day → more dB)
with distance attenuation. It is an **estimate**, not a certified measurement —
that's why it's always labelled "estimated noise" in the interface.

**Real accessibility**: walking times are not straight-line distances — they
are calculated on Valencia's real street graph (OpenStreetMap), finding the
actual shortest pedestrian route between the point and each facility.
            """
        )

    # --- Tabla de valores crudos ------------------------------------------
    with st.expander("📐 View raw (non-normalised) numbers"):
        filas_tabla = []
        for r in resultados:
            fila = dict(r["raw"])
            fila["price_eur"] = r.get("precio")
            fila["value_score"] = r.get("value_score")
            filas_tabla.append(fila)
        tabla = pd.DataFrame(filas_tabla, index=[r["direccion"][:30] for r in resultados])
        st.dataframe(tabla)

    # --- Exportar a PDF ----------------------------------------------------
    st.markdown("##### 📄 Take the analysis with you")
    if st.button("Generate downloadable PDF report"):
        with st.spinner("Generating PDF..."):
            pdf_path = generar_informe_comparativo(
                resultados, st.session_state.get("perfil_usado", "")
            )
            with open(pdf_path, "rb") as f:
                st.session_state["pdf_bytes"] = f.read()
            st.session_state["pdf_name"] = pdf_path.name
        st.success("Report generated.")

    if "pdf_bytes" in st.session_state:
        st.download_button(
            "⬇️ Download PDF report",
            data=st.session_state["pdf_bytes"],
            file_name=st.session_state["pdf_name"],
            mime="application/pdf",
        )
