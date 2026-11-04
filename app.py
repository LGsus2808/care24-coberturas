import os
import shutil
import json
import itertools
import requests
import pandas as pd
import streamlit as st
import gdown
from groq import Groq

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Care24 - Consulta de Coberturas",
    page_icon="🛡️",
    layout="wide"
)

# ---------------------------------------------------------
# VARIABLES DE CONFIGURACIÓN Y SECRETS
# ---------------------------------------------------------
CARPETA_CONDICIONES = "CONDICIONES"
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
APPS_SCRIPT_URL = st.secrets.get("APPS_SCRIPT_URL", "")
USUARIOS_SHEET_ID = st.secrets.get("USUARIOS_SHEET_ID", "")
URL_SHEET_CSV = f"https://docs.google.com/spreadsheets/d/{USUARIOS_SHEET_ID}/export?format=csv"

# Configuración de pool de claves Groq
GROQ_KEYS = st.secrets.get("GROQ_API_KEYS", [])
if isinstance(GROQ_KEYS, str):
    GROQ_KEYS = [GROQ_KEYS]
pool_keys = itertools.cycle(GROQ_KEYS) if GROQ_KEYS else None

# ---------------------------------------------------------
# GESTIÓN DE SESIÓN
# ---------------------------------------------------------
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_info" not in st.session_state:
    st.session_state.usuario_info = {}
if "historial_chat" not in st.session_state:
    st.session_state.historial_chat = []
if "modo_vista" not in st.session_state:
    st.session_state.modo_vista = "chat"

# ---------------------------------------------------------
# SINCRONIZACIÓN DE ARCHIVOS DESDE DRIVE
# ---------------------------------------------------------
def sincronizar_documentos():
    """Descarga o actualiza las carpetas de condicionados desde Google Drive."""
    if not os.path.exists(CARPETA_CONDICIONES) or not os.listdir(CARPETA_CONDICIONES):
        if DRIVE_FOLDER_ID:
            with st.spinner("Sincronizando coberturas desde Google Drive..."):
                try:
                    url = f"https://drive.google.com/drive/folders/{DRIVE_FOLDER_ID}"
                    gdown.download_folder(url, output=CARPETA_CONDICIONES, quiet=True, use_cookies=False)
                except Exception as e:
                    st.error(f"Error al descargar archivos desde Drive: {e}")
        else:
            st.warning("DRIVE_FOLDER_ID no configurado en st.secrets.")

# ---------------------------------------------------------
# CONEXIÓN CON GOOGLE SHEETS Y APPS SCRIPT
# ---------------------------------------------------------
@st.cache_data(ttl=30)
def obtener_base_usuarios():
    """Descarga los datos actualizados de usuarios desde Google Sheets."""
    try:
        df = pd.read_csv(URL_SHEET_CSV)
        df["USUARIO"] = df["USUARIO"].astype(str).str.strip().str.lower()
        df["PASSWORD"] = df["PASSWORD"].astype(str).str.strip()
        df["ROL"] = df["ROL"].astype(str).str.strip().str.upper()
        df["ESTADO"] = df["ESTADO"].astype(str).str.strip().str.upper()
        df["CORREO"] = df["CORREO"].astype(str).str.strip().str.lower()
        df["NOMBRE_APELLIDO"] = df["NOMBRE_APELLIDO"].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Error al leer base de datos de usuarios: {e}")
        return pd.DataFrame()

def enviar_peticion_apps_script(payload):
    """Envía peticiones POST al backend en Google Apps Script."""
    try:
        resp = requests.post(APPS_SCRIPT_URL, json=payload, timeout=15)
        return resp.json()
    except Exception as e:
        return {"status": "error", "msg": f"Fallo de conexión: {e}"}

