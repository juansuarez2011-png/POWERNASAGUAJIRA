import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import utm
import folium
from folium.plugins import Geocoder
from streamlit_folium import st_folium

# Configuración adaptada para PC y Móvil
st.set_page_config(
    page_title="Syntro - Dashboard Climático Satelital",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .main { padding: 0rem 0rem; }
    .stButton>button { width: 100%; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title("🛰 Syntro: Dashboard Climático Satelital Avanzado")
st.markdown("Sistema profesional de balance hídrico sincronizado para **PC y Móvil**.")

# Inicializar estado en sesión
if 'lat' not in st.session_state:
    st.session_state['lat'] = 8.0000
if 'lon' not in st.session_state:
    st.session_state['lon'] = -66.0000
if 'zoom' not in st.session_state:
    st.session_state['zoom'] = 6

# --- FRAGMENTO AISLADO PARA EL MAPA Y COORDENADAS (CERO PESTAÑAZOS) ---
@st.fragment
def render_map_and_coords():
    with st.sidebar:
        st.header("⚙️ Configuración y Coordenadas")
        coord_input_mode = st.radio("Sistema de Coordenadas", ("Geográficas (Lat/Lon)", "UTM (Metros)"))
        
        if coord_input_mode == "Geográficas (Lat/Lon)":
            lat_input = st.number_input("Latitud (- Sur)", value=float(st.session_state['lat']), format="%.6f", step=0.0001)
            lon_input = st.number_input("Longitud (- Oeste)", value=float(st.session_state['lon']), format="%.6f", step=0.0001)
            
            if lat_input != st.session_state['lat'] or lon_input != st.session_state['lon']:
                st.session_state['lat'] = lat_input
                st.session_state['lon'] = lon_input
        else:
            try:
                init_e, init_n, init_z, init_l = utm.from_latlon(st.session_state['lat'], st.session_state['lon'])
                init_north = st.session_state['lat'] >= 0
            except:
                init_e, init_n, init_z, init_north = 400000.0, 1000000.0, 19, True

            easting_input = st.number_input("Easting (X)", value=float(init_e), format="%.2f", step=10.0)
            northing_input = st.number_input("Northing (Y)", value=float(init_n), format="%.2f", step=10.0)
            zone_input = st.number_input("Zona UTM", value=int(init_z), min_value=1, max_value=60, step=1)
            hemi_input = st.selectbox("Hemisferio", ("Norte", "Sur"), index=0 if init_north else 1)
            
            try:
                l_conv, lo_conv = utm.to_latlon(easting_input, northing_input, int(zone_input), northern=(hemi_input=="Norte"))
                l_conv = round(l_conv, 6)
                lo_conv = round(lo_conv, 6)
                
                if l_conv != st.session_state['lat'] or lo_conv != st.session_state['lon']:
                    st.session_state['lat'] = l_conv
                    st.session_state['lon'] = lo_conv
            except Exception as e:
                st.error("Error al convertir UTM.")

        st.markdown("---")
        st.text_input("Fecha Inicio (AAAAMMDD)", value="20201001", key="f_start")
        st.text_input("Fecha Fin (AAAAMMDD)", value="20250331", key="f_end")
        st.number_input("CAD del Suelo (mm)", value=100.0, min_value=10.0, max_value=500.0, key="f_cad")

    st.markdown("---")
    st.info("💡 **Mapa Híbrido:** Haz clic en cualquier punto del mapa para actualizar la posición al instante.")

    m = folium.Map(
        location=[st.session_state['lat'], st.session_state['lon']], 
        zoom_start=st.session_state['zoom'],
        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr='Google Híbrido'
    )

    Geocoder(position='topright', themed=True, placeholder='Buscar municipio, estado o sector...', add_marker=True).add_to(m)

    folium.Marker(
        [st.session_state['lat'], st.session_state['lon']],
        popup=f"Lat: {st.session_state['lat']}, Lon: {st.session_state['lon']}",
        icon=folium.Icon(color="red", icon="crosshairs", prefix="fa")
    ).add_to(m)

    map_data = st_folium(
        m, 
        height=420, 
        use_container_width=True, 
        key="mapa_fijo_hibrido",
        returned_objects=["last_clicked", "zoom"]
    )

    if map_data:
        if map_data.get("zoom"):
            st.session_state['zoom'] = map_data["zoom"]
        if map_data.get("last_clicked"):
            clicked_lat = map_data["last_clicked"]["lat"]
            clicked_lon = map_data["last_clicked"]["lng"]
            if clicked_lat != st.session_state['lat'] or clicked_lon != st.session_state['lon']:
                st.session_state['lat'] = round(clicked_lat, 6)
                st.session_state['lon'] = round(clicked_lon, 6)
                st.rerun()

render_map_and_coords()

# Obtener parámetros de la barra lateral
start_date = st.session_state.get("f_start", "20201001")
end_date = st.session_state.get("f_end", "20250331")
cad = st.session_state.get("f_cad", 100.0)

lat_val = st.session_state['lat']
lon_val = st.session_state['lon']

try:
    easting, northing, zone_number, zone_letter = utm.from_latlon(lat_val, lon_val)
    hemisphere = "Norte" if lat_val >= 0 else "Sur"
except:
    easting, northing, zone_number, hemisphere = 0.0, 0.0, 19, "Norte"

st.markdown("### 📍 Coordenadas Actuales del Sitio")
col_c1, col_c2, col_c3 = st.columns(3)
col_c1.metric("🌍 Geográficas (Lat / Lon)", f"{lat_val}, {lon_val}")
col_c2.metric("📐 UTM (Easting / Northing)", f"{easting:,.1f} E, {northing:,.1f} N")
col_c3.metric("🌐 Zona UTM y Hemisferio", f"Zona {zone_number} ({hemisphere})")

run_btn = st.button("🚀 Cargar y Calcular Balance Hídrico", type="primary")

@st.cache_data(show_spinner=True)
def fetch_nasa_data(lat, lon, start, end):
    url = (
        f"https://power.larc.nasa.gov/api/temporal/daily/point?"
        f"parameters=PRECTOTCORR,T2M_MAX,T2M_MIN,ALLSKY_SFC_SW_DWN,RH2M&"
        f"community=AG&latitude={lat}&longitude={lon}&start={start}&end={end}&format=CSV"
    )
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Error HTTP {response.status_code} al consultar la API NASA POWER.")
    
    lines = response.text.splitlines()
    data_idx = 0
    for idx, line in enumerate(lines):
        if "-END HEADER-" in line:
            data_idx = idx + 1
            break
    
    df = pd.read_csv(io.StringIO("\n".join(lines[data_idx:])))
    return df, url

if run_btn:
    try:
        with st.spinner("Conectando con NASA POWER y procesando balance hídrico..."):
            df_raw, api_url = fetch_nasa_data(str(lat_val), str(lon_val), start_date, end_date)
            
            df_raw['Date'] = pd.to_datetime(df_raw['YEAR'].astype(str) + df_raw['DOY'].astype(str).str.zfill(3), format='%Y%j')
            df_raw['Fecha_Str'] = df_raw['Date'].dt.strftime('%Y-%m-%d')
            
            variables = ['PRECTOTCORR', 'T2M_MAX', 'T2M_MIN', 'ALLSKY_SFC_SW_DWN', 'RH2M']
            for var in variables:
                if var in df_raw.columns:
                    df_raw[var] = df_raw[var].replace(-999, np.nan)
            df_raw = df_raw.dropna(subset=variables)

            t_mean = (df_raw['T2M_MAX'] + df_raw['T2M_MIN']) / 2.0
            t_range = np.maximum(df_raw['T2M_MAX'] - df_raw['T2M_MIN'], 0.1)
            ra_mm = df_raw['ALLSKY_SFC_SW_DWN'] / 2.45
            df_raw['ETo'] = 0.0023 * ra_mm * (t_mean + 17.8) * np.sqrt(t_range)

            swc = [cad]
            deficit, excedente = [], []
            for i in range(len(df_raw)):
                p = df_raw['PRECTOTCORR'].iloc[i]
                eto = df_raw['ETo'].iloc[i]
                cur = swc[-1] + (p - eto)
                if cur > cad:
                    exc = cur - cad
                    cur = cad
                    def_v = 0.0
                elif cur < 0:
                    def_v = abs(cur)
                    cur = 0.0
                    exc = 0.0
                else:
                    def_v, exc = 0.0, 0.0
                swc.append(cur)
                deficit.append(def_v)
                excedente.append(exc)

            df_raw['SWC'] = swc[1:]
            df_raw['Deficit'] = deficit
            df_raw['Excedente'] = excedente

            st.session_state['data_diario'] = df_raw

            df_raw['Mes'] = df_raw['Date'].dt.to_period('M').astype(str)
            df_raw['Trimestre'] = df_raw['Date'].dt.year.astype(str) + "-Q" + df_raw['Date'].dt.quarter.astype(str)
            df_raw['Anio'] = df_raw['Date'].dt.year.astype(str)

            def agg(period_col):
                return df_raw.groupby(period_col).agg({
                    'PRECTOTCORR': 'sum',
                    'ETo': 'sum',
                    'Deficit': 'sum',
                    'Excedente': 'sum',
                    'T2M_MAX': 'mean',
                    'T2M_MIN': 'mean',
                    'RH2M': 'mean',
                    'ALLSKY_SFC_SW_DWN': 'mean'
                }).reset_index()

            st.session_state['data_mensual'] = agg('Mes')
            st.session_state['data_trimestral'] = agg('Trimestre')
            st.session_state['data_anual'] = agg('Anio')
            st.session_state['loaded'] = True
            st.success("¡Cálculo hídrico completado con éxito!")

    except Exception as e:
        st.error(f"Error en el procesamiento: {str(e)}")

if st.session_state.get('loaded', False):
    st.markdown("---")
    
    escala = st.radio(
        "📅 Escala Temporal de Análisis:",
        ("Diario", "Mensual", "Trimestral", "Anual"),
        horizontal=True
    )

    if escala == "Diario":
        dff = st.session_state['data_diario']
        x_col = 'Fecha_Str'
    elif escala == "Mensual":
        dff = st.session_state['data_mensual']
        x_col = 'Mes'
    elif escala == "Trimestral":
        dff = st.session_state['data_trimestral']
        x_col = 'Trimestre'
    else:
        dff = st.session_state['data_anual']
        x_col = 'Anio'

    fig = make_subplots(
        rows=4, cols=1,
        subplot_titles=(
            f"Balance Hídrico ({escala}: Lluvia vs ETo)",
            f"Déficit y Excedente Hídrico ({escala})",
            f"Temperaturas Medias ({escala})",
            f"Humedad Relativa y Radiación ({escala})"
        ),
        vertical_spacing=0.1
    )

    fig.add_trace(go.Bar(x=dff[x_col], y=dff['PRECTOTCORR'], name="Lluvia (mm)", marker_color="#3399ff"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['ETo'], name="ETo (mm)", mode="lines+markers", marker_color="#ff9933"), row=1, col=1)

    fig.add_trace(go.Bar(x=dff[x_col], y=dff['Deficit'], name="Déficit (mm)", marker_color="#ff4d4d"), row=2, col=1)
    fig.add_trace(go.Bar(x=dff[x_col], y=dff['Excedente'], name="Excedente (mm)", marker_color="#2ecc71"), row=2, col=1)

    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['T2M_MAX'], name="T. Máx (°C)", mode="lines+markers", marker_color="#e74c3c"), row=3, col=1)
    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['T2M_MIN'], name="T. Mín (°C)", mode="lines+markers", marker_color="#3498db"), row=3, col=1)

    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['RH2M'], name="Humedad Rel. (%)", mode="lines+markers", marker_color="#9b59b6"), row=4, col=1)
    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['ALLSKY_SFC_SW_DWN'], name="Radiación (MJ/m²)", mode="lines+markers", marker_color="#f1c40f"), row=4, col=1)

    # Leyenda posicionada de forma limpia ABAJO de las gráficas para evitar cualquier superposición
    fig.update_layout(
        height=1050,
        template="plotly_dark",
        legend=dict(
            orientation="h", 
            y=-0.12, 
            x=0, 
            font=dict(size=11, color="white"),
            bgcolor="rgba(0,0,0,0)"
        ),
        margin=dict(l=20, r=20, t=50, b=80)
    )

    st.plotly_chart(fig, use_container_width=True, config={'responsive': True, 'displayModeBar': False})

    with st.expander(f"📊 Ver Tabla de Datos ({escala}) y Descargar CSV"):
        st.dataframe(dff, use_container_width=True)
        csv_data = dff.to_csv(index=False).encode('utf-8')
        st.download_button(
            label=f"📥 Descargar CSV ({escala})",
            data=csv_data,
            file_name=f"clima_{escala.lower()}_{lat_val}_{lon_val}.csv",
            mime="text/csv"
        )
else:
    st.info("👆 Configura tu ubicación en el mapa y presiona **'Cargar y Calcular Balance Hídrico'**.")
