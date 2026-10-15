import os
import glob
import itertools
import shutil
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
# CONSTANTES Y CONFIGURACIÓN PROTEGIDA (SECRETS)
# ---------------------------------------------------------
CARPETA_CONDICIONES = "CONDICIONES"

# Validación de Secrets requeridos
if "ADMIN_PASSWORD" not in st.secrets:
    st.error("⚠️ Falta configurar 'ADMIN_PASSWORD' en Settings > Secrets de Streamlit.")
    st.stop()

if "DRIVE_FOLDER_ID" not in st.secrets:
    st.error("⚠️ Falta configurar 'DRIVE_FOLDER_ID' en Settings > Secrets de Streamlit.")
    st.stop()

PASSWORD_CORRECTA = st.secrets["ADMIN_PASSWORD"]
DRIVE_FOLDER_ID = st.secrets["DRIVE_FOLDER_ID"]

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
# BARRA LATERAL: PANEL DE GESTIÓN Y SINCRONIZACIÓN
# ---------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Configuración")
    st.markdown("Administra la base de pólizas sincronizadas desde Google Drive.")
    
    if st.button("🔄 Sincronizar / Actualizar Pólizas", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        if os.path.exists(CARPETA_CONDICIONES):
            shutil.rmtree(CARPETA_CONDICIONES)
        st.success("Caché limpiada. Descargando versiones actualizadas...")
        st.rerun()

    st.divider()
    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state.autenticado = False
        st.rerun()

# ---------------------------------------------------------
# DESCARGA AUTOMÁTICA DE DOCUMENTOS DESDE GOOGLE DRIVE
# ---------------------------------------------------------
@st.cache_resource(show_spinner="📥 Sincronizando documentos de pólizas desde Google Drive...")
def sincronizar_documentos():
    os.makedirs(CARPETA_CONDICIONES, exist_ok=True)
    archivos = os.listdir(CARPETA_CONDICIONES)
    
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
# GESTIÓN Y ROTACIÓN DE CLAVES DE GROQ (CON AUTO-SELECCIÓN)
# ---------------------------------------------------------
def obtener_claves_groq():
    if "GROQ_API_KEYS" in st.secrets:
        return [k.strip() for k in st.secrets["GROQ_API_KEYS"] if k.strip()]
    elif "GROQ_API_KEY" in st.secrets:
        return [st.secrets["GROQ_API_KEY"].strip()]
    return []

api_keys = obtener_claves_groq()

if not api_keys:
    st.error("⚠️ No se encontraron las claves de Groq en los Secrets de Streamlit. Agrégalas en Settings > Secrets.")
    st.stop()

def consultar_groq(prompt_sistema, consulta_usuario):
    ultimo_error = ""

    for current_key in api_keys:
        try:
            cliente = Groq(api_key=current_key.strip())

            modelos_disponibles = [m.id for m in cliente.models.list().data]

            # Excluir modelos no textuales o ultraligeros
            modelos_validos = [
                m for m in modelos_disponibles
                if "whisper" not in m.lower()
                and "orpheus" not in m.lower()
                and "vision" not in m.lower()
                and "guard" not in m.lower()
                and "1b" not in m.lower()
            ]

            prioridades = [
                "llama-3.3-70b-versatile",
                "llama3-70b-8192",
                "qwen-2.5-32b",
                "mistral-saba-24b",
                "llama-3.2-3b-preview"
            ]

            modelo_a_usar = None
            for cand in prioridades:
                if cand in modelos_validos:
                    modelo_a_usar = cand
                    break

            if not modelo_a_usar and modelos_validos:
                modelo_a_usar = modelos_validos[0]

            if not modelo_a_usar:
                raise Exception("No hay modelos de razonamiento disponibles en la cuenta.")

            respuesta = cliente.chat.completions.create(
                model=modelo_a_usar,
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": consulta_usuario}
                ],
                temperature=0.1,
                max_tokens=1500
            )
            return respuesta.choices[0].message.content

        except Exception as e:
            ultimo_error = str(e)
            continue

    return f"❌ Detalle técnico del error de Groq:\n\n`{ultimo_error}`"

