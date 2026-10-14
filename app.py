import os
import re
import itertools
import streamlit as st
from pathlib import Path
import docx
import pypdf
from groq import Groq

st.set_page_config(page_title="Portal Care24 - Cabina Médica", layout="wide", page_icon="🛡️")

CARPETA_DOCUMENTOS = str(Path(__file__).parent / "CONDICIONES")

# --- POOL DE CLAVES GROQ ---
API_KEYS = [
    "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",
    "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",
    "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"
]
API_KEYS = [k for k in API_KEYS if k.strip()]
key_cycle = itertools.cycle(API_KEYS) if API_KEYS else None

# --- LOGIN ASESORES ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.markdown("<h2 style='text-align: center; margin-top: 50px;'>🔐 Acceso Asesores - Care24</h2>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        clave = st.text_input("Ingrese contraseña de acceso:", type="password")
        if st.button("Ingresar al Portal", use_container_width=True):
            if clave == "Asesor2026":
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    st.stop()

# --- SEGMENTACIÓN LOCAL (0 TOKENS) ---
def segmentar_por_caracteristicas(texto):
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    caracteristicas = {
        "Beneficiarios y Límites de Edad": [],
        "Coberturas Médicas y Copagos": [],
        "Asistencias Adicionales (Hogar, Vial, Legal)": [],
        "Exclusiones y Restricciones": [],
        "Red / Ámbito Geográfico": [],
        "Procedimiento de Activación": []
    }
    patrones = {
        "Beneficiarios y Límites de Edad": re.compile(r"(beneficiar|titular|c[oó]nyuge|hijo|edad|dependiente|afiliad|parentesco)", re.IGNORECASE),
        "Coberturas Médicas y Copagos": re.compile(r"(copago|consulta|m[eé]dic|ambulancia|emergencia|hospital|farmacia|cl[ií]nica)", re.IGNORECASE),
        "Asistencias Adicionales (Hogar, Vial, Legal)": re.compile(r"(hogar|gasfiter|electric|vial|remolque|gr[uú]a|legal|asesor[ií]a|escolar)", re.IGNORECASE),
        "Exclusiones y Restricciones": re.compile(r"(exclui|no cubre|exclusi[oó]n|restricci[oó]n|carencia|preexistencia)", re.IGNORECASE),
        "Red / Ámbito Geográfico": re.compile(r"(cobertura geogr[aá]fica|nacional|lima|provincias|red de cl[ií]nicas|territor)", re.IGNORECASE),
        "Procedimiento de Activación": re.compile(r"(central telef[oó]nica|procedimiento|coordinaci[oó]n|reporte|reembolso|contacto)", re.IGNORECASE)
    }

    for linea in lineas:
        if len(linea) < 15:
            continue
        for cat, regex in patrones.items():
            if regex.search(linea):
                caracteristicas[cat].append(linea)
                break
    return caracteristicas

@st.cache_data(show_spinner="Indexando pólizas de Desktop\\CONDICIONES...")
def cargar_documentos(ruta_base_str):
    ruta_base = Path(ruta_base_str)
    docs = {}
    if not ruta_base.exists():
        return docs

    for archivo in ruta_base.glob("*"):
        if archivo.is_file() and archivo.suffix.lower() in [".docx", ".pdf"]:
            texto = ""
            try:
                if archivo.suffix.lower() == ".docx":
                    doc = docx.Document(archivo)
                    lineas = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
                    for tabla in doc.tables:
                        for fila in tabla.rows:
                            f_txt = " | ".join(c.text.strip() for c in fila.cells if c.text.strip())
                            if f_txt: lineas.append(f_txt)
                    texto = "\n".join(lineas)
                elif archivo.suffix.lower() == ".pdf":
                    lector = pypdf.PdfReader(archivo)
                    lineas = []
                    for pag in lector.pages:
                        t = pag.extract_text()
                        if t: lineas.append(t)
                    texto = "\n".join(lineas)

                if texto.strip():
                    nombre = archivo.stem.replace("CONDICIONADO", "").replace("Condicionado", "").strip(" -_")
                    docs[nombre or archivo.stem] = {
                        "archivo": archivo.name,
                        "texto_completo": texto,
                        "caracteristicas": segmentar_por_caracteristicas(texto)
                    }
            except Exception:
                pass
    return docs

polizas = cargar_documentos(CARPETA_DOCUMENTOS)

if not polizas:
    st.error(f"No se detectaron documentos en {CARPETA_DOCUMENTOS}")
    st.stop()

# --- CONSULTOR CON BALANCEO ---
MODELOS_GROQ = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]

def consultar_con_balanceo(mensajes, tokens=750):
    if not API_KEYS:
        return "⚠️ No hay claves de API configuradas."

    for _ in range(len(API_KEYS)):
        current_key = next(key_cycle)
        try:
            client = Groq(api_key=current_key)
            for mod in MODELOS_GROQ:
                try:
                    res = client.chat.completions.create(
                        messages=mensajes,
                        model=mod,
                        max_tokens=tokens,
                        temperature=0.1
                    )
                    return res.choices[0].message.content.strip()
                except Exception:
                    continue
        except Exception:
            continue
    return "Servicio momentáneamente ocupado. Por favor, reintente en unos segundos."

# --- ENCABEZADO ---
st.markdown("### 🛡️ Portal Integrado de Coberturas - Care24")
st.caption(f"📁 **{len(polizas)} pólizas indexadas** | 🔄 **{len(API_KEYS)} llaves API en balanceo activo**")

