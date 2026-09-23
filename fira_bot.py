import argparse
import re
import sys
from office_service import OfficeService
from retriever import KnowledgeRetriever

ESTADOS_MEXICO = [
    "aguascalientes", "baja california", "baja california sur", "campeche", "chiapas",
    "chihuahua", "coahuila", "colima", "durango", "guanajuato", "guerrero", "hidalgo",
    "jalisco", "méxico", "mexico", "michoacán", "michoacan", "morelos", "nayarit",
    "nuevo león", "nuevo leon", "oaxaca", "puebla", "querétaro", "queretaro",
    "quintana roo", "san luis potosí", "san luis potosi", "sinaloa", "sonora",
    "tabasco", "tamaulipas", "tlaxcala", "veracruz", "yucatán", "yucatan", "zacatecas"
]

class FiraTransactionalBot:
    def __init__(self):
        try:
            self.office_srv = OfficeService()
            self.retriever = KnowledgeRetriever()
        except Exception as e:
            print(f"❌ Error al inicializar servicios: {e}")
            sys.exit(1)

        self.sessions = {}

    def get_session(self, user_id: str) -> dict:
        if user_id not in self.sessions:
            self.sessions[user_id] = {
                "step": "INIT",
                "data": {"location_office": None, "location_name": None}
            }
        return self.sessions[user_id]

    def reset_session(self, user_id: str):
        self.sessions[user_id] = {
            "step": "INIT",
            "data": {"location_office": None, "location_name": None}
        }

    def menu_principal(self) -> str:
        return (
            "👋 ¡Hola! Bienvenido al asistente virtual de **FIRA**.\n\n"
            "Por favor escribe el **número** o la opción de tu interés:\n\n"
            "1️⃣ **Tengo un proyecto y requiero crédito**\n"
            "2️⃣ **Soy Intermediario Financiero (Banco, SOFOM, Caja) y quiero operar con FIRA**\n"
            "3️⃣ **Quiero trabajar en FIRA (Bolsa de Trabajo)**\n"
            "4️⃣ **Servicio Social, Residencias o Prácticas Profesionales**\n"
            "5️⃣ **Información de Programas y Apoyos**\n"
            "6️⃣ **Esperar atención de un asesor humano**\n\n"
            "*(Puedes escribir 'menu' en cualquier momento para reiniciar)*"
        )

    def is_valid_location(self, text: str) -> bool:
        """Determina si un texto representa genuinamente un lugar geográfico en México."""
        t_lower = text.lower().strip()
        
        # 1. ¿Es un estado de la república?
        if any(estado in t_lower for estado in ESTADOS_MEXICO):
            return True
            
        # 2. ¿Tiene prefijos claros de ubicación?
        if re.search(r"\b(soy\s+de|vivo\s+en|estoy\s+en|radico\s+en|desde|municipio\s+de|ciudad\s+de)\b", t_lower):
            return True

        # 3. ¿Coincide con alguna agencia o municipio de la base de oficinas?
        cleaned = self.office_srv.clean_location_input(text)
        if len(cleaned) >= 3:
            for ofi in self.office_srv.offices:
                name_dom = (ofi["name"] + " " + ofi.get("domicilio", "")).lower()
                if cleaned.lower() in name_dom:
                    return True

        return False

    def resolver_programas_adicionales(self, actividad: str) -> str:
        """Consulta dinámicamente el retriever y devuelve programas relevantes."""
        results = self.retriever.retrieve(actividad, top_k=3)

        if results and results[0][0] > 0.4:
            res = f"🌱 **Programas y apoyos sugeridos para '{actividad.title()}':**\n\n"
            for score, doc in results:
                title = doc.get("clean_title", doc.get("title", ""))
                url = doc.get("url", "https://www.fira.gob.mx/Nd/ApoyosFomento.jsp")
                summary = doc.get("summary", "")
                res += f"• **[{title}]({url})**\n  _{summary}_\n\n"
            return res.strip()

        return (
            "🌱 **Programas y herramientas generales de FIRA:**\n\n"
            "• **[Crédito FIRA (Avío y Refaccionario)](https://www.fira.gob.mx/Nd/FondeoFira.jsp)**\n"
            "  _Financiamiento para capital de trabajo e inversión fija a través de intermediarios autorizados._\n\n"
            "• **[Sistema de Agrocostos](https://www.fira.gob.mx/Nd/Agrocostos.jsp)**\n"
            "  _Simulador de costos de producción por hectárea para planear tu crédito._\n\n"
            "• **[Estrategia Cosechando Soberanía](https://www.fira.gob.mx/Nd/pagCosechandoSoberania.jsp)**\n"
            "  _Esquema prioritario con tasa de interés preferencial y garantía FONAGA._"
        )

    def handle_message(self, user_id: str, message: str) -> str:
        msg = message.strip()
        msg_lower = msg.lower()
        session = self.get_session(user_id)

        # 1. Comandos globales de reinicio
        if msg_lower in ["menu", "inicio", "empezar", "reset", "cancelar"]:
            self.reset_session(user_id)
            return self.menu_principal()

        # 2. Despedidas cordiales
        despedidas = [r"\badi[oó]s\b", r"\bgracias\b", r"\bhasta\s+luego\b", r"\bbye\b", r"\bnos\s+vemos\b"]
        if any(re.search(d, msg_lower) for d in despedidas) and len(msg_lower.split()) <= 3:
            self.reset_session(user_id)
            return (
                "🤝 ¡Fue un placer atenderte! Si requieres más información en el futuro, "
                "no dudes en escribirnos. ¡Mucho éxito con tu proyecto!"
            )

        # 3. Usuario en espera de humano
        if session["step"] == "WAITING_HUMAN":
            return (
                "Tu conversación está en espera de nuestro equipo humano. Te responderemos "
                "por este mismo chat a la brevedad durante días hábiles.\n\n"
                "*(Escribe 'menu' si deseas regresar al asistente automático)*"
            )

        # 4. Atajos directos globales
        if re.search(r"\b(servicio\s+social|servicio|social|pr[aá]cticas|residencias|estancias)\b", msg_lower) and len(msg_lower.split()) <= 4:
            self.reset_session(user_id)
            return self.opcion_4_servicio_social()

        if re.search(r"\b(vacantes?|trabajar|trabajo|empleo|chamba|bolsa\s+de\s+trabajo)\b", msg_lower):
            self.reset_session(user_id)
            return self.opcion_3_empleo()

        if re.search(r"\b(soy\s+un?\s+if|intermediario\s+financiero|incorporar\s+if|financiera|banco|sofom)\b", msg_lower):
            self.reset_session(user_id)
            return self.opcion_2_intermediario()

        if re.search(r"\b(consultor(es)?|habilitaci[oó]n|prestador(es)?)\b", msg_lower):
            self.reset_session(user_id)
            return self.opcion_consultores()

        if msg_lower in ["oficina", "oficinas", "agencia", "agencias", "sucursal", "sucursales", "donde estan", "dónde están"]:
            session["step"] = "CREDITO_PEDIR_UBICACION"
            return (
                "🏢 **Directorio de Oficinas FIRA:**\n\n"
                "Para darte el domicilio, teléfono local y horario de la oficina más cercana, "
                "por favor indícanos: **¿En qué municipio y estado te encuentras?**\n"
                "(Ejemplo: *'Ensenada, Baja California'* o *'Tequila, Jalisco'*)"
            )

        if re.search(r"\b(humano|asesor|persona|agente)\b", msg_lower) and len(msg_lower.split()) < 4:
            session["step"] = "WAITING_HUMAN"
            return self.opcion_6_humano()

        # 5. Detección estricta de ubicaciones al inicio (ej. "Soy de Oaxaca", "Sonora", "Irapuato")
        if session["step"] in ["INIT", "AWAITING_MENU_CHOICE"]:
            if self.is_valid_location(msg):
                office, loc_name = self.office_srv.find_by_location_query(msg)
                if office:
                    session["data"]["location_office"] = office
                    session["data"]["location_name"] = loc_name
                    session["step"] = "CREDITO_PEDIR_CULTIVO"
                    return (
                        f"📍 Ubicación identificada: **{loc_name}**.\n\n"
                        "Para conectarte con la oficina correspondiente y mostrarte los apoyos que aplican:\n"
                        "**¿Qué cultivo, ganado o actividad productiva tiene tu proyecto?**\n"
                        "(Ejemplo: *'Maíz'*, *'Limón'*, *'Ganado bovino'*, *'Cabañas'*, etc.)"
                    )

        # -------------------------------------------------------------
        # ESTADO: INIT o AWAITING_MENU_CHOICE
        # -------------------------------------------------------------
        if session["step"] in ["INIT", "AWAITING_MENU_CHOICE"]:
            # Validar si el usuario envió exactamente una opción del 1 al 6
            opt_match = re.match(r"^\s*([1-6])[.)]?\s*$", msg)
            if opt_match:
                opcion = opt_match.group(1)
                if opcion == "1":
                    session["step"] = "CREDITO_PEDIR_UBICACION"
                    return (
                        "💰 **Proyectos y Financiamiento:**\n\n"
                        "Por favor indícanos: **¿En qué municipio y estado se encuentra tu proyecto?**\n"
                        "(Ejemplo: *'Irapuato, Guanajuato'* o *'Caborca, Sonora'*)"
                    )
                elif opcion == "2":
                    self.reset_session(user_id)
                    return self.opcion_2_intermediario()
                elif opcion == "3":
                    self.reset_session(user_id)
                    return self.opcion_3_empleo()
                elif opcion == "4":
                    self.reset_session(user_id)
                    return self.opcion_4_servicio_social()
                elif opcion == "5":
                    session["step"] = "PROGRAMAS_PEDIR_ACTIVIDAD"
                    return (
                        "🌾 **Información de Programas y Apoyos:**\n\n"
                        "¿Sobre qué cultivo, ganado o actividad productiva requieres información?\n"
                        "(Ejemplo: *'Maíz'*, *'Limón'*, *'Biofertilizantes'*, *'Cursos'*, *'Riego'*)"
                    )
                elif opcion == "6":
                    session["step"] = "WAITING_HUMAN"
                    return self.opcion_6_humano()

            # Si saludó brevemente
            if any(saludo in msg_lower for saludo in ["hola", "buen", "tardes", "dias", "informacion", "info", "hello"]) and len(msg_lower.split()) <= 4:
                session["step"] = "AWAITING_MENU_CHOICE"
                return self.menu_principal()

            # Si escribió un tema libre (ej. "maiz", "fertilizantes", "esg", "inversionistas"), buscar en el retriever
            res = self.retriever.retrieve(msg, top_k=2)
            if res and res[0][0] > 0.8:
                self.reset_session(user_id)
                output = f"🔍 **Información relacionada encontrada para '{msg}':**\n\n"
                for score, doc in res:
                    title = doc.get("clean_title", doc.get("title", ""))
                    url = doc.get("url", "https://www.fira.gob.mx/Nd/ApoyosFomento.jsp")
                    summary = doc.get("summary", "")
                    output += f"• **[{title}]({url})**\n  _{summary}_\n\n"
                output += "*(Escribe 'menu' para volver a las opciones principales)*"
                return output.strip()

            # Si fue texto sin sentido (ej. "8912s", "giberish")
            session["step"] = "AWAITING_MENU_CHOICE"
            return (
                "No reconocí esa opción. Por favor escribe un número del **1 al 6** o indica el tema de tu interés:\n\n"
                + self.menu_principal()
            )

        # -------------------------------------------------------------
        # FLUJO 1: CRÉDITO (Ubicación -> Actividad)
        # -------------------------------------------------------------
        if session["step"] == "CREDITO_PEDIR_UBICACION":
            # Si el usuario se arrepiente y presiona otro número del menú (ej. "2" o "3")
            if msg in ["1", "2", "3", "4", "5", "6"]:
                self.reset_session(user_id)
                session["step"] = "AWAITING_MENU_CHOICE"
                return self.handle_message(user_id, msg)

            office, loc_name = self.office_srv.find_by_location_query(msg)
            if not office:
                return (
                    "No logré identificar la localidad. Por favor escribe tu **municipio y estado** "
                    "(por ejemplo: *'Torreón, Coahuila'* o *'Morelia, Michoacán'*):"
                )

            session["data"]["location_office"] = office
            session["data"]["location_name"] = loc_name
            session["step"] = "CREDITO_PEDIR_CULTIVO"

            return (
                f"✅ Ubicación identificada: **{loc_name}**.\n\n"
                "Para sugerirte los apoyos vigentes que aplican a tu caso:\n"
                "**¿Qué cultivo, ganado o actividad productiva vas a desarrollar?**\n"
                "(Ejemplo: *'Maíz'*, *'Aguacate'*, *'Becerros'*, *'Cabañas'*, etc.)"
            )

        if session["step"] == "CREDITO_PEDIR_CULTIVO":
            if msg in ["1", "2", "3", "4", "5", "6"]:
                self.reset_session(user_id)
                session["step"] = "AWAITING_MENU_CHOICE"
                return self.handle_message(user_id, msg)
                
            actividad = msg.strip()
            office = session["data"]["location_office"]
            loc_name = session["data"]["location_name"]

            respuesta_oficina = self.office_srv.format_office_response(office, loc_name)
            programas_sugeridos = self.resolver_programas_adicionales(actividad)
            self.reset_session(user_id)

            return (
                f"🤝 **Para financiar tu proyecto de {actividad.title()} en {loc_name}:**\n\n"
                "FIRA opera como banca de segundo piso a través de intermediarios financieros. "
                "El primer paso es **acudir a tu agencia FIRA más cercana** para presentar "
                "tu idea y conectarte con las instituciones financieras con convenio:\n\n"
                f"{respuesta_oficina}\n\n"
                f"{programas_sugeridos}\n\n"
                "💡 *Llama al número local de la agencia para agendar una cita previa.*"
            )

        # -------------------------------------------------------------
        # FLUJO 5: PROGRAMAS Y APOYOS
        # -------------------------------------------------------------
        if session["step"] == "PROGRAMAS_PEDIR_ACTIVIDAD":
            programas = self.resolver_programas_adicionales(msg)
            self.reset_session(user_id)
            return (
                f"{programas}\n\n"
                "🏢 **Ventanillas de atención:** Para conocer convocatorias y tramitar estos apoyos, acude a tu agencia local:\n"
                "Directorio de agencias: https://www.fira.gob.mx/OficinasXML/OficinasDireccion.jsp"
            )

        self.reset_session(user_id)
        return self.menu_principal()

    # -----------------------------------------------------------------
    # RESPUESTAS CANÓNICAS
    # -----------------------------------------------------------------

    def opcion_consultores(self) -> str:
        return (
            "📋 **Habilitación y Registro de Consultores FIRA:**\n\n"
            "Para registrarte como Prestador Externo de Servicios Especializados (evaluación técnico-financiera "
            "de proyectos o supervisión de crédito a intermediarios):\n\n"
            "1. Descarga y llena los formatos oficiales.\n"
            "2. Integra tu expediente con acreditación de competencias técnicas.\n"
            "3. Presenta tu solicitud en la agencia FIRA más cercana a tu domicilio.\n\n"
            "🔗 **Formatos y Convocatoria:** https://www.fira.gob.mx/Nd/HabilyCalif.jsp"
        )

    def opcion_2_intermediario(self) -> str:
        return (
            "🏦 **Incorporación de Intermediarios Financieros a la Red FIRA:**\n\n"
            "Si representas a una entidad financiera (Banco, SOFOM, Caja de Ahorro/Cooperativa, Unión de Crédito):\n\n"
            "1. **Consulta las 3 modalidades de participación:**\n"
            "   • *Esquema Tradicional* (Fondeo, garantía y apoyos).\n"
            "   • *Intermediarios Financieros en Desarrollo (IFD)*.\n"
            "   • *Programa de Financiamiento a la Agricultura Familiar (PROAF)*.\n"
            "2. **Integra tu expediente:** En el portal encontrarás la lista de documentos y formatos requeridos.\n"
            "3. **Dudas y atención corporativa:** Dirige tu expediente a los correos:\n"
            "   📧 dacif@fira.gob.mx | sacifnb@fira.gob.mx\n\n"
            "🔗 **Revisa los lineamientos y formatos de registro aquí:**\n"
            "https://www.fira.gob.mx/Nd/RegistroIF.jsp"
        )

    def opcion_3_empleo(self) -> str:
        return (
            "💼 **Bolsa de Trabajo y Convocatorias FIRA:**\n\n"
            "¡Qué gusto que quieras colaborar con nosotros en el desarrollo del campo mexicano!\n\n"
            "Todas las convocatorias de empleo, requisitos de perfil y plazas vacantes en nuestras "
            "oficinas centrales y agencias se publican y gestionan en el portal oficial:\n\n"
            "🔗 **Consulta vacantes y aplica aquí:**\n"
            "https://www.fira.gob.mx/VacantesUserDtoXML/Requisitos.jsp"
        )

    def opcion_4_servicio_social(self) -> str:
        return (
            "🎓 **Servicio Social, Residencias y Prácticas Profesionales:**\n\n"
            "Si estudias o recién egresaste de Agronomía, Veterinaria, Biotecnología, Economía, "
            "Finanzas, Informática o carreras afines:\n\n"
            "1. **Contacto Oficial:** Escribe directamente al **Lic. Jesús Juárez**:\n"
            "   📧 **jjuarezb@fira.gob.mx**\n\n"
            "2. **Incluye en tu correo:**\n"
            "   • Fechas o periodo en el que deseas realizarlo.\n"
            "   • Licenciatura o Ingeniería que cursas y porcentaje de créditos.\n"
            "   • Lugar o ciudad donde te gustaría asignarte (Oficinas Centrales, Agencias o CDTs).\n\n"
            "💡 *También puedes acercarte directamente a la agencia FIRA más cercana a tu escuela o domicilio:*\n"
            "https://www.fira.gob.mx/OficinasXML/OficinasDireccion.jsp"
        )

    def opcion_6_humano(self) -> str:
        return (
            "👤 **Atención con un Asesor Humano:**\n\n"
            "Hemos transferido tu conversación a la bandeja de nuestro equipo. "
            "Un asesor de FIRA te responderá por este mismo chat durante nuestro horario de atención "
            "(Lunes a Viernes de 9:00 a 17:00 hrs, Tiempo del Centro).\n\n"
            "Por favor déjanos tu duda detallada y el estado/municipio de donde nos escribes para prepararte "
            "la información exacta.\n\n"
            "*(Escribe 'menu' en cualquier momento si deseas volver al asistente automático)*"
        )


def main():
    parser = argparse.ArgumentParser(description="Chatbot Transaccional FIRA para Facebook Messenger.")
    args = parser.parse_args()

    bot = FiraTransactionalBot()
    simulated_user_id = "fb_user_123"

    print("=" * 65)
    print("🤖 CHATBOT TRANSACCIONAL FIRA (Simulador de Messenger Activo)")
    print("=" * 65 + "\n")

    while True:
        try:
            user_input = input("Usuario: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["salir", "exit", "quit"]:
                break
            
            response = bot.handle_message(simulated_user_id, user_input)
            print(f"\nFIRA Bot:\n{response}\n" + "-" * 65 + "\n")
            
        except (KeyboardInterrupt, EOFError):
            break

if __name__ == "__main__":
    main()