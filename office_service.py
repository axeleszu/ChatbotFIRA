import argparse
import json
import math
import re
import sys
from pathlib import Path
import requests

class OfficeService:
    def __init__(self, data_path="data/offices.json"):
        path = Path(data_path)
        if not path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de datos en: {data_path}")

        with open(path, "r", encoding="utf-8") as f:
            self.offices = json.load(f)

    def clean_location_input(self, text: str) -> str:
        """Limpia palabras de intención y preposiciones para aislar el lugar geográfico."""
        cleaned = re.sub(r"[¿?¡!,.:;]", " ", text)
        
        remove_words = [
            r"\bsoy de\b", r"\bvivo en\b", r"\bradico en\b", r"\bme encuentro en\b",
            r"\bestoy en\b", r"\bcerca(?:\s+de)?\b", r"\balrededor(?:\s+de)?\b", 
            r"\brumbo\s+a\b", r"\bpr[oó]ximo\s+a\b", r"\boficinas?\b", r"\bagencias?\b", 
            r"\bsucursales?\b", r"\bdireccion(es)?\b", r"\bdirección(es)?\b", 
            r"\btelefonos?\b", r"\bteléfonos?\b", r"\bcontacto\b", r"\bnumeros?\b", 
            r"\bnúmeros?\b", r"\bllamar\b", r"\bdonde\s+(?:estan|queda|esta)\b",
            r"\bdónde\s+(?:están|queda|está)\b", r"\btienen\s+en\b", r"\bhubica\b", 
            r"\bubica\b", r"\bel\s+estado\s+de\b", r"\bel\s+municipio\s+de\b", 
            r"\bla\s+ciudad\s+de\b", r"\bde\b", r"\ben\b", r"\bel\b", r"\bla\b", 
            r"\blos\b", r"\blas\b", r"\bun\b", r"\buna\b"
        ]
        
        for pattern in remove_words:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
            
        return " ".join(cleaned.split()).strip()

    def find_nearest_by_coords(self, lat: float, lng: float, top_n=1):
        """Calcula distancia euclidiana dando prioridad a Agencias sobre Residencias."""
        scored = []
        for ofi in self.offices:
            if ofi["lat"] == 0 and ofi["lng"] == 0:
                continue

            d_lat = ofi["lat"] - lat
            d_lng = ofi["lng"] - lng
            dist = math.sqrt((d_lat * d_lat) + (d_lng * d_lng))

            if not ofi.get("esAgencia", False):
                dist += 0.001

            scored.append((dist, ofi))

        scored.sort(key=lambda x: x[0])
        return [item[1] for item in scored[:top_n]]

    def find_by_location_query(self, user_text: str):
        """Busca oficina solo si el usuario especificó un lugar real."""
        target_place = self.clean_location_input(user_text)
        
        if not target_place or len(target_place) < 3:
            return None, None

        # 1. Búsqueda por coordenadas con OpenStreetMap Nominatim
        api_url = "https://nominatim.openstreetmap.org/search"
        params = {
            "format": "json",
            "countrycodes": "mx",
            "q": target_place,
            "limit": 1
        }
        headers = {"User-Agent": "FiraChatbot/1.0"}

        try:
            r = requests.get(api_url, params=params, headers=headers, timeout=5)
            data = r.json()
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                display_name = data[0]["display_name"]
                nearest = self.find_nearest_by_coords(lat, lon, top_n=1)
                if nearest:
                    return nearest[0], target_place.title()
        except Exception:
            pass

        target_lower = target_place.lower()
        for ofi in self.offices:
            name_dom = (ofi["name"] + " " + ofi.get("domicilio", "")).lower()
            if target_lower in name_dom:
                return ofi, target_place.title()

        return None, None

    def get_schedule_for_office(self, office: dict) -> str:
        """Horario diferenciado: 8 a 16 hrs para estados del pacífico/noroeste."""
        name_dom = (office.get("name", "") + " " + office.get("domicilio", "")).lower()
        western_keywords = [
            "sonora", "son.", "sinaloa", "sin.", 
            "baja california", "b.c.", "bcs", "nayarit", "nay."
        ]
        if any(kw in name_dom for kw in western_keywords):
            return "Lunes a Viernes de 8:00 a 16:00 hrs (hora local)"
        return "Lunes a Viernes de 9:00 a 17:00 hrs (Tiempo del Centro)"

    def format_office_response(self, office: dict, location_name: str = None) -> str:
        loc_str = f" para **{location_name}**" if location_name else ""
        tel = office.get("tel", "").strip()
        tel_line = f"☎️ **Teléfono:** {tel}\n" if tel else ""

        titular = office.get("responsable", "").strip()
        titular_line = f"👤 **Atención:** {titular}\n" if titular else ""
        schedule = self.get_schedule_for_office(office)

        response = (
            f"📍 La oficina más cercana{loc_str} es:\n\n"
            f"🏢 **{office['name']}**\n"
            f"{titular_line}"
            f"📬 **Domicilio:** {office.get('domicilio', 'Consultar en directorio')}\n"
            f"{tel_line}"
            f"🕒 **Horario de atención:** {schedule}\n\n"
            f"💡 **Recomendación:** Te sugerimos llamar al número local para agendar "
            f"una cita o acudir directamente a ventanilla para revisar los detalles "
            f"de tu proyecto productivo.\n\n"
            f"Directorio nacional: https://www.fira.gob.mx/OficinasXML/OficinasDireccion.jsp"
        )
        return response


def main():
    parser = argparse.ArgumentParser(description="Buscador de oficinas FIRA.")
    parser.add_argument("location", nargs="?", type=str, help="Ciudad, municipio o estado.")
    args = parser.parse_args()

    service = OfficeService()
    if args.location:
        ofi, loc = service.find_by_location_query(args.location)
        if ofi:
            print(service.format_office_response(ofi, loc))
        else:
            print(f"❌ No se encontró oficina para '{args.location}'.")


if __name__ == "__main__":
    main()