import argparse
import re
import sys
from office_service import OfficeService
from retriever import KnowledgeRetriever

class SmartFiraBot:
    def __init__(self):
        try:
            self.office_srv = OfficeService()
            self.retriever = KnowledgeRetriever()
        except Exception as e:
            print(f"❌ Error al inicializar: {e}")
            sys.exit(1)

    def is_location_query(self, text: str) -> bool:
        """Detecta si la consulta busca una sucursal, teléfono o dirección."""
        triggers = [
            r"\boficinas?\b", r"\bagencias?\b", r"\bsucursales?\b", r"\bdonde\s+(?:estan|queda|esta)\b",
            r"\bdónde\s+(?:están|queda|está)\b", r"\bubicaci[oó]n\b", r"\bdirecci[oó]n\b",
            r"\btelefonos?\b", r"\bteléfonos?\b", r"\bcontacto\b", r"\bsoy\s+de\b", r"\bvivo\s+en\b"
        ]
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in triggers)

    def format_knowledge_response(self, doc: dict, user_query: str) -> str:
        """
        Reconstruye el texto en oraciones completas y gramaticalmente válidas.
        """
        title = doc.get("title", "Información Institucional FIRA")
        raw_content = doc.get("content", "")
        official_url = doc.get("official_url")

        # 1. Unir todo el contenido eliminando saltos de línea artificiales
        clean_full_text = " ".join(line.strip() for line in raw_content.splitlines() if line.strip())
        
        # 2. Dividir en oraciones reales (que terminan en punto y espacio)
        raw_sentences = re.split(r'(?<=[.!?])\s+', clean_full_text)
        
        # Filtrar oraciones que no sean menúes ni fragmentos de tabla
        sentences = [
            s.strip() for s in raw_sentences 
            if len(s.strip()) > 45 
            and not re.search(r"^\d+[\s\d\.,\$\/]+$", s.strip())
            and not s.lower().startswith("seleccione")
            and not s.lower().startswith("loading")
        ]

        query_tokens = set(re.findall(r'\b[a-záéíóúñ]{3,}\b', user_query.lower()))

        # 3. Ponderar oraciones según relevancia con la duda del usuario
        scored_sentences = []
        for s in sentences:
            s_lower = s.lower()
            score = sum(3 for w in query_tokens if w in s_lower)
            if any(term in s for term in ["%", "$", "UDIS", "crédito", "financiamiento", "apoyo", "tasa"]):
                score += 1
            scored_sentences.append((score, s))

        scored_sentences.sort(key=lambda x: x[0], reverse=True)

        # Seleccionar las 2 o 3 mejores oraciones completas
        top_sentences = [s for score, s in scored_sentences[:3] if score > 0]
        if not top_sentences and sentences:
            top_sentences = sentences[:2]

        body = "\n\n".join(f"• {s}" for s in top_sentences)

        response = f"📋 **{title}**\n\n{body}\n\n"

        if official_url:
            response += f"🔗 **Más información y enlaces oficiales:** {official_url}\n\n"

        response += (
            "💡 *FIRA opera como banca de segundo piso a través de intermediarios financieros "
            "autorizados (bancos, cajas de ahorro y SOFOMES). Acude a tu agencia FIRA local "
            "para conocer los requisitos específicos de tu proyecto.*"
        )
        return response

    def respond(self, user_message: str) -> str:
        msg = user_message.strip()
        if not msg:
            return "¿En qué podemos orientarte hoy? Pregúntame sobre oficinas, créditos o programas de apoyo."

        # -------------------------------------------------------------
        # 1. RUTA DE BOLSA DE TRABAJO / VACANTES
        # -------------------------------------------------------------
        job_triggers = [r"\bempleo\b", r"\bvacantes?\b", r"\btrabajo\b", r"\bbolsa\s+de\s+trabajo\b", r"\breclutamiento\b"]
        if any(re.search(p, msg, re.IGNORECASE) for p in job_triggers):
            return (
                "💼 **Bolsa de Trabajo y Vacantes en FIRA:**\n\n"
                "Puedes consultar las convocatorias laborales vigentes, plazas disponibles y los requisitos "
                "de postulación directamente en nuestro portal de empleo institucional:\n\n"
                "🔗 **Portal de Vacantes FIRA:** https://www.fira.gob.mx/VacantesUserDtoXML/Requisitos.jsp"
            )

        # -------------------------------------------------------------
        # 2. RUTA GEOGRÁFICA / OFICINAS / TELÉFONOS
        # -------------------------------------------------------------
        if self.is_location_query(msg):
            office, loc_name = self.office_srv.find_by_location_query(msg)
            if office:
                return self.office_srv.format_office_response(office, loc_name)
            else:
                return (
                    "🏢 **Directorio de Oficinas FIRA:**\n\n"
                    "Contamos con oficinas y agencias en todo México. Para darte la dirección "
                    "y el teléfono local de atención, por favor **indícanos tu municipio o estado** "
                    "(por ejemplo: *'oficina en Saltillo'* o *'soy de Colima'*).\n\n"
                    "🌐 Directorio nacional: https://www.fira.gob.mx/OficinasXML/OficinasDireccion.jsp"
                )

        # -------------------------------------------------------------
        # 3. RUTA DE CONOCIMIENTO (Recuperación sobre los 40+ XMLs)
        # -------------------------------------------------------------
        results = self.retriever.retrieve(msg, top_k=1)
        
        if results and results[0][0] > 1.2:
            top_doc = results[0][1]
            return self.format_knowledge_response(top_doc, msg)

        # -------------------------------------------------------------
        # 4. MENÚ DE TRIAJE
        # -------------------------------------------------------------
        return (
            "👋 Hola. Para orientarte mejor en tu proyecto, indícanos el tema de tu interés:\n\n"
            "• **Oficinas y Teléfonos:** Escribe tu municipio o estado (ej. *'oficina en Michoacán'*).\n"
            "• **Programas Específicos:** Escribe tu cultivo o programa (ej. *'arroz'*, *'limón'*, *'cultivos perennes'*).\n"
            "• **Cursos y CDTs:** Escribe *'cursos'* o el nombre del centro tecnológico.\n"
            "• **Trámites:** Escribe *'habilitación de consultores'* o *'registro de intermediarios'*.\n"
            "• **Bolsa de Trabajo:** Escribe *'vacantes'* o *'empleo'*."
        )


def main():
    parser = argparse.ArgumentParser(description="Chatbot FIRA RAG Híbrido Local.")
    parser.add_argument("query", nargs="?", type=str, help="Mensaje a probar.")
    args = parser.parse_args()

    bot = SmartFiraBot()

    if args.query:
        print("\n💬 RESPUESTA:\n")
        print(bot.respond(args.query))
        print("\n" + "-" * 60)
        return

    print("🤖 Chatbot FIRA Local activo. Escribe 'salir' para terminar:\n")
    while True:
        try:
            line = input("Tú: ").strip()
            if not line:
                continue
            if line.lower() in ["salir", "exit", "quit"]:
                break
            print(f"\nFIRA Bot:\n{bot.respond(line)}\n" + "-" * 60 + "\n")
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    main()