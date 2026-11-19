import os
import shutil
import base64
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
    """Detecta las carpetas de pólizas que contienen al menos un TXT o carpeta ACTUALIZACION."""
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

    # Recorte seguro (~4,500 tokens) garantizando que SECCIÓN 1 (ACTUALIZACIÓN) entre siempre primero
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
        st.title("🛡️ Care24 - Consulta de Coberturas")
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
            st.markdown("### 💬 Asistente IA")

            for msj in st.session_state.historial_chat:
                with st.chat_message(msj["role"]):
                    st.write(msj["content"])

            if prompt_usuario := st.chat_input("Escribe tu consulta sobre la póliza..."):
                st.session_state.historial_chat.append({"role": "user", "content": prompt_usuario})
                with st.chat_message("user"):
                    st.write(prompt_usuario)

                with st.chat_message("assistant"):
                    with st.spinner("Analizando actualizaciones vigentes y condicionado..."):
                        respuesta_ia = consultar_ia(contenido_completo, prompt_usuario)
                        st.write(respuesta_ia)
                        st.session_state.historial_chat.append({"role": "assistant", "content": respuesta_ia})

app_principal()