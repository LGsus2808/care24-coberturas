import os
import glob
import itertools
import streamlit as st
import gdown
from groq import Groq
import docx
import pypdf

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Care24 - Portal de Coberturas",
    page_icon="🛡️",
    layout="wide"
)

# ---------------------------------------------------------
# CONSTANTES Y CONFIGURACIÓN
# ---------------------------------------------------------
PASSWORD_CORRECTA = "Asesor2026"
DRIVE_FOLDER_ID = "1oHbjy3u0FSb0ctBhu2p8HPv1ubeO9_J5"
CARPETA_CONDICIONES = "CONDICIONES"

# ---------------------------------------------------------
# SEGURIDAD: CONTROL DE ACCESO
# ---------------------------------------------------------
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

def login():
    st.title("🛡️ Care24 - Acceso Seguro al Portal")
    st.markdown("Por favor, introduce tu contraseña de asesor para continuar.")
    
    with st.form("form_login"):
        clave = st.text_input("Contraseña:", type="password")
        submit = st.form_submit_button("Ingresar")
        if submit:
            if clave == PASSWORD_CORRECTA:
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta. Inténtalo nuevamente.")

if not st.session_state.autenticado:
    login()
    st.stop()

# ---------------------------------------------------------
# DESCARGA AUTOMÁTICA DE DOCUMENTOS DESDE GOOGLE DRIVE
# ---------------------------------------------------------
@st.cache_resource(show_spinner="📥 Sincronizando documentos de pólizas desde Google Drive...")
def sincronizar_documentos():
    os.makedirs(CARPETA_CONDICIONES, exist_ok=True)
    archivos = os.listdir(CARPETA_CONDICIONES)
    
    # Si la carpeta está vacía o no tiene archivos soportados, descargamos de Drive
    archivos_validos = [f for f in archivos if f.lower().endswith(('.pdf', '.docx', '.txt'))]
    if not archivos_validos:
        url_drive = f"https://drive.google.com/drive/folders/{DRIVE_FOLDER_ID}"
        gdown.download_folder(url_drive, output=CARPETA_CONDICIONES, quiet=True, use_cookies=False)
        
    return CARPETA_CONDICIONES

sincronizar_documentos()

# ---------------------------------------------------------
# LECTURA Y PROCESAMIENTO DE DOCUMENTOS
# ---------------------------------------------------------
def extraer_texto_archivo(ruta_archivo):
    texto = ""
    try:
        if ruta_archivo.lower().endswith(".docx"):
            doc = docx.Document(ruta_archivo)
            texto = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        elif ruta_archivo.lower().endswith(".pdf"):
            reader = pypdf.PdfReader(ruta_archivo)
            paginas = [page.extract_text() for page in reader.pages if page.extract_text()]
            texto = "\n".join(paginas)
        elif ruta_archivo.lower().endswith(".txt"):
            with open(ruta_archivo, "r", encoding="utf-8", errors="ignore") as f:
                texto = f.read()
    except Exception as e:
        return f"[Error al leer {os.path.basename(ruta_archivo)}: {e}]"
    return texto

@st.cache_data(show_spinner="Indexando pólizas y condiciones...")
def cargar_base_conocimiento():
    documentos = {}
    if os.path.exists(CARPETA_CONDICIONES):
        for nombre in sorted(os.listdir(CARPETA_CONDICIONES)):
            ruta = os.path.join(CARPETA_CONDICIONES, nombre)
            if os.path.isfile(ruta) and nombre.lower().endswith(('.pdf', '.docx', '.txt')):
                contenido = extraer_texto_archivo(ruta)
                if contenido:
                    documentos[nombre] = contenido
    return documentos

base_documentos = cargar_base_conocimiento()

