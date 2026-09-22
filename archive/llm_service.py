import argparse
import os
import re
import sys
from openai import OpenAI
from retriever import KnowledgeRetriever

class LLMService:
    def __init__(self, api_key: str = None, model: str = "nvidia/nemotron-3-super-120b-a12b:free"):
        with open('.key', 'r', encoding='utf-8') as f:
            api_key = f.read()

        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("❌ Falta la variable OPENROUTER_API_KEY en tu entorno.")

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
            default_headers={
                "HTTP-Referer": "https://www.fira.gob.mx",
                "X-Title": "FIRA Messenger Chatbot"
            }
        )
        self.model = model

    def clean_llm_reasoning(self, text: str) -> str:
        """Elimina procesos de razonamiento interno filtrados por modelos de tipo 'thinking'."""
        # Elimina bloques <think> ... </think>
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        # Elimina encabezados típicos de análisis como '1. **Analyze the Request:**'
        text = re.sub(r"(?i)^(?:(?:\d+\.\s*)?\*\*(?:analyze|thinking|understanding|plan)[^\n]*\*\*.*?)(?=\n\n|\Z)", "", text, flags=re.DOTALL)
        return text.strip()

    def answer_query(self, user_question: str, context_docs: list) -> str:
        context_parts = []
        official_urls = []

        for doc in context_docs:
            title = doc.get("title", "")
            content = doc.get("content", "")
            context_parts.append(f"--- Documento: {title} ---\n{content}")
            
            if "official_url" in doc and doc["official_url"] not in official_urls:
                official_urls.append(doc["official_url"])

        combined_context = "\n\n".join(context_parts)
        urls_note = f"\nEnlaces oficiales que DEBES incluir en la respuesta si aplican: {', '.join(official_urls)}" if official_urls else ""

        system_prompt = (
            "Eres el asistente virtual oficial de FIRA en Facebook Messenger.\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. RESPONDE DIRECTAMENTE AL USUARIO con la respuesta final. NUNCA muestres tu análisis previo, pasos de razonamiento ni 'Analyze the Request'.\n"
            "2. Basa tu respuesta ÚNICAMENTE en el contexto proporcionado.\n"
            "3. Si no hay información suficiente en el contexto, indica que no puedes responder y sugiere al usuario consultar la agencia FIRA más cercana.\n"
            "4. Si se consulta sobre consultores/prestadores de servicios, aclara que deben llenar los formatos y consultar la liga oficial.\n"
            "5. Si se consulta sobre registro de intermediarios financieros (IF/IFNB), menciona los requisitos y la liga oficial de registro.\n"
            "6. Sé conciso y claro (máximo 2 párrafos cortos)."
        )

        user_prompt = (
            f"Contexto verificado:\n\"\"\"\n{combined_context}\n\"\"\"\n"
            f"{urls_note}\n\n"
            f"Pregunta del usuario: {user_question}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=400
            )

            message = response.choices[0].message
            bot_text = message.content or ""
            if not bot_text and hasattr(message, "reasoning") and message.reasoning:
                bot_text = message.reasoning

            # Limpiar fugas de razonamiento interno
            bot_text = self.clean_llm_reasoning(bot_text)

            # Si faltó incluir el enlace oficial obligatorio, agregarlo al final
            for url in official_urls:
                if url not in bot_text:
                    bot_text += f"\n\n🔗 Más información y formatos en: {url}"

            return bot_text

        except Exception as e:
            return f"Lo sentimos, ocurrió un error temporal: {e}"


def main():
    parser = argparse.ArgumentParser(description="Generador LLM FIRA.")
    parser.add_argument("query", nargs="?", type=str, help="Pregunta del usuario.")
    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        return

    retriever = KnowledgeRetriever()
    results = retriever.retrieve(args.query, top_k=2)
    docs = [doc for score, doc in results]

    llm = LLMService()
    print("\n💬 RESPUESTA:\n" + llm.answer_query(args.query, docs))


if __name__ == "__main__":
    main()