# --- DISTRIBUCIÓN EN 2 COLUMNAS (SPLIT VIEW) ---
col_izq, col_der = st.columns([1, 1], gap="medium")

# ==========================================
# LADO IZQUIERDO: DATOS Y CONDICIONADOS
# ==========================================
with col_izq:
    st.subheader("📋 Información de la Póliza")
    
    poliza_activa = st.selectbox("Seleccione Póliza / Seguro:", list(polizas.keys()), key="sel_poliza_izq")
    datos_activa = polizas[poliza_activa]
    st.caption(f"📄 Archivo fuente: `{datos_activa['archivo']}`")
    
    filtro_rapido = st.text_input("🔍 Filtro rápido (ej. copago, clínica, ambulancia, padres):", key="filtro_izq")

    if filtro_rapido.strip():
        st.markdown(f"**Coincidencias encontradas:**")
        coincidencias = [l for l in datos_activa["texto_completo"].split("\n") if filtro_rapido.lower() in l.lower()]
        if coincidencias:
            for c in coincidencias[:25]:
                st.info(c)
        else:
            st.warning("No se hallaron coincidencias con ese término.")
    else:
        cats = datos_activa["caracteristicas"]
        with st.expander("👥 Beneficiarios y Límites de Edad", expanded=True):
            if cats["Beneficiarios y Límites de Edad"]:
                for l in cats["Beneficiarios y Límites de Edad"][:15]: st.write(f"• {l}")
            else:
                st.write("Verificar en el texto general.")

        with st.expander("🩺 Coberturas Médicas y Copagos", expanded=True):
            if cats["Coberturas Médicas y Copagos"]:
                for l in cats["Coberturas Médicas y Copagos"][:18]: st.write(f"• {l}")
            else:
                st.write("Sin cláusulas médicas explícitas.")

        with st.expander("🚫 Exclusiones Críticas", expanded=False):
            if cats["Exclusiones y Restricciones"]:
                for l in cats["Exclusiones y Restricciones"][:15]: st.write(f"• {l}")
            else:
                st.write("Ver exclusiones generales.")

        with st.expander("📍 Red y Ámbito Geográfico", expanded=False):
            if cats["Red / Ámbito Geográfico"]:
                for l in cats["Red / Ámbito Geográfico"][:10]: st.write(f"• {l}")
            else:
                st.write("Cobertura estándar según condicionado.")

        with st.expander("🔧 Asistencias Adicionales (Hogar, Vial, Legal)", expanded=False):
            if cats["Asistencias Adicionales (Hogar, Vial, Legal)"]:
                for l in cats["Asistencias Adicionales (Hogar, Vial, Legal)"][:10]: st.write(f"• {l}")
            else:
                st.write("No incluye asistencias adicionales.")

        with st.expander("📄 Ver texto completo del documento", expanded=False):
            st.text_area("Contenido completo:", datos_activa["texto_completo"], height=300)

# ==========================================
# LADO DERECHO: CONSULTOR IA
# ==========================================
with col_der:
    st.subheader("🤖 Consultor IA en Vivo")
    
    col_scope, col_clean = st.columns([3, 1])
    with col_scope:
        alcance_chat = st.selectbox(
            "Consultar sobre:",
            [f"Solo: {poliza_activa}", "Todas las pólizas (Comparativa)"],
            key="scope_chat_der"
        )
    with col_clean:
        st.write("")
        if st.button("🗑️ Limpiar", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Entrada de pregunta
    pregunta = st.chat_input("Escribe tu duda (ej. ¿cubre a los padres? / copago ambulancia)")

    if pregunta:
        if alcance_chat.startswith("Solo:"):
            contexto = f"=== PÓLIZA: {poliza_activa} ===\n{datos_activa['texto_completo'][:20000]}"
        else:
            contexto = "\n\n".join([f"=== PÓLIZA: {k} ===\n{v['texto_completo'][:2800]}" for k, v in polizas.items()])

        prompt = f"""
        Eres el consultor experto de pólizas y asistencias de Care24.
        El usuario puede escribir con errores ortográficos, abreviaciones o faltas de tipificación.
        Interpreta su intención real y responde basándote estrictamente en los condicionados:

        CONDICIONADOS:
        {contexto}

        CONSULTA DEL ASESOR:
        {pregunta}

        REGLAS:
        1. Indica claramente si aplica la cobertura (SÍ / NO).
        2. Menciona copagos en Soles, topes de eventos y montos límite.
        3. Advierte exclusiones críticas si aplican.
        4. Usa viñetas directas para lectura rápida durante una llamada.
        """

        with st.spinner("Consultando reglas..."):
            resp = consultar_con_balanceo([
                {"role": "system", "content": "Asistente experto en seguros para call center médico. Tolerante a errores tipográficos."},
                {"role": "user", "content": prompt}
            ], tokens=750)

        # Se inserta al inicio para que la última pregunta aparezca arriba
        st.session_state.chat_history.insert(0, {"role": "assistant", "content": resp})
        st.session_state.chat_history.insert(0, {"role": "user", "content": pregunta})
        st.rerun()

    # Contenedor de mensajes (la más reciente arriba, anteriores abajo)
    chat_container = st.container()
    with chat_container:
        if not st.session_state.chat_history:
            st.info("Sin consultas activas. Escribe una pregunta abajo para comenzar.")
        else:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
