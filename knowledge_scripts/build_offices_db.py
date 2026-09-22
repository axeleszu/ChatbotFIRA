import json
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path

BASE_URL = "https://www.fira.gob.mx"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def clean_html_entities(text):
    if not text:
        return ""
    replacements = {
        "&aacute;": "á", "&eacute;": "é", "&iacute;": "í",
        "&oacute;": "ó", "&uacute;": "ú", "&Aacute;": "Á",
        "&Eacute;": "É", "&Iacute;": "Í", "&Oacute;": "Ó",
        "&Uacute;": "Ú", "&ntilde;": "ñ", "&Ntilde;": "Ñ"
    }
    for ent, char in replacements.items():
        text = text.replace(ent, char)
    return re.sub(r"<.*?>", " ", text).strip()

def extract_titular_domicilio(raw_html):
    titular = ""
    domicilio = ""
    try:
        # REGEX
        m1 = re.search(r"<.*5px\'?>(.*?)(?:<br\s*/?>)", raw_html)
        if m1:
            titular = clean_html_entities(m1.group(1))

        # REGEX
        m2 = re.search(r"<.*5px\'?>(?:.*?)(?:<br\s*/?>)(.*?)(?:<br\s*/?>)", raw_html)
        if m2:
            domicilio = clean_html_entities(m2.group(1))
    except Exception:
        pass
    return titular, domicilio

def fetch_base_offices():
    offices = {}
    
    # 1. Agencias
    try:
        r = requests.get(f"{BASE_URL}/Nd/agencia.json", headers=HEADERS, timeout=10)
        ag_data = r.json()
        
        # Handle both list and dict structures
        ag_items = ag_data if isinstance(ag_data, list) else ag_data.values()
        
        for item in ag_items:
            name = item.get("name")
            if not name:
                continue
                
            titular, domicilio = extract_titular_domicilio(item.get("titular", ""))
            coords = item.get("coords", {}) or {}
            
            offices[name] = {
                "name": name,
                "esAgencia": True,
                "lat": float(coords.get("lat", 0)),
                "lng": float(coords.get("lng", 0)),
                "responsable": titular,
                "domicilio": domicilio,
                "tel": ""
            }
        print(f" Loaded {len(offices)} base agencias.")
    except Exception as e:
        print(f"Error loading agencia.json: {e}")

    # 2. Residencias Estatales
    try:
        r = requests.get(f"{BASE_URL}/Nd/residencia.json", headers=HEADERS, timeout=10)
        re_data = r.json()
        
        re_items = re_data if isinstance(re_data, list) else re_data.values()
        count_res = 0
        
        for item in re_items:
            name = item.get("name")
            if not name:
                continue
                
            titular, domicilio = extract_titular_domicilio(item.get("titular", ""))
            coords = item.get("coords", {}) or {}
            
            offices[name] = {
                "name": name,
                "esAgencia": False,
                "lat": float(coords.get("lat", 0)),
                "lng": float(coords.get("lng", 0)),
                "responsable": titular,
                "domicilio": domicilio,
                "tel": ""
            }
            count_res += 1
        print(f" Loaded {count_res} base residencias.")
    except Exception as e:
        print(f"Error loading residencia.json: {e}")

    return offices

def enrich_from_jsp(offices):
    # IDs defined in your JS array: valoresOfUrl
    state_ids = [2, 4, 5, 6, 7, 9, 11, 12, 13, 14, 16, 17, 18, 19, 20, 
                 21, 22, 23, 24, 26, 27, 28, 29, 30, 31, 32, 33, 35, 36, 37, 38, 39]
    
    print(f"Enriching phones & addresses from {len(state_ids)} states...")

    for state_id in state_ids:
        url = f"{BASE_URL}/OficinasXML/CheckOficina.jsp?Of={state_id}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, "html.parser")
            cards = soup.select(".card")

            for card in cards:
                header = card.select_one(".card-header")
                if not header:
                    continue
                name = header.get_text(strip=True)
                
                paragraphs = card.select(".d-block")
                title_el = card.select_one(".card-title")
                titular = title_el.get_text(strip=True) if title_el else ""

                if len(paragraphs) >= 4:
                    if not titular:
                        titular = paragraphs[0].get_text(strip=True)
                    domicilio = paragraphs[0].get_text(strip=True)
                    loc = paragraphs[1].get_text(strip=True)
                    cp = paragraphs[2].get_text(strip=True)
                    tel = paragraphs[3].get_text(strip=True)

                    full_domicilio = f"{domicilio} {loc} C.P. {cp}"

                    if name in offices:
                        offices[name]["tel"] = tel
                        offices[name]["responsable"] = titular
                        offices[name]["domicilio"] = full_domicilio
                    else:
                        offices[name] = {
                            "name": name,
                            "esAgencia": False,
                            "lat": 0.0,
                            "lng": 0.0,
                            "responsable": titular,
                            "domicilio": full_domicilio,
                            "tel": tel
                        }
        except Exception as e:
            print(f"Error scraping state {state_id}: {e}")

    return offices

def main():
    Path("data").mkdir(exist_ok=True)
    print("1. Fetching base JSON coordinates...")
    offices = fetch_base_offices()
    print(f"Loaded {len(offices)} base offices.")

    print("2. Enriching phone and postal details...")
    offices = enrich_from_jsp(offices)

    output_path = Path("data/offices.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(list(offices.values()), f, ensure_ascii=False, indent=2)

    print(f" Saved {len(offices)} offices into {output_path}")

if __name__ == "__main__":
    main()