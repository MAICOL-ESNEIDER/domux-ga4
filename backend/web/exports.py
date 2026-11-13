"""Excel de las listas de la web: la misma lista que se ve en pantalla, con sus filtros, en un archivo.

El Excel se descarga solo aquí, en la web de administración desde el computador: en la app no hay
Excel ni se guarda nada en el celular. Cada lista lleva solo los datos que se necesitan para trabajar
con ella (no van correos, teléfonos, números de documento, fotos ni conversaciones) y una hoja
«Acerca de» que dice quién la descargó, cuándo, con qué filtros y que tiene datos personales. Cada
descarga queda anotada en el registro de auditoría: quién, qué lista, con qué filtros y cuántas filas.

Las filas llegan por la misma API de la lista y con el token del administrador, así los permisos y
los filtros son exactamente los de la pantalla.
"""

from flask import Response, flash, g, redirect

from extensions import db
from services.audit_service import add_audit_log
from services.excel_service import MIME_XLSX, generate_list_xlsx
from time_utils import colombia_now, colombia_today
from web import texts
from web.support import fetch_all

#: Lo más que trae un Excel: 50 páginas de 100 filas. Si hay más, la hoja «Acerca de» lo dice.
MAX_PAGES = 50
MAX_ROWS = MAX_PAGES * 100

PRIVACY_NOTE = (
    "Este archivo tiene datos personales de la unidad. Úsalo solo para la administración, guárdalo en un "
    "lugar seguro y no lo compartas (Ley 1581 de 2012). Cada descarga queda registrada."
)

ROLE_TEXTS = {"ADMIN": "Administración", "GUARD": "Portería", "RESIDENT": "Residente"}
OCCUPANCY_TEXTS = {"propietario": "Propietario", "arrendatario": "Arrendatario", "residente": "Residente"}


def _label(kind, value):
    return texts.badge_info(kind, value)["label"] if value else ""


def _yes(value):
    return "Sí" if value else "No"


#: Las columnas de cada lista: (encabezado, cómo se saca de la fila que entrega la API).
PQRS_COLUMNS = (
    ("Radicado", lambda row: row.get("radicado")),
    ("Radicada", lambda row: texts.date_es(row.get("createdAt"))),
    ("Tipo", lambda row: row.get("category")),
    ("Asunto", lambda row: row.get("subject")),
    ("Apartamento", lambda row: row.get("apartment")),
    ("Estado", lambda row: _label("pqrs", row.get("status"))),
    ("Plazo", lambda row: _label("semaphore", row.get("semaphore"))),
    ("Vence", lambda row: texts.date_es(row.get("dueDate"))),
    ("Última actualización", lambda row: texts.date_es(row.get("updatedAt"))),
    ("Archivada", lambda row: _yes(row.get("isArchived"))),
)

RESERVATION_COLUMNS = (
    ("Zona", lambda row: row.get("commonAreaName")),
    ("Fecha", lambda row: texts.date_es(row.get("date"))),
    ("Horario", lambda row: row.get("timeSlot")),
    ("Personas", lambda row: row.get("attendees")),
    ("Apartamento", lambda row: row.get("apartment")),
    ("Estado", lambda row: _label("reservation", row.get("status"))),
    ("Solicitada", lambda row: texts.date_es(row.get("createdAt"))),
    ("La hizo la administración", lambda row: _yes(row.get("createdByAdministration"))),
    ("Archivada", lambda row: _yes(row.get("isArchived"))),
)

PACKAGE_COLUMNS = (
    ("Apartamento", lambda row: row.get("apartment")),
    ("Descripción", lambda row: row.get("description")),
    ("Transportadora", lambda row: row.get("carrier")),
    ("Estado", lambda row: _label("package", row.get("status"))),
    ("Llegó", lambda row: texts.date_es(row.get("arrivedAt"))),
    ("Entregado", lambda row: texts.date_es(row.get("deliveredAt"))),
    ("Lo recibió", lambda row: row.get("deliveredTo")),
    ("Archivado", lambda row: _yes(row.get("isDeleted"))),
)


