import os
import shutil
import base64
import itertools
import requests
import pandas as pd
import streamlit as st
from groq import Groq

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ---------------------------------------------------------
LOGO_PATH = "logo.png"

st.set_page_config(
    page_title="Care24 - Consulta de Coberturas",
    page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "🏥",
    layout="wide"
)

# Estilos CSS personalizados para fondo suave, contraste de logo y tarjetas limpias
st.markdown("""
    <style>
    .stApp {
        background-color: #E6ECF2;
    }
    div[data-testid="stForm"] {
        background-color: #FFFFFF;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 4px 16px rgba(11, 79, 158, 0.08);
        border: 1px solid #D1DCE5;
    }
    .titulo-login {
        text-align: center;
        color: #0B4F9E;
        font-weight: 700;
        font-size: 1.75rem;
        margin-top: 0.5rem;
        margin-bottom: 0.2rem;
    }
    .subtitulo-login {
        text-align: center;
        color: #475569;
        font-size: 1rem;
        margin-bottom: 1.2rem;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# VARIABLES DE CONFIGURACIÓN Y SECRETS
# ---------------------------------------------------------
CARPETA_CONDICIONES = "CONDICIONES"
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
APPS_SCRIPT_URL = st.secrets.get("APPS_SCRIPT_URL", "")
USUARIOS_SHEET_ID = st.secrets.get("USUARIOS_SHEET_ID", "")
URL_SHEET_CSV = f"https://docs.google.com/spreadsheets/d/{USUARIOS_SHEET_ID}/export?format=csv"

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
# SINCRONIZACIÓN DE ARCHIVOS DESDE DRIVE (VÍA APPS SCRIPT)
# ---------------------------------------------------------
def sincronizar_documentos():
    """Descarga las carpetas de condicionados desde Drive a través de Google Apps Script."""
    if not os.path.exists(CARPETA_CONDICIONES) or not os.listdir(CARPETA_CONDICIONES):
        if DRIVE_FOLDER_ID and APPS_SCRIPT_URL:
            with st.spinner("Sincronizando coberturas desde Google Drive..."):
                try:
                    resp = requests.get(APPS_SCRIPT_URL, params={"folderId": DRIVE_FOLDER_ID}, timeout=45)
                    datos = resp.json()
                    if datos.get("status") != "ok":
                        st.error(f"Error en Drive Bridge: {datos.get('msg')}")
                        return

                    os.makedirs(CARPETA_CONDICIONES, exist_ok=True)
                    for item in datos.get("data", []):
                        ruta_poliza = os.path.join(CARPETA_CONDICIONES, item["poliza"])
                        os.makedirs(ruta_poliza, exist_ok=True)

                        for arch in item.get("archivos", []):
                            destino_dir = os.path.join(ruta_poliza, arch["subcarpeta"]) if arch["subcarpeta"] else ruta_poliza
                            os.makedirs(destino_dir, exist_ok=True)
                            ruta_archivo = os.path.join(destino_dir, arch["nombre"])

                            if arch["tipo"] == "txt":
                                with open(ruta_archivo, "w", encoding="utf-8") as f:
                                    f.write(arch["contenido"])
                            elif arch["tipo"] == "img":
                                with open(ruta_archivo, "wb") as f:
                                    f.write(base64.b64decode(arch["contenido_b64"]))
                except Exception as e:
                    st.error(f"Error al sincronizar con Drive: {e}")
        else:
            st.warning("Configura DRIVE_FOLDER_ID y APPS_SCRIPT_URL en st.secrets.")

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
# PANTALLA DE AUTENTICACIÓN CENTRADA Y COMPACTA
# ---------------------------------------------------------
def login():
    # Centrar el bloque de login usando columnas laterales de espaciado
    _, col_centro, _ = st.columns([1.2, 1.4, 1.2])

    with col_centro:
        # Mostrar logo centrado
        if os.path.exists(LOGO_PATH):
            _, col_logo, _ = st.columns([1, 1.5, 1])
            with col_logo:
                st.image(LOGO_PATH, use_container_width=True)

        st.markdown('<div class="titulo-login">Care24 - Consulta de Coberturas</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitulo-login">Acceso al Portal Corporativo</div>', unsafe_allow_html=True)

        tab_login, tab_recuperar = st.tabs(["🔑 Iniciar Sesión", "📩 Olvidé mi Contraseña"])

        with tab_login:
            with st.form("form_login"):
                usuario_in = st.text_input("Usuario:").strip().lower()
                password_in = st.text_input("Contraseña:", type="password").strip()
                boton_ingreso = st.form_submit_button("Ingresar", use_container_width=True, type="primary")

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
                                st.error("⛔ Tu cuenta se encuentra INACTIVA. Contacta al administrador.")
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
            st.markdown("##### 1. Solicitar Código de Verificación")
            st.caption("El código tiene una validez de 5 minutos. Si solicitas uno nuevo, el anterior se anula.")
            
            correo_recup = st.text_input("Correo Gmail registrado:").strip().lower()
            if st.button("Enviar Código de Verificación", use_container_width=True):
                if not correo_recup:
                    st.warning("Por favor ingresa tu correo electrónico.")
                else:
                    df_u = obtener_base_usuarios()
                    if df_u.empty or correo_recup not in df_u["CORREO"].values:
                        st.error("❌ Correo no registrado, por favor coloque el correo Gmail correcto.")
                    else:
                        datos_user = df_u[df_u["CORREO"] == correo_recup].iloc[0]
                        if datos_user["ESTADO"] != "ACTIVO":
                            st.error("⛔ Esta cuenta está INACTIVA. Contacta al administrador.")
                        else:
                            with st.spinner("Generando y enviando código..."):
                                res = enviar_peticion_apps_script({
                                    "accion": "solicitar_codigo",
                                    "correo": correo_recup
                                })
                                if res.get("status") == "ok":
                                    st.success("✅ Código enviado a tu correo. Tienes 5 minutos para usarlo.")
                                else:
                                    st.error(f"❌ {res.get('msg', 'Error al procesar solicitud')}")

            st.divider()
            st.markdown("##### 2. Confirmar Código y Nueva Contraseña")
            with st.form("form_cambio_clave"):
                codigo_in = st.text_input("Código de 6 dígitos:").strip()
                nueva_clave = st.text_input("Nueva contraseña:", type="password").strip()
                confirmar_clave = st.text_input("Confirmar nueva contraseña:", type="password").strip()
                boton_guardar = st.form_submit_button("Actualizar Contraseña", use_container_width=True, type="primary")

                if boton_guardar:
                    if not correo_recup or not codigo_in or not nueva_clave:
                        st.warning("Completa tu correo, el código y la nueva contraseña.")
                    elif nueva_clave != confirmar_clave:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        df_u = obtener_base_usuarios()
                        if df_u.empty or correo_recup not in df_u["CORREO"].values:
                            st.error("❌ Correo no registrado, por favor coloque el correo Gmail correcto.")
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

if not st.session_state.autenticado:
    login()
    st.stop()

# ---------------------------------------------------------
# EXTRACCIÓN DE IMÁGENES CON GROQ VISION (CACHEADO)
# ---------------------------------------------------------
@st.cache_data(show_spinner=False)
def transcribir_imagen_con_groq(ruta_imagen, mod_time):
    """
    Usa un modelo Vision activo de Groq para leer tablas y textos de imágenes.
    Se cachea por fecha de modificación (mod_time) para no gastar tokens repetidamente.
    """
    if not pool_keys:
        return "[Imagen no procesada: sin claves API]"

    ext = os.path.splitext(ruta_imagen)[1].lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"

    try:
        with open(ruta_imagen, "rb") as img_file:
            base64_img = base64.b64encode(img_file.read()).decode("utf-8")
    except Exception as e:
        return f"[Error abriendo imagen {os.path.basename(ruta_imagen)}: {e}]"

    prompt_vision = (
        "Transcribe con total precisión y fidelidad todos los textos, números, montos, "
        "porcentajes, deducibles, copagos y tablas que aparecen en esta imagen de una póliza de seguros. "
        "Si hay tablas, estructúralas claramente en formato Markdown. No inventes ni omitas ningún dato."
    )

    for _ in range(len(GROQ_KEYS)):
        key = next(pool_keys)
        cliente = Groq(api_key=key)
        try:
            modelos = cliente.models.list().data
            modelos_vision = [
                m.id for m in modelos
                if "vision" in m.id.lower() or "scout" in m.id.lower() or "maverick" in m.id.lower()
            ]
            if not modelos_vision:
                modelos_vision = ["meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.2-90b-vision-preview"]

            for mod_v in modelos_vision[:2]:
                try:
                    resp = cliente.chat.completions.create(
                        model=mod_v,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt_vision},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/{ext};base64,{base64_img}"}
                                    }
                                ]
                            }
                        ],
                        temperature=0.0
                    )
                    return resp.choices[0].message.content
                except Exception:
                    continue
        except Exception:
            continue

    return f"[Aviso: No se pudo extraer texto visual de {os.path.basename(ruta_imagen)}]"

# ---------------------------------------------------------
# DETECCIÓN Y LECTURA JERÁRQUICA DE PÓLIZAS
# ---------------------------------------------------------
def cargar_polizas_disponibles():
    """Detecta las carpetas de pólizas que contienen al menos un TXT o imagen."""
    polizas = {}
    extensiones_img = (".png", ".jpg", ".jpeg", ".webp")
    if os.path.exists(CARPETA_CONDICIONES):
        for item in sorted(os.listdir(CARPETA_CONDICIONES)):
            ruta_item = os.path.join(CARPETA_CONDICIONES, item)
            if os.path.isdir(ruta_item):
                tiene_contenido = False
                for root_dir, _, files in os.walk(ruta_item):
                    if any(f.lower().endswith(".txt") or f.lower().endswith(extensiones_img) for f in files):
                        tiene_contenido = True
                        break
                if tiene_contenido:
                    polizas[item] = ruta_item
    return polizas

def leer_contenido_poliza(ruta_carpeta):
    """
    Lee primero la carpeta ACTUALIZACION (TXT + Imágenes) y luego el condicionado base
    (TXT + imagenes_revision), marcando la prioridad absoluta de vigencia.
    """
    bloque_actualizacion = []
    bloque_base = []
    extensiones_img = (".png", ".jpg", ".jpeg", ".webp")

    # 1. PRIORIDAD MÁXIMA: Carpeta ACTUALIZACION
    for nombre_sub in sorted(os.listdir(ruta_carpeta)):
        ruta_sub = os.path.join(ruta_carpeta, nombre_sub)
        if os.path.isdir(ruta_sub) and nombre_sub.strip().upper() == "ACTUALIZACION":
            for archivo in sorted(os.listdir(ruta_sub)):
                ruta_arch = os.path.join(ruta_sub, archivo)
                if not os.path.isfile(ruta_arch):
                    continue

                if archivo.lower().endswith(".txt"):
                    with open(ruta_arch, "r", encoding="utf-8", errors="ignore") as f:
                        bloque_actualizacion.append(
                            f"=== [ACTUALIZACIÓN VIGENTE - ARCHIVO: {archivo}] ===\n{f.read().strip()}"
                        )
                elif archivo.lower().endswith(extensiones_img):
                    mod_time = os.path.getmtime(ruta_arch)
                    texto_img = transcribir_imagen_con_groq(ruta_arch, mod_time)
                    bloque_actualizacion.append(
                        f"=== [ACTUALIZACIÓN VIGENTE - IMAGEN/TABLA: {archivo}] ===\n{texto_img}"
                    )

    # 2. CONDICIONADO GENERAL BASE (TXT en la raíz de la póliza)
    for archivo in sorted(os.listdir(ruta_carpeta)):
        ruta_arch = os.path.join(ruta_carpeta, archivo)
        if os.path.isfile(ruta_arch) and archivo.lower().endswith(".txt"):
            if archivo.lower() == "actualizacion.txt":
                with open(ruta_arch, "r", encoding="utf-8", errors="ignore") as f:
                    bloque_actualizacion.append(
                        f"=== [ACTUALIZACIÓN VIGENTE - {archivo}] ===\n{f.read().strip()}"
                    )
            else:
                with open(ruta_arch, "r", encoding="utf-8", errors="ignore") as f:
                    bloque_base.append(
                        f"--- [CONDICIONADO GENERAL BASE: {archivo}] ---\n{f.read().strip()}"
                    )

    # 3. TABLAS DEL CONDICIONADO BASE (Carpeta imagenes_revision)
    ruta_imgs_rev = os.path.join(ruta_carpeta, "imagenes_revision")
    if os.path.isdir(ruta_imgs_rev):
        for archivo in sorted(os.listdir(ruta_imgs_rev)):
            ruta_arch = os.path.join(ruta_imgs_rev, archivo)
            if os.path.isfile(ruta_arch) and archivo.lower().endswith(extensiones_img):
                mod_time = os.path.getmtime(ruta_arch)
                texto_img = transcribir_imagen_con_groq(ruta_arch, mod_time)
                bloque_base.append(
                    f"--- [TABLA DEL CONDICIONADO BASE ({archivo})] ---\n{texto_img}"
                )

    resultado = []
    if bloque_actualizacion:
        resultado.append(
            "******************************************************************\n"
            "SECCIÓN 1: DATA ACTUALIZADA (MÁXIMA PRIORIDAD Y VIGENCIA ACTUAL)\n"
            "******************************************************************\n" +
            "\n\n".join(bloque_actualizacion)
        )
    if bloque_base:
        resultado.append(
            "******************************************************************\n"
            "SECCIÓN 2: CONDICIONADO GENERAL BASE (APLICAR SOLO SI NO FUE MODIFICADO ARRIBA)\n"
            "******************************************************************\n" +
            "\n\n".join(bloque_base)
        )

    return "\n\n".join(resultado)

# ---------------------------------------------------------
# MOTOR DE CONSULTA CON JERARQUÍA Y FILTRO DE MODELOS GROQ
# ---------------------------------------------------------
def consultar_ia(contexto, pregunta):
    """Consulta modelos de texto activos en Groq aplicando jerarquía estricta de actualización."""
    if not pool_keys:
        return "Error: No hay claves API de Groq configuradas en st.secrets."

    contexto_seguro = contexto[:18000]

    prompt_sistema = (
        "Eres el asistente especializado en coberturas de salud y seguros de Care24. "
        "Responde de forma clara, directa y fundamentada a las dudas del asesor.\n\n"
        "REGLA SUPREMA DE VIGENCIA Y JERARQUÍA:\n"
        "1. El contexto está dividido en 'SECCIÓN 1: DATA ACTUALIZADA' y 'SECCIÓN 2: CONDICIONADO GENERAL BASE'.\n"
        "2. Si existe cualquier contradicción entre ambas secciones (por ejemplo, precios, copagos, deducibles, "
        "topes de edad o condiciones de acceso), la 'SECCIÓN 1: DATA ACTUALIZADA' SIEMPRE tiene la verdad absoluta y anula lo que diga la SECCIÓN 2.\n"
        "3. Menciona brevemente si el dato proviene de la actualización vigente cuando aplique.\n"
        "4. Si el dato consultado no aparece en ninguna sección, indícalo claramente sin inventar."
    )

    ultimo_error = ""
    for _ in range(len(GROQ_KEYS)):
        key = next(pool_keys)
        cliente = Groq(api_key=key)
        try:
            lista_modelos = cliente.models.list().data
            palabras_permitidas = ("llama", "qwen", "mixtral", "gemma")
            palabras_excluidas = ("whisper", "guard", "tts", "orpheus", "vision", "audio", "prompt")

            ids_activos = [
                m.id for m in lista_modelos
                if any(p in m.id.lower() for p in palabras_permitidas)
                and not any(e in m.id.lower() for e in palabras_excluidas)
            ]
            ids_activos.sort(key=lambda x: (
                0 if "70b" in x.lower() else (1 if "32b" in x.lower() or "versatile" in x.lower() else 2),
                x
            ))
        except Exception as e:
            ultimo_error = f"Error validando clave API: {e}"
            continue

        for modelo in ids_activos[:4]:
            try:
                respuesta = cliente.chat.completions.create(
                    model=modelo,
                    messages=[
                        {"role": "system", "content": prompt_sistema},
                        {"role": "user", "content": f"Documentación de la póliza:\n{contexto_seguro}\n\nPregunta del asesor:\n{pregunta}"}
                    ],
                    temperature=0.0
                )
                return respuesta.choices[0].message.content
            except Exception as e:
                ultimo_error = f"[{modelo}] {e}"
                continue

    return f"❌ No se pudo procesar la consulta en Groq. Detalle técnico: {ultimo_error}"

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

    with st.sidebar:
        if os.path.exists(LOGO_PATH):
            st.image(LOGO_PATH, use_container_width=True)
            st.divider()

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

    if st.session_state.modo_vista == "admin" and st.session_state.usuario_info.get("rol") == "ADMIN":
        panel_administrador()
    else:
        col_head_logo, col_head_txt = st.columns([0.8, 5])
        with col_head_logo:
            if os.path.exists(LOGO_PATH):
                st.image(LOGO_PATH, width=110)
        with col_head_txt:
            st.title("Care24 - Consulta de Coberturas")
            st.caption("Asistente corporativo con inteligencia artificial para consulta inmediata de condicionados y actualizaciones.")

        if not dict_polizas:
            st.warning("No se encontraron carpetas de pólizas disponibles en el directorio local.")
            return

        poliza_seleccionada = st.selectbox(
            "Selecciona la póliza o producto a consultar:",
            options=list(dict_polizas.keys())
        )

        col_doc, col_chat = st.columns([1, 1], gap="medium")

        with col_doc:
            st.markdown("### 📄 Contenido Consolidado")
            ruta_poliza = dict_polizas[poliza_seleccionada]
            with st.spinner("Consolidando texto y transcribiendo tablas visuales..."):
                contenido_completo = leer_contenido_poliza(ruta_poliza)
            st.text_area("Vista previa (Sección 1: Actualizaciones > Sección 2: Base):", contenido_completo, height=520)

        with col_chat:
            col_titulo, col_btn_limpiar = st.columns([3, 1])
            with col_titulo:
                st.markdown("### 💬 Asistente IA")
            with col_btn_limpiar:
                if st.button("🧹 Limpiar", use_container_width=True):
                    st.session_state.historial_chat = []
                    st.rerun()

            if prompt_usuario := st.chat_input("Escribe tu consulta sobre la póliza..."):
                with st.spinner("Analizando actualizaciones vigentes y condicionado..."):
                    respuesta_ia = consultar_ia(contenido_completo, prompt_usuario)
                    st.session_state.historial_chat.insert(0, {
                        "pregunta": prompt_usuario,
                        "respuesta": respuesta_ia
                    })
                    st.rerun()

            for turno in st.session_state.historial_chat:
                with st.chat_message("user"):
                    st.write(turno["pregunta"])
                with st.chat_message("assistant"):
                    st.write(turno["respuesta"])
                st.divider()

app_principal()