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
            cliente = Groq(api_key=current_key)
            
            lista_modelos = [m.id for m in cliente.models.list().data]
            
            preferidos = [
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "llama-3.1-8b-instant",
                "llama-3.2-3b-preview",
                "llama-3.2-1b-preview",
                "mixtral-8x7b-32768"
            ]
            
            modelo_elegido = None
            for pref in preferidos:
                if pref in lista_modelos:
                    modelo_elegido = pref
                    break
                    
            if not modelo_elegido and lista_modelos:
                modelo_elegido = lista_modelos[0]

            respuesta = cliente.chat.completions.create(
                model=modelo_elegido,
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": consulta_usuario}
                ],
                temperature=0.2,
                max_tokens=1000
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
        # Registrar pregunta del usuario
        st.session_state.mensajes.append({"role": "user", "content": pregunta})

        # Armar contexto enfocado en la póliza activa
        if doc_seleccionado and doc_seleccionado in base_documentos:
            texto_poliza_activa = base_documentos[doc_seleccionado][:5000]
            contexto_especifico = (
                f"--- PÓLIZA PRINCIPAL SELECCIONADA POR EL ASESOR: {doc_seleccionado} ---\n"
                f"{texto_poliza_activa}\n"
            )
        else:
            contexto_especifico = "No hay ninguna póliza seleccionada actualmente."

        prompt_sistema = (
            "Eres el asistente oficial de asesoría de Care24. Tu objetivo es resolver las consultas de los asesores "
            "sobre coberturas, servicios, exclusiones, montos y condiciones generales.\n\n"
            f"El usuario tiene actualmente abierta y seleccionada la siguiente póliza en su pantalla:\n"
            f"{contexto_especifico}\n\n"
            "INSTRUCCIONES CLAVE:\n"
            "1. Asume siempre por defecto que la consulta del usuario se refiere a la póliza seleccionada en pantalla.\n"
            "2. No preguntes al usuario a qué póliza se refiere salvo que te pida explícitamente comparar con otra.\n"
            "3. Responde directamente con la lista de servicios, coberturas o límites basándote en el documento proporcionado.\n"
            "4. Sé claro, directo y profesional."
        )

        with st.spinner(f"Consultando información de {doc_seleccionado}..."):
            respuesta_ia = consultar_groq(prompt_sistema, pregunta)
            st.session_state.mensajes.append({"role": "assistant", "content": respuesta_ia})
        st.rerun()

    # Mostrar mensajes ordenados del más reciente al más antiguo
    for m in reversed(st.session_state.mensajes):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])