def _document_text(row):
    if row.get("hasDocument"):
        return "Lo dio"
    return "No quiso darlo" if row.get("documentRefused") else ""


VISIT_COLUMNS = (
    ("Visitante", lambda row: row.get("visitorName")),
    ("Tipo", lambda row: texts.visit_type_text(row.get("type"))),
    ("Apartamento", lambda row: row.get("apartment")),
    ("Documento", _document_text),
    ("Autorización", lambda row: _label("visit", row.get("approvalStatus"))),
    ("Cómo se autorizó", lambda row: texts.authorization_method_text(row.get("authorizationMethod"), True)),
    ("Llegó a la portería", lambda row: texts.date_es(row.get("createdAt"))),
    ("Entró", lambda row: texts.date_es(row.get("enteredAt"))),
    ("Salió", lambda row: texts.date_es(row.get("exitedAt"))),
)

VEHICLE_COLUMNS = (
    ("Placa", lambda row: row.get("plate")),
    ("Apartamento", lambda row: row.get("apartment")),
    ("Parqueadero", lambda row: row.get("spotCode")),
    ("Entró", lambda row: texts.date_es(row.get("enteredAt"))),
    ("Salió", lambda row: texts.date_es(row.get("exitedAt"))),
    ("Pasó el tiempo permitido", lambda row: _yes(row.get("isOverdue"))),
)

USER_COLUMNS = (
    ("Nombre", lambda row: row.get("fullName") or row.get("name")),
    ("Rol", lambda row: ROLE_TEXTS.get(row.get("role"), row.get("role"))),
    ("Apartamento", lambda row: row.get("apartment") or ""),
    ("Tipo de residente", lambda row: OCCUPANCY_TEXTS.get(row.get("occupancyType"), "")
     if row.get("role") == "RESIDENT" else ""),
    ("Cuenta", lambda row: "Activa" if row.get("isActive") else "Desactivada"),
)


def filters_text(pairs):
    """Los filtros que tenía la lista, en palabras: «Estado: Abierta · Búsqueda: luz»."""
    return " · ".join(f"{label}: {value}" for label, value in pairs if value)


def excel_download(kind, title, api, path, key, params, filters, columns, back_url):
    """Arma y entrega el Excel de una lista; si la API falla, vuelve a la lista con el aviso.

    ``params`` son los filtros tal como se los manda la lista a la API (sin página) y ``filters``
    los mismos en palabras, para la hoja «Acerca de» y para la auditoría.
    """
    rows, failure = fetch_all(api, path, key, max_pages=MAX_PAGES, **params)
    if failure is not None:
        flash(failure.error, "error")
        return redirect(back_url)
    headers = [header for header, _value in columns]
    table = [[value(row) for _header, value in columns] for row in rows]
    about = [
        ("Lista", title),
        ("Descargado por", g.web_user.full_name),
        ("Fecha", colombia_now().strftime("%d/%m/%Y %H:%M")),
        ("Filtros", filters or "Sin filtros: toda la lista"),
        ("Filas", len(table)),
        ("Datos personales", PRIVACY_NOTE),
    ]
    if len(table) >= MAX_ROWS:
        about.append(("Ojo", f"Salen solo las primeras {MAX_ROWS} filas: usa los filtros para acotar la lista."))
    content = generate_list_xlsx(title, headers, table, about)
    # Se anota cuando el archivo ya está armado: la auditoría dice lo que de verdad se entregó.
    add_audit_log(
        "export", None, kind, {"lista": title, "filtros": filters or "", "filas": len(table)}, actor=g.web_user
    )
    db.session.commit()
    return xlsx_response(content, f"DOMUX_{kind}_{colombia_today().isoformat()}.xlsx")


def xlsx_response(content, filename):
    """El archivo de Excel como descarga (no se abre en el navegador ni se guarda en caché)."""
    response = Response(content, mimetype=MIME_XLSX)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "no-store"
    return response