# ---------------------------------------------------------
# INTERFAZ SPLIT-VIEW (DOS COLUMNAS)
# ---------------------------------------------------------
st.title("🛡️ Portal de Coberturas Care24")
col_info, col_chat = st.columns([1, 1], gap="medium")

# --- COLUMNA IZQUIERDA: VISOR DE COBERTURAS ---
with col_info:
    st.subheader("📋 Documentación de Pólizas")
    doc_seleccionado = None
    if not base_documentos:
        st.warning("No se encontraron documentos en la carpeta sincronizada.")
    else:
        doc_seleccionado = st.selectbox(
            "Selecciona una póliza para revisar:",
            options=list(base_documentos.keys()),
            key="selector_poliza"
        )
        if doc_seleccionado:
            st.info(f"Póliza activa para consultas: **{doc_seleccionado}**")
            with st.container(height=560):
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

    # Entrada de pregunta
    pregunta = st.chat_input("Escribe tu consulta sobre la póliza seleccionada...")
    if pregunta:
        st.session_state.mensajes.append({"role": "user", "content": pregunta})

        # Hasta 25,000 caracteres de la póliza activa
        if doc_seleccionado and doc_seleccionado in base_documentos:
            texto_poliza_activa = base_documentos[doc_seleccionado][:25000]
            contexto_especifico = (
                f"--- DOCUMENTO ACTIVO: {doc_seleccionado} ---\n"
                f"{texto_poliza_activa}\n"
            )
        else:
            contexto_especifico = "No hay póliza seleccionada."

        prompt_sistema = (
            "Eres el asistente especializado de Care24 para asesores de seguros. Tu tarea es extraer "
            "y resumir con total exactitud y rigor la información técnica de la póliza proporcionada.\n\n"
            f"DOCUMENTO ADJUNTO:\n{contexto_especifico}\n\n"
            "DIRECTIVAS ESTRICTAS:\n"
            "1. Responde basándote ÚNICAMENTE en la póliza activa seleccionada.\n"
            "2. Responde de forma directa, concisa y profesional. Prohibido saludar o repetir fórmulas de cortesía.\n"
            "3. Prohibido enumerar páginas sin contenido útil o generar frases en bucle.\n"
            "4. Cuando te pidan servicios, copagos, exámenes o eventos, presenta la información en una TABLA MARKDOWN "
            "con columnas delimitadas y saltos de línea (por ejemplo: | Servicio | Copago | Eventos / Límite | Detalle |).\n"
            "5. Sé preciso con montos en Soles (S/.) o Dólares, límites anuales y restricciones.\n"
            "6. Si un dato no figura explícitamente en el texto, indícalo claramente: 'El documento no especifica...' en vez de suponer."
        )

        with st.spinner(f"Analizando {doc_seleccionado}..."):
            respuesta_ia = consultar_groq(prompt_sistema, pregunta)
            st.session_state.mensajes.append({"role": "assistant", "content": respuesta_ia})
        st.rerun()

    # Agrupar mensajes en pares (pregunta + respuesta)
    pares_conversacion = []
    lista = st.session_state.mensajes
    i = 0
    while i < len(lista):
        if i + 1 < len(lista) and lista[i]["role"] == "user" and lista[i+1]["role"] == "assistant":
            pares_conversacion.append((lista[i], lista[i+1]))
            i += 2
        else:
            pares_conversacion.append((lista[i], None))
            i += 1

    # Renderizar pares ordenados de más reciente a más antiguo
    for user_msg, bot_msg in reversed(pares_conversacion):
        with st.chat_message(user_msg["role"]):
            st.markdown(user_msg["content"])
        if bot_msg:
            with st.chat_message(bot_msg["role"]):
                st.markdown(bot_msg["content"])
        st.divider()