# ---------------------------------------------------------
# PANTALLA DE AUTENTICACIÓN Y RECUPERACIÓN
# ---------------------------------------------------------
def login():
    st.title("🛡️ Care24 - Consulta de Coberturas")
    st.subheader("Acceso al Portal")
    
    tab_login, tab_recuperar = st.tabs(["🔑 Iniciar Sesión", "📩 Olvidé mi Contraseña"])

    with tab_login:
        with st.form("form_login"):
            usuario_in = st.text_input("Usuario:").strip().lower()
            password_in = st.text_input("Contraseña:", type="password").strip()
            boton_ingreso = st.form_submit_button("Ingresar", use_container_width=True)

            if boton_ingreso:
                if not usuario_in or not password_in:
                    st.warning("Por favor completa todos los campos.")
                else:
                    df_u = obtener_base_usuarios()
                    user_match = df_u[df_u["USUARIO"] == usuario_in]

                    if user_match.empty:
                        st.error("❌ Usuario o contraseña incorrectos.")
                    else:
                        datos = user_match.iloc[0]
                        if datos["ESTADO"] != "ACTIVO":
                            st.error("⛔ Tu cuenta se encuentra deshabilitada. Contacta al administrador.")
                        elif datos["PASSWORD"] == password_in:
                            st.session_state.autenticado = True
                            st.session_state.usuario_info = {
                                "usuario": datos["USUARIO"],
                                "nombre": datos["NOMBRE_APELLIDO"],
                                "correo": datos["CORREO"],
                                "rol": datos["ROL"]
                            }
                            st.success(f"Bienvenido, {datos['NOMBRE_APELLIDO']}")
                            st.rerun()
                        else:
                            st.error("❌ Usuario o contraseña incorrectos.")

    with tab_recuperar:
        st.markdown("#### Restablecer Contraseña")
        st.write("Recibirás un código de 6 dígitos en tu correo corporativo.")
        
        correo_recup = st.text_input("Ingresa tu correo registrado:").strip().lower()
        if st.button("Enviar Código de Verificación"):
            if correo_recup:
                with st.spinner("Generando y enviando código..."):
                    res = enviar_peticion_apps_script({
                        "accion": "solicitar_codigo",
                        "correo": correo_recup
                    })
                    if res.get("status") == "ok":
                        st.success("✅ Código enviado a tu correo corporativo. Revisa tu bandeja de entrada o spam.")
                    else:
                        st.error(f"❌ {res.get('msg', 'Error al procesar solicitud')}")
            else:
                st.warning("Escribe tu correo electrónico.")

        st.divider()
        st.markdown("#### Confirmar Código y Nueva Contraseña")
        with st.form("form_cambio_clave"):
            codigo_in = st.text_input("Código de 6 dígitos:").strip()
            nueva_clave = st.text_input("Nueva contraseña:", type="password").strip()
            confirmar_clave = st.text_input("Confirmar nueva contraseña:", type="password").strip()
            boton_guardar = st.form_submit_button("Actualizar Contraseña")

            if boton_guardar:
                if not correo_recup or not codigo_in or not nueva_clave:
                    st.warning("Completa tu correo, el código y la nueva contraseña.")
                elif nueva_clave != confirmar_clave:
                    st.error("Las contraseñas no coinciden.")
                else:
                    with st.spinner("Validando código y actualizando..."):
                        res = enviar_peticion_apps_script({
                            "accion": "cambiar_password",
                            "correo": correo_recup,
                            "codigo": codigo_in,
                            "nueva_password": nueva_clave
                        })
                        if res.get("status") == "ok":
                            st.success("✅ Contraseña actualizada correctamente. Ya puedes iniciar sesión.")
                            st.cache_data.clear()
                        else:
                            st.error(f"❌ {res.get('msg', 'Error al actualizar contraseña')}")

# Detener ejecución si no está autenticado
if not st.session_state.autenticado:
    login()
    st.stop()

# ---------------------------------------------------------
# FUNCIONES DEL MOTOR DE COBERTURAS Y CHAT
# ---------------------------------------------------------
def cargar_polizas_disponibles():
    """Detecta las carpetas de pólizas dentro del directorio CONDICIONES."""
    polizas = {}
    if os.path.exists(CARPETA_CONDICIONES):
        for item in os.listdir(CARPETA_CONDICIONES):
            ruta_item = os.path.join(CARPETA_CONDICIONES, item)
            if os.path.isdir(ruta_item):
                archivos = os.listdir(ruta_item)
                archivos_txt = [a for a in archivos if a.endswith(".txt")]
                if archivos_txt:
                    polizas[item] = ruta_item
    return polizas

