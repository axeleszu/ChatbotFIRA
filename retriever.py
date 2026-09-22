import argparse
import json
import re
import sys
import math
from pathlib import Path
from typing import List, Dict, Tuple

def normalize_spanish(text: str) -> str:
    """Elimina acentos y diacríticos."""
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u',
        'Á': 'a', 'É': 'e', 'Í': 'i', 'Ó': 'o', 'Ú': 'u', 'Ü': 'u'
    }
    for acc, clean in replacements.items():
        text = text.replace(acc, clean)
    return text

def stem_spanish(word: str) -> str:
    """Extrae la raíz singular básica en español para resolver plurales."""
    if len(word) > 4 and word.endswith("ces"):
        return word[:-3] + "z"
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("is"):
        return word[:-1]
    return word

CDT_CLAVES = {
    "LiraLopez.xml": "1",
    "Tezoyuca.xml": "2",
    "Tantakin.xml": "3",
    "Noria.xml": "4",
    "Villadiego.xml": "5"
}

# Archivos administrativos sin programas
EXCLUDED_FILES = {
    "politicas.xml", "AvisoLegal.xml", "Seguridad.xml", "accesibilidad.xml",
    "ComiteEtica.xml", "RecomendacionesFira.xml", "DatosAbiertos.xml",
    "memoriaCajas2019.xml", "DocTranspParticipacion.xml", "AvanceOperaciones.xml",
    "EstFinancierosN.xml", "ProgramasOtrasEntidades.xml", "ProgramasSagarpa.xml"
}

INTENT_BOOSTS = [
    # 1. Fertilizantes y Sustenta+
    (
        {"fertilizante", "fertilizacion", "fertilizar", "biofertilizante", "bioinsumo", "sustenta", "abono", "nutriente", "composta"},
        ["sustenta+.xml", "fertilizantes.xml", "Profertil1.xml"],
        40.0
    ),
    # 2. Suelos y Drenaje
    (
        {"suelo", "drenaje", "desempiedre", "subsoleo", "conservacion"},
        ["RecuperacionSuelo.xml"],
        40.0
    ),
    # 3. Agua, Riego y Pozos
    (
        {"agua", "riego", "pozo", "bombeo", "goteo", "aspersion", "tecnificacion", "presa", "conagua"},
        ["Fonagua.xml", "PagTecnificacion.xml"],
        40.0
    ),
    # 4. Granos Básicos y Cosechando Soberanía (Nacional)
       (
        {"arroz", "trigo", "frijol", "maiz", "sorgo", "soya", "cebada"},
        ["cosechandoSoberania.xml", "fondoCosechandoSoberania.xml", "pagCosechandoSoberania.xml"],
        35.0
    ),
    # 5. Frutales, Perennes, Vid, Uva y Pitahaya (VAN DIRECTO A PERENNES)
    (
        {"uva", "uvas", "vid", "vinedo", "vinedos", "vino", "pitahaya", "pitaya", 
         "agave", "tequila", "mezcal", "nogal", "nuez", "limon", "naranja", "citrico", 
         "aguacate", "mango", "berry", "berrie", "fresa", "zarzamora", "perenne", 
         "frutal", "manzana", "durazno", "platano", "papaya"},
        ["Perennes.xml", "FondeoFira.xml", "agrocostos.xml"],
        35.0
    ),
    # 6. Café y Cacao
    (
        {"cafe", "cafetal", "cacao", "procafe"},
        ["ProCafe.xml", "fondoCosechandoSoberania.xml"],
        35.0
    ),
    # 7. Ganadería
    (
        {"ganado", "ganaderia", "pecuario", "becerro", "corral", "vaca", "carne", "chivo", "borrego", "ovino", "caprino"},
        ["FomentoGanadero.xml", "fondoCosechandoSoberania.xml"],
        35.0
    ),
    # 8. Lechería
    (
        {"leche", "lecheria", "ordena"},
        ["lecheriaTropical.xml", "fondoCosechandoSoberania.xml"],
        35.0
    ),
    # 9. Turismo y Cabañas
    (
        {"turismo", "ecoturismo", "cabana", "hotel", "restaurante", "tirolesa"},
        ["turismo.xml"],
        35.0
    ),
    # 10. Floricultura y Ornamentales
    (
        {"cempasuchil", "nochebuena", "anturio", "rosa", "crisantemo", "flor", "floricultura", "ornamental"},
        ["Tezoyuca.xml", "FonagaProductividad.xml", "Perennes.xml"],
        35.0
    ),
    # 11. Consultores
    (
        {"consultor", "habilitacion", "habilitar", "prestador"},
        ["HabilyCalif.xml"],
        35.0
    ),
    # 12. Intermediarios
    (
        {"if", "intermediario", "financiera", "banco", "caja"},
        ["RegistroIF.xml", "IntemediariosFinancieros.xml"],
        35.0
    ),
    # 13. Cursos
    (
        {"curso", "capacitacion", "taller", "diplomado"},
        ["CdtsAcerca.xml", "LiraLopez.xml", "Villadiego.xml", "Tantakin.xml", "Noria.xml", "Tezoyuca.xml"],
        30.0
    ),
    (
        {"requisito", "requisitos", "papeleria", "documento", "documentos", "pasos", "tramite", "tramites"},
        ["pasos_para_credito.json", "FondeoFira.xml", "FAQ.xml"],
        40.0
    )
]

