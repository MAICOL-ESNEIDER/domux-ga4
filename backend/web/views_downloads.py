"""La zona «Descargas» de la web: un solo lugar para sacar información de la unidad.

* Descarga a la medida: el administrador marca qué quiere (PQRS, reservas, visitas, paquetes…), elige
  las fechas y, si quiere, un apartamento. Sale un Excel con una hoja por tipo, que junta lo que sigue
  en la base de datos con lo que ya está en el archivo histórico.
* Una sola PQRS o una sola reserva, con su conversación, desde su propia página.
* El historial de lo que se ha descargado: quién, qué y cuándo.

Desde aquí también se llega al archivo histórico, a la copia de respaldo y al respaldo legal. Antes de
una descarga a la medida se pide otra vez la contraseña; todas quedan en la auditoría.
"""

import json

from flask import abort, flash, g, redirect, render_template, request, url_for

from extensions import db
from models import AuditLog, Pqrs, Reservation
from services.audit_service import add_audit_log
from services.excel_service import generate_workbook_xlsx
from services.history_archive_service import ArchiveError
from time_utils import colombia_now, colombia_today, to_colombia
from web import bp, downloads, texts
from web.exports import PRIVACY_NOTE, xlsx_response
from web.security import login_required, password_confirmation_required

#: Cómo se llama en el historial cada cosa que se descarga.
HISTORY_LABELS = {
    "history_downloaded": "Archivo histórico",
    "history_archived": "Pasó registros al archivo histórico",
    "history_restored": "Volvió a cargar un archivo histórico",
    "copia_respaldo": "Copia de respaldo",
    "respaldo_legal": "Respaldo legal",
    "attachment_downloaded": "Adjunto",
    "descarga_a_la_medida": "Descarga a la medida",
    "pqrs_individual": "Una PQRS",
    "reserva_individual": "Una reserva",
}
HISTORY_SIZE = 15


def _choice():
    """Lo que la persona eligió en el formulario, ya revisado."""
    known = {key for key, _label in downloads.CHOICES}
    keys = [key for key in request.args.getlist("tipo") if key in known]
    period = request.args.get("periodo", "mes")
    if period not in {key for key, _label in downloads.PERIODS}:
        period = "mes"
    since_text = request.args.get("desde", "").strip()
    until_text = request.args.get("hasta", "").strip()
    since, until, problem = downloads.period_range(period, since_text, until_text)
    apartments = downloads.apartment_choices()
    try:
        apartment_id = int(request.args.get("apto", "") or 0)
    except ValueError:
        apartment_id = 0
    if apartment_id not in {apartment for apartment, _label in apartments}:
        apartment_id = 0
    return {
        "keys": keys, "period": period, "since_text": since_text, "until_text": until_text,
        "since": since, "until": until, "problem": problem, "apartment_id": apartment_id,
        "apartments": apartments, "apartment_label": dict(apartments).get(apartment_id, ""),
    }


def _history():
    """Las últimas descargas, de la más reciente a la más antigua."""
    logs = (
        AuditLog.query
        .filter(db.or_(AuditLog.entity_type.in_(("export", "archive")), AuditLog.action == "attachment_downloaded"))
        .order_by(AuditLog.id.desc())
        .limit(HISTORY_SIZE)
        .all()
    )
    rows = []
    for log in logs:
        try:
            details = json.loads(log.details) if log.details else {}
        except ValueError:
            details = {}
        if not isinstance(details, dict):
            details = {}
        what = HISTORY_LABELS.get(log.action) or details.get("lista") or "Lista en Excel"
        extra = details.get("lista") if log.action in ("descarga_a_la_medida",) else details.get("tipo")
        if log.action == "attachment_downloaded":
            extra = {"pqrs": "de una PQRS", "reservation": "de una reserva"}.get(log.entity_type, "")
        rows.append({
            "when": to_colombia(log.created_at).strftime("%d/%m/%Y %H:%M"),
            "who": log.actor.full_name if log.actor else "—",
            "what": what if not extra or extra == what else f"{what}: {extra}",
            "rows": details.get("filas", details.get("registros", "")),
        })
    return rows


@bp.get("/descargas")
@login_required
def downloads_page():
    choice = _choice()
    summary = None
    if request.args.get("contar") and choice["keys"] and not choice["problem"]:
        try:
            summary = downloads.collect(choice["keys"], choice["since"], choice["until"], choice["apartment_id"])
        except ArchiveError as error:
            flash(str(error), "error")
    elif request.args.get("contar") and choice["problem"]:
        flash(choice["problem"], "error")
    elif request.args.get("contar"):
        flash("Marca al menos una cosa para descargar.", "error")
    return render_template(
        "web/downloads.html",
        choice=choice, choices=downloads.CHOICES, periods=downloads.PERIODS, summary=summary,
        total=sum(sheet["count"] for sheet in summary) if summary else 0,
        archived=sum(sheet["archived"] for sheet in summary) if summary else 0,
        period_text=downloads.period_text(choice["since"], choice["until"]) if not choice["problem"] else "",
        history=_history(),
    )


