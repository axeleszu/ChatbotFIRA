import json
import re
from pathlib import Path

# Files to explicitly exclude because they are junk, outdated, or dummy tables
EXCLUDED_FILES = {
    "firaCifras.xml",
    "mapaSitio.xml",
    "transferenciaTecnologia-proyectos.xml",
    "transferenciaTecnologia-videos.xml",
    "condicionesOpCOVID.xml",
    "accionesCovid.xml",
    "feriasYexpo.xml",
    "RelaBienes.xml",
    "Almacenes.xml",
    "indicadoresGestion.xml",
    "sustenta+_ocotlan.xml",
    "sustenta+_culiacan.xml",
    "sustenta+_mexicali.xml",
    "sustenta+_obregon.xml",
    "sustenta+_obregon26.xml",
    "sustenta+_cuahutemoc.xml",
    "sustenta+_irapuato.xml",
    "sustenta+_ameca.xml",
    "sustenta+_culiacan26.xml",
    "sustenta+_mochis.xml",
    "purepecha.xml",
    "NuevaAgriculturaContrato.xml",
    "economista.xml",
    "MontoApoyo.xml",
    "RendicionCuentas.xml",
    "EstudiosOpinion.xml",
    "AdquisicionesObraPublica.xml",
    "NormatividadMateriaTrans.xml",
    "Art7_oic.xml",
    "landing70aniversario.xml"
}

def clean_800_numbers(text: str) -> str:
    """Removes any mention of the 800 phone number."""
   # text = re.sub(r"(?:01\s*)?800[\s\-\.]*999[\s\-\.]*(?:FIRA|3472)", "Oficinas locales FIRA", text, flags=re.IGNORECASE)
    return text

def main():
    input_file = Path("data/extracted_articles.json")
    output_file = Path("data/clean_knowledge.json")

    if not input_file.exists():
        print(f"❌ File not found: {input_file}")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        articles = json.load(f)

    clean_articles = []
    for art in articles:
        if art["file"] in EXCLUDED_FILES:
            continue
        
        # Clean 800 mentions from content
        cleaned_content = clean_800_numbers(art["content"])
        
        clean_articles.append({
            "file": art["file"],
            "title": art["title"],
            "content": cleaned_content
        })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(clean_articles, f, ensure_ascii=False, indent=2)

    print(f"✅ Filtered {len(articles)} raw files down to {len(clean_articles)} clean articles.")
    print(f"📁 Saved to: {output_file}")

if __name__ == "__main__":
    main()