class KnowledgeRetriever:
    def __init__(self, knowledge_path="data/knowledge.json"):
        path = Path(knowledge_path)
        if not path.exists():
            raise FileNotFoundError(f"No se encontró el archivo: {knowledge_path}")

        with open(path, "r", encoding="utf-8") as f:
            self.documents = json.load(f)

    def _tokenize(self, text: str) -> set:
        """Tokeniza, normaliza acentos y añade la raíz singular."""
        text_clean = normalize_spanish(text.lower())
        raw_words = re.findall(r'\b[a-z0-9_]{2,}\b', text_clean)
        stopwords = {
            "para", "como", "este", "esta", "estos", "estas", "con", "por", 
            "que", "los", "las", "del", "una", "uno", "unos", "unas", "sobre",
            "mas", "pero", "sus", "les", "nos", "fira", "ante", "entre", "hacia",
            "de", "en", "el", "la", "un", "quiero", "tengo", "proyecto", "apoyo", 
            "apoyos", "programas", "programa"
        }
        tokens = set()
        for w in raw_words:
            if w not in stopwords:
                tokens.add(w)
                stemmed = stem_spanish(w)
                if len(stemmed) >= 2:
                    tokens.add(stemmed)
        return tokens

    def retrieve(self, query: str, top_k: int = 3) -> List[Tuple[float, Dict]]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        is_course_query = bool(query_tokens.intersection({"curso", "capacitacion", "taller"}))
        all_scored = []

        for doc in self.documents:
            file_name = doc.get("file", "")
            if file_name in EXCLUDED_FILES:
                continue

            clean_title = doc.get("clean_title", doc.get("title", ""))
            summary = doc.get("summary", "")
            content = doc.get("content", "")
            url = doc.get("url", "https://www.fira.gob.mx/Nd/ApoyosFomento.jsp")

            if is_course_query and file_name in CDT_CLAVES:
                url = f"https://www.fira.gob.mx/CursosSeminariosXML/LstCursos.jsp?clave={CDT_CLAVES[file_name]}"
            elif is_course_query and file_name == "CdtsAcerca.xml":
                url = "https://www.fira.gob.mx/CursosSeminariosXML/LstCursos.jsp?clave=0"

            doc_result = {
                "file": file_name,
                "clean_title": clean_title,
                "summary": summary,
                "url": url,
                "content": content
            }

            title_tokens = self._tokenize(clean_title)
            summary_tokens = self._tokenize(summary)
            content_tokens = self._tokenize(content)

            title_matches = len(query_tokens.intersection(title_tokens))
            summary_matches = len(query_tokens.intersection(summary_tokens))
            content_matches = len(query_tokens.intersection(content_tokens))

            word_count = max(len(content.split()), 50)
            length_penalty = 1.0 / math.log10(word_count + 10)

            base_score = (
                (title_matches * 7.0) +
                (summary_matches * 4.0) +
                (content_matches * 1.5)
            ) * length_penalty

            # Aplicar aumentos por intención
            for trigger_tokens, target_files, boost_pts in INTENT_BOOSTS:
                if query_tokens.intersection(trigger_tokens) and file_name in target_files:
                    base_score += boost_pts

            if base_score > 0.4:
                all_scored.append((base_score, doc_result))

        # 1. ORDENAR PRIMERO DE MAYOR A MENOR PUNTUACIÓN
        all_scored.sort(key=lambda x: x[0], reverse=True)

        # 2. DEDUPLICAR URLS DESPUÉS DE ORDENAR
        final_results = []
        seen_urls = set()
        for score, doc_res in all_scored:
            doc_url = doc_res["url"]
            if doc_url not in seen_urls:
                final_results.append((score, doc_res))
                seen_urls.add(doc_url)
            if len(final_results) >= top_k:
                break

        return final_results


def main():
    parser = argparse.ArgumentParser(description="Recuperador FIRA con deduplicación post-orden.")
    parser.add_argument("query", type=str, help="Texto a buscar.")
    parser.add_argument("-k", "--top", type=int, default=3, help="Número de resultados.")
    args = parser.parse_args()

    retriever = KnowledgeRetriever()
    results = retriever.retrieve(args.query, top_k=args.top)

    print(f"\n🔍 Resultados recuperados para: \"{args.query}\"\n" + "=" * 65)
    for idx, (score, doc) in enumerate(results, start=1):
        print(f"[{idx}] {doc['clean_title']} ({doc['file']}) - Score: {score:.2f}")
        print(f"    ℹ️  {doc['summary']}")
        print(f"    🔗 {doc['url']}")
        print("-" * 65)


if __name__ == "__main__":
    main()