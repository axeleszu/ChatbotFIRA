import argparse
import re
import sys
from office_service import OfficeService
from retriever import KnowledgeRetriever
from llm_service import LLMService

LOCATION_TRIGGERS = [
    "oficina", "agencia", "donde estan", "dónde están", "ubicacion", "ubicación",
    "sucursal", "direccion", "dirección", "telefono", "teléfono", "contacto",
    "donde queda", "dónde queda", "donde esta", "dónde está", "encuentro",
    "soy de", "vivo en", "radico en"
]

ESTADOS_MEXICO = [
    "aguascalientes", "baja california", "baja california sur", "campeche", "chiapas",
    "chihuahua", "coahuila", "colima", "durango", "guanajuato", "guerrero", "hidalgo",
    "jalisco", "méxico", "mexico", "michoacán", "michoacan", "morelos", "nayarit",
    "nuevo león", "nuevo leon", "oaxaca", "puebla", "querétaro", "queretaro",
    "quintana roo", "san luis potosí", "san luis potosi", "sinaloa", "sonora",
    "tabasco", "tamaulipas", "tlaxcala", "veracruz", "yucatán", "yucatan", "zacatecas"
]

def sanitize_output(text: str) -> str:

    return str(re.sub(r"\s+", " ", text)).strip()

class FiraChatbot:
    def __init__(self):
        try:
            self.office_srv = OfficeService()
            self.retriever = KnowledgeRetriever()
            self.llm_srv = LLMService()
        except Exception as e:
            print(f"❌ Error al inicializar componentes del chatbot: {e}")
            sys.exit(1)

    def is_location_query(self, user_msg: str) -> bool:
        """Determina si la intención del usuario es ubicar una oficina o teléfono."""
        msg_lower = user_msg.lower()
        has_trigger = any(trigger in msg_lower for trigger in LOCATION_TRIGGERS)
        has_state = any(estado in msg_lower for estado in ESTADOS_MEXICO)
        return has_trigger or has_state

    def respond(self, user_message: str) -> str:
        msg_clean = user_message.strip()

        # Datos de oficina
        if self.is_location_query(msg_clean):
            office, loc_name = self.office_srv.find_by_location_query(msg_clean)
            if office:
                print("\n [Base de Datos Local - office_service.py (0 tokens)]")
                return self.office_srv.format_office_response(office, loc_name)
            else:
                return (
                    "Para proporcionarte el teléfono y la dirección de la oficina correspondiente, "
                    "por favor indícanos de qué municipio o estado nos contactas."
                )

        # Datos de IA
        matches = self.retriever.retrieve(msg_clean, top_k=2)
        if not matches:
            return (
                "Para orientarte mejor sobre tu proyecto productivo, indícanos tu municipio "
                "o estado para brindarte los datos de la agencia FIRA más cercana."
            )

        docs = [doc for score, doc in matches]
        
        result = self.llm_srv.answer_query(msg_clean, docs)
        
        if isinstance(result, (tuple, list)) and len(result) >= 2:
            raw_answer, model_used = result[0], result[1]
        else:
            raw_answer = result
            model_used = getattr(self.llm_srv, "model", "openrouter/free")

        # print(f"\n⚙️ [Ruta: RAG + OpenRouter | Modelo: {model_used}]")
        return sanitize_output(raw_answer)


def main():
    parser = argparse.ArgumentParser(description="Orquestador Maestro del Chatbot FIRA.")
    parser.add_argument("query", nargs="?", type=str, help="Mensaje del usuario.")
    parser.add_argument("-q", "--query", type=str, dest="query_flag", help="Mensaje alternativo.")

    args = parser.parse_args()
    user_msg = args.query_flag or args.query

    bot = FiraChatbot()

    if user_msg:
        respuesta = bot.respond(user_msg)
        print("💬 RESPUESTA:\n")
        print(respuesta)
        return

    print("🤖 Chatbot FIRA activo en consola. Escribe tu consulta (o 'salir'):\n")
    while True:
        try:
            line = input("Tú: ").strip()
            if not line:
                continue
            if line.lower() in ["salir", "exit", "quit"]:
                break
            
            reply = bot.respond(line)
            print(f"\nFIRA Bot:\n{reply}\n" + "-" * 50 + "\n")
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    main()