def leer_contenido_poliza(ruta_carpeta):
    """
    Lee los documentos de la póliza priorizando actualizacion.txt sobre el condicionado base.
    """
    textos = []
    ruta_actualizacion = os.path.join(ruta_carpeta, "actualizacion.txt")
    
    # 1. Prioridad: Actualizaciones o cláusulas agregadas
    if os.path.exists(ruta_actualizacion):
        try:
            with open(ruta_actualizacion, "r", encoding="utf-8", errors="ignore") as f:
                textos.append("--- [DOCUMENTO PRIORITARIO: ACTUALIZACIÓN / CLÁUSULA MODIFICATORIA] ---\n" + f.read())
        except Exception as e:
            st.warning(f"Error leyendo actualización: {e}")

    # 2. Documentos base
    for archivo in os.listdir(ruta_carpeta):
        if archivo.endswith(".txt") and archivo.lower() != "actualizacion.txt":
            ruta_completa = os.path.join(ruta_carpeta, archivo)
            try:
                with open(ruta_completa, "r", encoding="utf-8", errors="ignore") as f:
                    textos.append(f"--- [CONDICIONADO BASE: {archivo}] ---\n" + f.read())
            except Exception as e:
                st.warning(f"Error leyendo {archivo}: {e}")

    return "\n\n".join(textos)

def consultar_ia(contexto, pregunta):
    """Envía la consulta a Llama 3 en Groq rotando API Keys."""
    if not pool_keys:
        return "Error: No hay claves API de Groq configuradas en st.secrets."

    prompt_sistema = (
        "Eres el asistente especializado en coberturas de salud y seguros de Care24. "
        "Tu objetivo es responder de forma clara, directa y fundamentada a las dudas del asesor. "
        "REGLA CRÍTICA: Si en el contexto existe una sección marcada como '[DOCUMENTO PRIORITARIO: ACTUALIZACIÓN]', "
        "sus términos reemplazan o tienen precedencia absoluta sobre el condicionado base. "
        "Si la respuesta no se encuentra en el texto proporcionado, indica amablemente que dicha información no figura en las pólizas analizadas."
    )

    intentos = len(GROQ_KEYS)
    for _ in range(intentos):
        key = next(pool_keys)
        try:
            cliente = Groq(api_key=key)
            respuesta = cliente.chat.completions.create(
                model="llama3-70b-8192",
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": f"Contexto de la póliza:\n{contexto}\n\nPregunta del asesor:\n{pregunta}"}
                ],
                temperature=0.1
            )
            return respuesta.choices[0].message.content
        except Exception:
            continue
    return "Error: Todos los tokens de API de Groq alcanzaron su cuota de servicio o fallaron. Intenta nuevamente más tarde."