@bp.get("/descargas/excel")
@login_required
@password_confirmation_required("web.downloads_page")
def downloads_excel():
    choice = _choice()
    back = url_for("web.downloads_page", **request.args.to_dict(flat=False))
    if not choice["keys"]:
        flash("Marca al menos una cosa para descargar.", "error")
        return redirect(back)
    if choice["problem"]:
        flash(choice["problem"], "error")
        return redirect(back)
    try:
        sheets = downloads.collect(choice["keys"], choice["since"], choice["until"], choice["apartment_id"])
    except ArchiveError as error:
        flash(str(error), "error")
        return redirect(back)
    total = sum(sheet["count"] for sheet in sheets)
    archived = sum(sheet["archived"] for sheet in sheets)
    names = ", ".join(sheet["label"] for sheet in sheets)
    period = downloads.period_text(choice["since"], choice["until"])
    filters = period + (f" · {choice['apartment_label']}" if choice["apartment_label"] else "")
    about = [
        ("Descarga", names),
        ("Descargado por", g.web_user.full_name),
        ("Fecha", colombia_now().strftime("%d/%m/%Y %H:%M")),
        ("Fechas de los registros", period),
        ("Apartamento", choice["apartment_label"] or "Todos"),
        ("Filas", total),
        ("Del archivo histórico", archived),
        ("Nota", "La columna «Dónde está» dice si el registro sigue en la base de datos o ya está en el "
                 "archivo histórico. Las fotos y los demás adjuntos no van en este archivo."),
        ("Datos personales", PRIVACY_NOTE),
    ]
    content = generate_workbook_xlsx(
        [(sheet["label"], sheet["headers"], sheet["rows"]) for sheet in sheets], about,
    )
    add_audit_log(
        "export", None, "descarga_a_la_medida",
        {"lista": names, "filtros": filters, "filas": total, "delArchivo": archived},
        actor=g.web_user,
    )
    db.session.commit()
    return xlsx_response(content, f"DOMUX_descarga_{colombia_today().isoformat()}.xlsx")


# --- Un solo registro -----------------------------------------------------------------------------------

def _conversation_rows(messages):
    return [
        [
            to_colombia(message.created_at).strftime("%d/%m/%Y %H:%M") if message.created_at else "",
            message.author.full_name if message.author else "",
            downloads.ROLE_TEXTS.get(message.author_role, message.author_role),
            message.message or "",
            "Sí" if message.media_url else "No",
        ]
        for message in messages
    ]


CONVERSATION_HEADERS = ("Fecha", "Quién", "Rol", "Mensaje", "Trae adjunto")


def _single_download(kind, title, name, facts, messages):
    about = [
        ("Descarga", title),
        ("Descargado por", g.web_user.full_name),
        ("Fecha", colombia_now().strftime("%d/%m/%Y %H:%M")),
        ("Nota", "Los adjuntos no van en este archivo: se ven y se descargan desde la página."),
        ("Datos personales", PRIVACY_NOTE),
    ]
    content = generate_workbook_xlsx(
        [(name, ("Dato", "Valor"), facts), ("Conversación", CONVERSATION_HEADERS, _conversation_rows(messages))],
        about,
    )
    add_audit_log("export", None, kind, {"lista": title, "filas": 1}, actor=g.web_user)
    db.session.commit()
    return xlsx_response(content, f"DOMUX_{title.replace(' ', '_')}.xlsx")


@bp.get("/pqrs/<int:pqrs_id>/descargar")
@login_required
def pqrs_download(pqrs_id):
    """Una sola PQRS con su conversación, en Excel."""
    pqrs = db.session.get(Pqrs, pqrs_id)
    if pqrs is None:
        abort(404)
    resident = pqrs.resident
    facts = [
        ("Radicado", pqrs.radicado or ""),
        ("Radicada", to_colombia(pqrs.created_at).strftime("%d/%m/%Y %H:%M") if pqrs.created_at else ""),
        ("Residente", resident.full_name if resident else ""),
        ("Apartamento", (resident.apartment if resident else "") or ""),
        ("Tipo", pqrs.category or ""),
        ("Asunto", pqrs.subject or ""),
        ("Mensaje", pqrs.message or ""),
        ("Estado", texts.badge_info("pqrs", pqrs.status)["label"]),
        ("Respuesta de la administración", pqrs.admin_response or ""),
        ("Fecha del hecho", texts.date_es(pqrs.incident_date)),
        ("Archivada", "Sí" if pqrs.is_archived else "No"),
    ]
    title = f"PQRS {pqrs.radicado or pqrs.id}"
    return _single_download("pqrs_individual", title, "PQRS", facts, pqrs.conversation)


@bp.get("/reservas/<int:res_id>/descargar")
@login_required
def reservation_download(res_id):
    """Una sola reserva con su conversación, en Excel."""
    reservation = db.session.get(Reservation, res_id)
    if reservation is None:
        abort(404)
    resident = reservation.resident
    area = reservation.common_area
    facts = [
        ("Zona", area.name if area else ""),
        ("Fecha de la reserva", texts.date_es(reservation.date)),
        ("Horario", reservation.time_slot or ""),
        ("Residente", resident.full_name if resident else ""),
        ("Apartamento", (resident.apartment if resident else "") or ""),
        ("Asistentes", reservation.attendees if reservation.attendees is not None else ""),
        ("Estado", texts.badge_info("reservation", reservation.status)["label"]),
        ("Pedida el", to_colombia(reservation.created_at).strftime("%d/%m/%Y %H:%M") if reservation.created_at else ""),
    ]
    return _single_download("reserva_individual", f"Reserva {reservation.id}", "Reserva", facts, reservation.messages)