# ---------------------------------------------------------
# GESTIÓN Y ROTACIÓN DE CLAVES DE GROQ
# ---------------------------------------------------------
def obtener_claves_groq():
    # Intenta obtenerlas de st.secrets primero
    if "GROQ_API_KEYS" in st.secrets:
        return list(st.secrets["GROQ_API_KEYS"])
    elif "GROQ_API_KEY" in st.secrets:
        return [st.secrets["GROQ_API_KEY"]]
    return []

api_keys = obtener_claves_groq()

if not api_keys:
    st.error("⚠️ No se encontraron las claves de Groq en los Secrets de Streamlit. Agrégalas en Settings > Secrets.")
    st.stop()

if "key_cycler" not in st.session_state:
    st.session_state.key_cycler = itertools.cycle(api_keys)

def consultar_groq(prompt_sistema, consulta_usuario):
    intentos = len(api_keys)
    while intentos > 0:
        current_key = next(st.session_state.key_cycler)
        try:
            cliente = Groq(api_key=current_key)
            respuesta = cliente.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": consulta_usuario}
                ],
                temperature=0.2,
                max_tokens=1500
            )
            return respuesta.choices[0].message.content
        except Exception:
            intentos -= 1
    return "❌ Error: Todas las claves de Groq alcanzaron su límite temporal de cuota. Por favor, reintenta en unos instantes."

# ---------------------------------------------------------
# INTERFAZ SPLIT-VIEW (DOS COLUMNAS)
# ---------------------------------------------------------
st.title("🛡️ Portal de Coberturas Care24")
col_info, col_chat = st.columns([1, 1], gap="medium")

# --- COLUMNA IZQUIERDA: VISOR DE COBERTURAS ---
with col_info:
    st.subheader("📋 Documentación de Pólizas")
    if not base_documentos:
        st.warning("No se encontraron documentos en la carpeta sincronizada.")
    else:
        doc_seleccionado = st.selectbox(
            "Selecciona una póliza para revisar:",
            options=list(base_documentos.keys())
        )
        if doc_seleccionado:
            st.info(f"Mostrando extracto de: **{doc_seleccionado}**")
            with st.container(height=520):
                st.text(base_documentos[doc_seleccionado])

# --- COLUMNA DERECHA: ASISTENTE INTELIGENTE CON IA ---
with col_chat:
    c_head1, c_head2 = st.columns([3, 1])
    with c_head1:
        st.subheader("💬 Consulta a la IA")
    with c_head2:
        if st.button("Limpiar chat"):
            st.session_state.mensajes = []
            st.rerun()

    if "mensajes" not in st.session_state:
        st.session_state.mensajes = []

    # Historial de mensajes
    with st.container(height=450):
        for m in st.session_state.mensajes:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    # Entrada de pregunta
    pregunta = st.chat_input("Escribe tu consulta sobre coberturas o requisitos...")
    if pregunta:
        # Registrar y mostrar mensaje de usuario
        st.session_state.mensajes.append({"role": "user", "content": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)

        # Preparar contexto relevante
        contexto_acumulado = ""
        for nombre, texto in base_documentos.items():
            contexto_acumulado += f"\n--- DOCUMENTO: {nombre} ---\n{texto[:1000]}\n"

        prompt_sistema = (
            "Eres el asistente oficial de asesoría de Care24. Tu objetivo es ayudar a los asesores respondiendo "
            "preguntas sobre coberturas, exclusiones, deducibles, clínicas y condiciones generales de los seguros basándote "
            "estrictamente en los siguientes documentos:\n\n"
            f"{contexto_acumulado}\n\n"
            "Instrucciones: Responde de forma clara, directa, profesional y estructurada. Cita siempre el nombre del plan o "
            "documento del cual extraes la información. Si la información no se encuentra en los documentos, indícalo explícitamente."
        )

        with st.chat_message("assistant"):
            with st.spinner("Analizando coberturas..."):
                respuesta_ia = consultar_groq(prompt_sistema, pregunta)
                st.markdown(respuesta_ia)
                st.session_state.mensajes.append({"role": "assistant", "content": respuesta_ia})