# ---------------------------------------------------------
# PANEL DE ADMINISTRADOR
# ---------------------------------------------------------
def panel_administrador():
    st.title("🛠️ Panel de Control - Administración Care24")
    st.write("Gestiona el acceso y roles de los asesores en tiempo real.")

    df_u = obtener_base_usuarios()
    if df_u.empty:
        st.warning("No se pudo cargar la base de datos de usuarios.")
        return

    # Visualización de usuarios activos e inactivos
    columnas_vista = ["USUARIO", "NOMBRE_APELLIDO", "CORREO", "ROL", "ESTADO"]
    st.dataframe(df_u[columnas_vista], use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Cambiar Estado de Acceso")
        df_u["SELECTOR"] = df_u["NOMBRE_APELLIDO"] + " (" + df_u["USUARIO"] + ")"
        seleccion = st.selectbox("Selecciona al asesor:", df_u["SELECTOR"].tolist())

        fila_sel = df_u[df_u["SELECTOR"] == seleccion].iloc[0]
        usuario_sel = fila_sel["USUARIO"]
        estado_actual = fila_sel["ESTADO"]
        
        st.info(f"Estado registrado: **{estado_actual}**")
        nuevo_estado = st.radio("Nuevo estado de cuenta:", ["ACTIVO", "INACTIVO"], horizontal=True)

        if st.button("Guardar Estado de Acceso", use_container_width=True):
            with st.spinner("Actualizando estado en base de datos..."):
                res = enviar_peticion_apps_script({
                    "accion": "modificar_estado",
                    "usuario": usuario_sel,
                    "nuevo_estado": nuevo_estado
                })
                if res.get("status") == "ok":
                    st.success(f"Estado de {usuario_sel} cambiado a {nuevo_estado}.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Error al actualizar estado.")

    with col2:
        st.markdown("### Registrar Nuevo Asesor")
        nuevo_nombre = st.text_input("Nombre y Apellido:")
        nuevo_user = st.text_input("Usuario (ej. juan.perez):").strip().lower()
        nuevo_correo = st.text_input("Correo corporativo:").strip().lower()
        nueva_clave = st.text_input("Contraseña temporal:", type="password").strip()
        nuevo_rol = st.selectbox("Rol:", ["ASESOR", "ADMIN"])

        if st.button("Crear Usuario", use_container_width=True):
            if nuevo_nombre and nuevo_user and nuevo_correo and nueva_clave:
                with st.spinner("Registrando nuevo asesor..."):
                    res = enviar_peticion_apps_script({
                        "accion": "crear_usuario",
                        "usuario": nuevo_user,
                        "nombre_apellido": nuevo_nombre,
                        "correo": nuevo_correo,
                        "password": nueva_clave,
                        "rol": nuevo_rol
                    })
                    if res.get("status") == "ok":
                        st.success(f"Asesor {nuevo_nombre} registrado correctamente.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Error al registrar nuevo usuario.")
            else:
                st.warning("Completa todos los campos obligatorios.")

# ---------------------------------------------------------
# INTERFAZ PRINCIPAL DE CONSULTA Y CHATBOT
# ---------------------------------------------------------
def app_principal():
    sincronizar_documentos()
    dict_polizas = cargar_polizas_disponibles()

    # Barra lateral
    with st.sidebar:
        st.subheader("👤 Sesión Activa")
        st.write(f"**Asesor:** {st.session_state.usuario_info.get('nombre')}")
        st.write(f"**Rol:** {st.session_state.usuario_info.get('rol')}")

        if st.session_state.usuario_info.get("rol") == "ADMIN":
            st.divider()
            st.subheader("⚙️ Navegación")
            modo = st.radio("Selecciona vista:", ["Consulta de Coberturas", "Panel Administrador"])
            if modo == "Panel Administrador":
                st.session_state.modo_vista = "admin"
            else:
                st.session_state.modo_vista = "chat"

        st.divider()
        if st.button("🔄 Forzar Recarga de Documentos", use_container_width=True):
            st.cache_data.clear()
            if os.path.exists(CARPETA_CONDICIONES):
                shutil.rmtree(CARPETA_CONDICIONES)
            st.success("Carpetas limpias. Descargando versiones más recientes...")
            st.rerun()

        st.divider()
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.usuario_info = {}
            st.session_state.historial_chat = []
            st.rerun()

    # Despliegue de vistas
    if st.session_state.modo_vista == "admin" and st.session_state.usuario_info.get("rol") == "ADMIN":
        panel_administrador()
    else:
        st.title("🛡️ Care24 - Consulta de Coberturas")
        st.caption("Asistente corporativo con inteligencia artificial para consulta inmediata de condicionados.")

        if not dict_polizas:
            st.warning("No se encontraron carpetas de pólizas disponibles en el directorio local.")
            return

        poliza_seleccionada = st.selectbox(
            "Selecciona la póliza o producto a consultar:",
            options=list(dict_polizas.keys())
        )

        col_doc, col_chat = st.columns([1, 1], gap="medium")

        # Visualizador de texto de póliza
        with col_doc:
            st.markdown("### 📄 Contenido del Condicionado")
            ruta_poliza = dict_polizas[poliza_seleccionada]
            contenido_completo = leer_contenido_poliza(ruta_poliza)
            st.text_area("Texto consolidado (Base + Actualizaciones):", contenido_completo, height=520)

        # Chatbot con IA
        with col_chat:
            st.markdown("### 💬 Asistente IA")

            for msj in st.session_state.historial_chat:
                with st.chat_message(msj["role"]):
                    st.write(msj["content"])

            if prompt_usuario := st.chat_input("Escribe tu consulta sobre la póliza..."):
                st.session_state.historial_chat.append({"role": "user", "content": prompt_usuario})
                with st.chat_message("user"):
                    st.write(prompt_usuario)

                with st.chat_message("assistant"):
                    with st.spinner("Analizando condicionado y cláusulas prioritarias..."):
                        respuesta_ia = consultar_ia(contenido_completo, prompt_usuario)
                        st.write(respuesta_ia)
                        st.session_state.historial_chat.append({"role": "assistant", "content": respuesta_ia})

# Ejecución de la aplicación
app_principal()