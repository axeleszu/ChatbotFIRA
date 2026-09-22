#genera un archivo JSON con el contenido de los archivos XML de FIRA, limpiando el HTML y extrayendo títulos y párrafos.
import os
import re
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from bs4 import BeautifulSoup

# Default directory on your Mac
DEFAULT_XML_DIR = "/Users/spps/ROOT/Nd/xml"
OUTPUT_DIR = Path("data")

def clean_html_from_cdata(raw_html: str) -> str:
    """Removes scripts, styles, and extracts clean, readable text."""
    if not raw_html:
        return ""
    
    soup = BeautifulSoup(raw_html, "html.parser")
    
    for tag in soup(["script", "style", "iframe"]):
        tag.decompose()
        
    text = soup.get_text(separator="\n")
    
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

def process_xml_file(filepath: Path) -> dict:
    """Parses a single FIRA XML file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        root = ET.fromstring(content)
        
        extracted_data = {
            "file": filepath.name,
            "title": "",
            "content": ""
        }
       
        titulo_el = root.find(".//titulo")
        if titulo_el is not None and titulo_el.text:
            extracted_data["title"] = titulo_el.text.strip()

        parrafo_el = root.find(".//parrafo")
        if parrafo_el is not None and parrafo_el.text:
            clean_text = clean_html_from_cdata(parrafo_el.text)
            extracted_data["content"] = clean_text            
         
            if not extracted_data["title"] and clean_text:
                extracted_data["title"] = clean_text.split("\n")[0]

        return extracted_data

    except Exception as e:
        print(f"⚠️ Error reading {filepath.name}: {e}")
        return None

def main(xml_dir=DEFAULT_XML_DIR):
    xml_path = Path(xml_dir)
    if not xml_path.exists():
        print(f"❌ Error: Directory '{xml_path}' does not exist.")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    all_articles = []

    xml_files = list(xml_path.glob("*.xml"))
    print(f"📂 Found {len(xml_files)} XML files in {xml_path}...")

    for file in xml_files:
        parsed = process_xml_file(file)
        if parsed and parsed["content"]:
            all_articles.append(parsed)

    out_file = OUTPUT_DIR / "extracted_articles.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"✅ Extracted {len(all_articles)} documents into '{out_file}'.")

if __name__ == "__main__":
    import sys
    target_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XML_DIR
    main(target_dir)