import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import io
import utm

# Configuración adaptada para móviles y PC
st.set_page_config(
    page_title="Syntro - Dashboard Climático UTM & Diario",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .main { padding: 0rem 0rem; }
    .stButton>button { width: 100%; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title("🌍 Syntro: Dashboard Climático (UTM, Diario y Multi-escala)")
st.markdown("Sistema de balance hídrico y teledetección (NASA POWER) sincronizado para **Móvil y PC**.")

# Barra Lateral (Sidebar) para Parámetros y Sistema de Coordenadas
with st.sidebar:
    st.header("⚙️ Configuración del Sitio")
    
    # Selector de Sistema de Coordenadas
    coord_system = st.radio("Sistema de Coordenadas", ("Geográficas (Lat/Lon)", "UTM (Metros)"))
    
    if coord_system == "UTM (Metros)":
        st.markdown("---")
        st.subheader("Parámetros UTM")
        easting = st.number_input("Easting (X)", value=400000.0, format="%.2f")
        northing = st.number_input("Northing (Y)", value=1000000.0, format="%.2f")
        zone_number = st.number_input("Zona UTM", value=19, min_value=1, max_value=60, step=1)
        hemisphere = st.selectbox("Hemisferio", ("Norte", "Sur"), index=0)
        
        # Conversión automática de UTM a Lat/Lon para la API de la NASA
        is_northern = (hemisphere == "Norte")
        lat_conv, lon_conv = utm.to_latlon(easting, northing, int(zone_number), northern=is_northern)
        
        lat = str(round(lat_conv, 6))
        lon = str(round(lon_conv, 6))
        st.info(f"📍 Lat/Lon calculada: {lat}, {lon}")
    else:
        st.markdown("---")
        st.subheader("Coordenadas Geográficas")
        lat = st.text_input("Latitud (- Sur)", value="-8.83")
        lon = st.text_input("Longitud (- Oeste)", value="-35.28")

    st.markdown("---")
    start_date = st.text_input("Fecha Inicio (AAAAMMDD)", value="20201001")
    end_date = st.text_input("Fecha Fin (AAAAMMDD)", value="20250331")
    cad = st.number_input("CAD del Suelo (mm)", value=100.0, min_value=10.0, max_value=500.0)
    
    run_btn = st.button("🚀 Cargar y Calcular", type="primary")

# Función con caché para optimizar la consulta a la API de la NASA
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
        with st.spinner("Conectando con NASA POWER y ejecutando calibración hídrica..."):
            df_raw, api_url = fetch_nasa_data(lat, lon, start_date, end_date)
            
            # Limpieza y conversión de fechas
            df_raw['Date'] = pd.to_datetime(df_raw['YEAR'].astype(str) + df_raw['DOY'].astype(str).str.zfill(3), format='%Y%j')
            df_raw['Fecha_Str'] = df_raw['Date'].dt.strftime('%Y-%m-%d')
            
            # Limpieza estricta de códigos -999
            variables = ['PRECTOTCORR', 'T2M_MAX', 'T2M_MIN', 'ALLSKY_SFC_SW_DWN', 'RH2M']
            for var in variables:
                if var in df_raw.columns:
                    df_raw[var] = df_raw[var].replace(-999, np.nan)
            df_raw = df_raw.dropna(subset=variables)

            # Cálculo de ETo por Hargreaves-Samani y Balance Hídrico Secuencial con CAD
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

            # Guardar dataset diario
            st.session_state['data_diario'] = df_raw

            # Agregaciones temporales superiores (Mensual, Trimestral, Anual)
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
            st.success("¡Calibración y procesamiento completados con éxito!")

    except Exception as e:
        st.error(f"Error en el procesamiento: {str(e)}")

# Sección de Visualización Interactiva Multi-escala (Incluyendo Diario)
if st.session_state.get('loaded', False):
    st.markdown("---")
    
    # Selector horizontal para cambiar entre Diario, Mensual, Trimestral y Anual
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

    # Construcción de gráficos múltiples optimizados para móvil y PC
    fig = make_subplots(
        rows=4, cols=1,
        subplot_titles=(
            f"Balance Hídrico ({escala}: Lluvia vs ETo)",
            f"Déficit y Excedente Hídrico ({escala})",
            f"Temperaturas Medias ({escala})",
            f"Humedad Relativa y Radiación ({escala})"
        ),
        vertical_spacing=0.07
    )

    # Fila 1: Lluvia y ETo
    fig.add_trace(go.Bar(x=dff[x_col], y=dff['PRECTOTCORR'], name="Lluvia (mm)", marker_color="royalblue"), row=1, col=1)
    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['ETo'], name="ETo (mm)", mode="lines+markers", marker_color="darkorange"), row=1, col=1)

    # Fila 2: Déficit y Excedente
    fig.add_trace(go.Bar(x=dff[x_col], y=dff['Deficit'], name="Déficit (mm)", marker_color="crimson"), row=2, col=1)
    fig.add_trace(go.Bar(x=dff[x_col], y=dff['Excedente'], name="Excedente (mm)", marker_color="forestgreen"), row=2, col=1)

    # Fila 3: Temperaturas
    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['T2M_MAX'], name="T. Máx (°C)", mode="lines+markers", marker_color="firebrick"), row=3, col=1)
    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['T2M_MIN'], name="T. Mín (°C)", mode="lines+markers", marker_color="navy"), row=3, col=1)

    # Fila 4: Humedad y Radiación
    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['RH2M'], name="Humedad Rel. (%)", mode="lines+markers", marker_color="purple"), row=4, col=1)
    fig.add_trace(go.Scatter(x=dff[x_col], y=dff['ALLSKY_SFC_SW_DWN'], name="Radiación (MJ/m²)", mode="lines+markers", marker_color="goldenrod"), row=4, col=1)

    fig.update_layout(
        height=950,
        template="plotly_white",
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10)),
        margin=dict(l=10, r=10, t=30, b=10)
    )

    st.plotly_chart(fig, use_container_width=True, config={'responsive': True, 'displayModeBar': False})

    # Sección colapsable para tablas y descargas en CSV
    with st.expander(f"📊 Ver Tabla de Datos ({escala}) y Descargar CSV"):
        st.dataframe(dff, use_container_width=True)
        csv_data = dff.to_csv(index=False).encode('utf-8')
        st.download_button(
            label=f"📥 Descargar CSV ({escala})",
            data=csv_data,
            file_name=f"clima_{escala.lower()}_{lat}_{lon}.csv",
            mime="text/csv"
        )
else:
    st.info("👆 Abre el menú lateral izquierdo para configurar tus coordenadas UTM o geográficas, y presiona **'Cargar y Calcular'**.")
