"""Census import and legal Excel report generation."""

import csv
import io
import json
import re
import secrets
import unicodedata
from datetime import date, datetime
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import false, or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from extensions import db
from models import (
    AuditLog,
    Pet,
    Pqrs,
    PqrsMessage,
    Reservation,
    User,
    Vehicle,
)
from services.structure_service import (
    apartment_by_text,
    assign_parking_codes,
    assign_storage_codes,
    ensure_unit,
)
from time_utils import colombia_today, to_colombia, utc_now
from validators import normalize_phone, validate_colombian_plate

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CENSUS_HEADERS = (
    "Apartamento",
    "Nombre",
    "Apellido",
    "Correo",
    "Telefono",
    "Documento",
    "Fecha_Nacimiento",
    "Tipo_Tenencia",
    "Autorizacion_Parental",
    "Parqueadero",
    "Cuarto_Util",
    "Seguro_Mascotas",
    "Aseguradora_Mascotas",
    "Mascota_Nombre",
    "Mascota_Especie",
    "Mascota_Raza",
    "Mascota_Edad",
    "Vehiculo_Placa",
    "Vehiculo_Tipo",
    "Vehiculo_Marca_Modelo",
    "Vehiculo_Anio",
    "Vehiculo_Color",
)

_COLUMN_ALIASES = {
    "apartamento": "apartment",
    "apto": "apartment",
    "unidad": "apartment",
    "unidadresidencial": "apartment",
    "nombre": "name",
    "nombres": "name",
    "apellido": "last_name",
    "apellidos": "last_name",
    "correo": "email",
    "email": "email",
    "e-mail": "email",
    "telefono": "phone",
    "celular": "phone",
    "movil": "phone",
    "documento": "document_id",
    "cedula": "document_id",
    "identificacion": "document_id",
    "fecha nacimiento": "birth_date",
    "fechanacimiento": "birth_date",
    "tipotenencia": "occupancy_type",
    "tenencia": "occupancy_type",
    "autorizacionparental": "parental_consent",
    "consentimientoparental": "parental_consent",
    "parqueadero": "parking_identifier",
    "cuartoutil": "storage_identifier",
    "seguromascotas": "pet_insurance",
    "aseguradoramascotas": "pet_insurer",
    "mascotanombre": "pet_name",
    "mascotaespecie": "pet_species",
    "mascotaraza": "pet_breed",
    "mascotaedad": "pet_age",
    "vehiculoplaca": "vehicle_plate",
    "vehiculotipo": "vehicle_type",
    "vehiculomarcamodelo": "vehicle_make_model",
    "vehiculoanio": "vehicle_year",
    "vehiculocolor": "vehicle_color",
    "placa": "vehicle_plate",
}


def _normalize_header(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[\s_-]+", "", text.strip().lower())


def _header_key(value):
    normalized = _normalize_header(value)
    return _COLUMN_ALIASES.get(normalized)


def _cell_text(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_bool(value, default=False):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    normalized = _normalize_header(value)
    if normalized in ("si", "true", "1", "yes", "x"):
        return True
    if normalized in ("no", "false", "0"):
        return False
    raise ValueError(f"Valor booleano inválido: {value}")


def _read_rows(file_bytes, filename):
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if extension == "xlsx":
        try:
            workbook = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
            worksheet = workbook["Censo_Residentes"] if "Censo_Residentes" in workbook.sheetnames else workbook.active
            rows = worksheet.iter_rows(values_only=True)
            headers = next(rows, None)
            if headers is None:
                raise ValueError("El archivo Excel está vacío.")
            return list(headers), [(index, row) for index, row in enumerate(rows, start=2)]
        except (BadZipFile, InvalidFileException, OSError, KeyError, ValueError) as error:
            raise ValueError("No se pudo leer el archivo Excel.") from error
    if extension == "csv":
        decoded = None
        for encoding in ("utf-8-sig", "latin-1"):
            try:
                decoded = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("El CSV debe estar codificado en UTF-8 o Latin-1.")
        rows = list(csv.reader(io.StringIO(decoded)))
        if not rows:
            raise ValueError("El archivo CSV está vacío.")
        return rows[0], [(index, row) for index, row in enumerate(rows[1:], start=2)]
    raise ValueError("Formato no soportado. Usa un archivo .xlsx o .csv.")


def _normalized_rows(file_bytes, filename):
    headers, rows = _read_rows(file_bytes, filename)
    columns = {}
    for index, header in enumerate(headers):
        key = _header_key(header)
        if key:
            columns[key] = index
    if "apartment" not in columns or "name" not in columns:
        raise ValueError("El archivo debe incluir como mínimo las columnas Apartamento y Nombre.")

    for row_number, values in rows:
        if not values or not any(value is not None and str(value).strip() for value in values):
            continue
        yield row_number, {
            key: _cell_text(values[index]) if index < len(values) else ""
            for key, index in columns.items()
        }


def _upsert_census_row(row):
    apartment_text = row.get("apartment", "").strip()
    name = row.get("name", "").strip()
    if not apartment_text or not name:
        raise ValueError("Apartamento y Nombre son obligatorios.")
    # El apartamento debe existir en la estructura de la unidad (HU-014 y HU-017).
    apartment = apartment_by_text(apartment_text)
    if apartment is None:
        raise ValueError(
            f"El apartamento «{apartment_text}» no existe: créalo antes en la estructura de la unidad."
        )
    email = row.get("email", "").strip().lower() or None
    document_id = row.get("document_id", "").strip() or None
    if not email and not document_id:
        raise ValueError("Se requiere Correo o Documento para identificar al residente.")
    birth_date = row.get("birth_date", "").strip() or None
    if birth_date:
        try:
            parsed_birth_date = date.fromisoformat(birth_date)
        except ValueError as error:
            raise ValueError("Fecha_Nacimiento debe tener formato YYYY-MM-DD.") from error
        if parsed_birth_date.isoformat() != birth_date or parsed_birth_date > colombia_today():
            raise ValueError("Fecha_Nacimiento no es válida.")
    occupancy_type = row.get("occupancy_type", "").strip().lower() or "propietario"
    if occupancy_type not in ("propietario", "arrendatario", "residente"):
        occupancy_type = "residente"

    identity_filters = []
    if email:
        identity_filters.append(db.func.lower(User.email) == email)
    if document_id:
        identity_filters.append(User.document_id == document_id)
    matches = User.query.filter(or_(*identity_filters)).all()
    if len(matches) > 1:
        raise ValueError("Correo y Documento pertenecen a usuarios distintos.")
    user = matches[0] if matches else None
    created = user is None
    if user is None:
        if email is None:
            email = f"censo-{document_id}@domux.invalid"
        # Sin contraseña conocida: nadie entra hasta que el administrador la restablezca
        # (SEC: ninguna cuenta nace con una clave que otros conozcan).
        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(secrets.token_urlsafe(24)),
            role="RESIDENT",
        )
        db.session.add(user)
    elif email and User.query.filter(
        db.func.lower(User.email) == email, User.id != user.id
    ).first():
        raise ValueError("El correo ya está asociado a otro usuario.")

    user.name = name
    if "last_name" in row:
        user.last_name = row["last_name"].strip()
    user.email = email or user.email
    if "phone" in row:
        # Igual que en la app y la web: se guardan solo los 10 números (sin +57 ni espacios).
        phone, phone_error = normalize_phone(row["phone"])
        if phone_error:
            raise ValueError(phone_error)
        user.phone = phone or None
    if document_id:
        user.document_id = document_id
    user.role = "RESIDENT"
    user.apartment_ref = apartment
    if "occupancy_type" in row:
        user.occupancy_type = occupancy_type
    if "birth_date" in row:
        user.birth_date = birth_date
    if "parental_consent" in row:
        user.parental_consent = _parse_bool(row["parental_consent"])
    user.data_processing_consent = True
    if user.data_processing_consent_at is None:
        user.data_processing_consent_at = utc_now()
    db.session.flush()

    unit = ensure_unit(apartment)
    db.session.flush()
    # Un dato vacío no quita nada: el parqueadero y el cuarto se retiran en la estructura.
    assign_parking_codes(row.get("parking_identifier", ""), apartment)
    assign_storage_codes(row.get("storage_identifier", ""), apartment)
    if "pet_insurer" in row:
        unit.pet_insurer = row["pet_insurer"].strip() or None
    if "pet_insurance" in row:
        unit.pet_insurance = _parse_bool(row["pet_insurance"])

    pet_name = row.get("pet_name", "").strip()
    pet_species = row.get("pet_species", "").strip()
    pet_breed = row.get("pet_breed", "").strip()
    pet_age = row.get("pet_age", "").strip()
    if any((pet_name, pet_species, pet_breed, pet_age)):
        if not all((pet_name, pet_species, pet_breed, pet_age)):
            raise ValueError("Los datos de mascota requieren nombre, especie, raza y edad.")
        try:
            age_years = int(float(pet_age))
        except ValueError as error:
            raise ValueError("Mascota_Edad debe ser un número entero.") from error
        if age_years < 0:
            raise ValueError("Mascota_Edad no puede ser negativa.")
        # Solo cuentan las mascotas vigentes; una retirada se vuelve a agregar (TT-032).
        existing_pet = Pet.query.filter_by(
            unit_id=unit.id, name=pet_name, species=pet_species, breed=pet_breed, retired_at=None
        ).first()
        if existing_pet is None:
            db.session.add(Pet(
                unit_id=unit.id,
                name=pet_name,
                species=pet_species,
                breed=pet_breed,
                age_years=age_years,
            ))
        else:
            existing_pet.age_years = age_years

    plate = row.get("vehicle_plate", "").strip().upper()
    vehicle_type = row.get("vehicle_type", "").strip().lower()
    make_model = row.get("vehicle_make_model", "").strip()
    vehicle_year = row.get("vehicle_year", "").strip()
    if any((plate, vehicle_type, make_model, vehicle_year)):
        if not all((plate, vehicle_type, make_model, vehicle_year)):
            raise ValueError("Los datos de vehículo requieren placa, tipo, marca/modelo y año.")
        if error := validate_colombian_plate(plate):
            raise ValueError(error)
        try:
            year = int(float(vehicle_year))
        except ValueError as error:
            raise ValueError("Vehiculo_Anio debe ser un año numérico.") from error
        if not 1900 <= year <= colombia_today().year + 1:
            raise ValueError("Vehiculo_Anio está fuera de rango.")
        normalized_plate = re.sub(r"[\s-]", "", plate)
        # Solo cuentan los vehículos vigentes: una placa retirada puede volver (IDX-013).
        existing_vehicle = Vehicle.query.filter_by(plate=normalized_plate, retired_at=None).first()
        if existing_vehicle is None:
            db.session.add(Vehicle(
                unit_id=unit.id,
                plate=normalized_plate,
                vehicle_type=vehicle_type[:10],
                make_model=make_model[:120],
                year=year,
                registered_owner=user.full_name[:120],
                color=row.get("vehicle_color", "").strip() or None,
            ))
        elif existing_vehicle.unit_id == unit.id:
            existing_vehicle.vehicle_type = vehicle_type[:10]
            existing_vehicle.make_model = make_model[:120]
            existing_vehicle.year = year
            existing_vehicle.registered_owner = user.full_name[:120]
            existing_vehicle.color = row.get("vehicle_color", "").strip() or None

    return created, apartment.id


def import_census_from_bytes(
    file_bytes: bytes, filename: str, actor_user: User
) -> dict[str, object]:
    """Create or update residents and unit data from an Excel workbook or CSV."""
    created_users = 0
    updated_users = 0
    units = set()
    errors = []
    row_count = 0
    try:
        for row_number, row in _normalized_rows(file_bytes, filename):
            row_count += 1
            try:
                with db.session.begin_nested():
                    created, apartment = _upsert_census_row(row)
                    db.session.flush()
                if created:
                    created_users += 1
                else:
                    updated_users += 1
                units.add(apartment)
            except (ValueError, SQLAlchemyError) as error:
                message = (
                    str(error)
                    if isinstance(error, ValueError)
                    else "No se pudo guardar la fila por conflicto con los datos existentes."
                )
                errors.append(f"Fila {row_number}: {message}")
        db.session.add(AuditLog(
            entity_type="census",
            entity_id=None,
            action="imported",
            actor_id=actor_user.id if actor_user else None,
            actor_role=actor_user.role if actor_user else None,
            details=json.dumps({
                "filename": filename,
                "createdUsers": created_users,
                "updatedUsers": updated_users,
                "unitsProcessed": len(units),
                "rowCount": row_count,
                "errorCount": len(errors),
            }),
        ))
        db.session.commit()
    except (ValueError, SQLAlchemyError):
        db.session.rollback()
        raise
    return {
        "createdUsers": created_users,
        "updatedUsers": updated_users,
        "unitsProcessed": len(units),
        "errors": errors,
    }


def _format_datetime(value):
    """Fecha y hora en hora de Colombia, como en la app (ADR-011)."""
    return to_colombia(value).strftime("%Y-%m-%d %H:%M:%S") if value else None


def _style_sheet(worksheet):
    header_fill = PatternFill("solid", fgColor="17365D")
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column in worksheet.columns:
        values = [len(str(cell.value or "")) for cell in column]
        width = min(max(max(values, default=10) + 2, 12), 45)
        worksheet.column_dimensions[column[0].column_letter].width = width


def _append_sheet(workbook, name, headers, rows):
    worksheet = workbook.create_sheet(name)
    worksheet.append(headers)
    for row in rows:
        worksheet.append([
            "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
            else value
            for value in row
        ])
    _style_sheet(worksheet)
    return worksheet


def generate_census_template_xlsx() -> bytes:
    """Generate an example census workbook with a styled header row."""
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Censo_Residentes"
    worksheet.append(CENSUS_HEADERS)
    worksheet.append((
        "Torre 1 Apto 101", "María", "Pérez", "maria.perez@example.com",
        "3001234567", "1234567890", "1990-05-14", "propietario", "No",
        "P-101", "CU-101", "Sí", "Aseguradora Ejemplo",
        "Luna", "Perro", "Criollo", 3, "ABC123", "carro",
        "Toyota Corolla", 2021, "Blanco",
    ))
    worksheet.append((
        "Torre 2 Apto 202", "Carlos", "Gómez", "carlos.gomez@example.com",
        "3107654321", "9876543210", "1985-09-22", "arrendatario", "Sí",
        "P-202", "CU-202", "No", "",
        "", "", "", "", "XYZ789", "moto", "Honda CB", 2020, "Negro",
    ))
    _style_sheet(worksheet)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def generate_legal_report_xlsx(
    include_active=True, include_archived=True
) -> tuple[bytes, dict[str, int]]:
    """Export PQRS, conversation messages, reservations, and audit history."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    pqrs_query = Pqrs.query
    reservation_query = Reservation.query
    if include_active and not include_archived:
        pqrs_query = pqrs_query.filter(Pqrs.is_archived.is_(False))
        reservation_query = reservation_query.filter(Reservation.is_archived.is_(False))
    elif include_archived and not include_active:
        pqrs_query = pqrs_query.filter(Pqrs.is_archived.is_(True))
        reservation_query = reservation_query.filter(Reservation.is_archived.is_(True))
    elif not include_active and not include_archived:
        pqrs_query = pqrs_query.filter(false())
        reservation_query = reservation_query.filter(false())

    pqrs_items = pqrs_query.order_by(Pqrs.id).all()
    pqrs_ids = [item.id for item in pqrs_items]
    messages = PqrsMessage.query.filter(PqrsMessage.pqrs_id.in_(pqrs_ids)).order_by(
        PqrsMessage.created_at, PqrsMessage.id
    ).all() if pqrs_ids else []
    reservations = reservation_query.order_by(Reservation.id).all()
    audit_logs = AuditLog.query.order_by(AuditLog.created_at, AuditLog.id).all()

    _append_sheet(
        workbook,
        "PQRS_Radicados",
        (
            "ID", "Radicado", "Fecha Creación", "Fecha Actualización", "Estado", "Archivada",
            "Fecha Archivo", "Categoría", "Asunto", "Descripción", "Respuesta Admin",
            "Residente", "Documento", "Apartamento", "Creada por Admin",
            "Calificación Satisfacción", "Comentario",
        ),
        [
            (
                item.id, item.radicado, _format_datetime(item.created_at),
                _format_datetime(item.updated_at),
                item.status, bool(item.is_archived), _format_datetime(item.archived_at),
                item.category, item.subject, item.message, item.admin_response,
                item.resident.full_name if item.resident else None,
                item.resident.document_id if item.resident else None,
                item.resident.apartment if item.resident else None,
                item.created_by_admin_id,
                item.satisfaction_ratings[-1].rating if item.satisfaction_ratings else None,
                item.satisfaction_ratings[-1].comment if item.satisfaction_ratings else None,
            )
            for item in pqrs_items
        ],
    )
    _append_sheet(
        workbook,
        "PQRS_Historial_Chat",
        ("ID Mensaje", "ID PQRS", "Fecha/Hora", "Autor", "Rol Autor", "Mensaje", "Tipo Adjunto"),
        [
            (
                item.id, item.pqrs_id, _format_datetime(item.created_at),
                item.author.full_name if item.author else None, item.author_role,
                item.message, item.media_type,
            )
            for item in messages
        ],
    )
    _append_sheet(
        workbook,
        "Reservas_Zonas_Comunes",
        (
            "ID Reserva", "Fecha Creación", "Zona Común", "Fecha Reservada",
            "Franja Horaria", "Estado", "Archivada", "Residente", "Apartamento",
            "Solicitada por Menor", "Creada por Admin", "Cantidad Mensajes",
        ),
        [
            (
                item.id, _format_datetime(item.created_at),
                item.common_area.name if item.common_area else None,
                item.date, item.time_slot, item.status, bool(item.is_archived),
                item.resident.full_name if item.resident else None,
                item.resident.apartment if item.resident else None,
                bool(item.resident and item.resident.is_minor),
                item.created_by_admin_id, len(item.messages),
            )
            for item in reservations
        ],
    )
    _append_sheet(
        workbook,
        "Logs_Auditoria",
        (
            "ID Log", "Fecha/Hora", "Entidad", "ID Entidad", "Acción",
            "Usuario Ejecutor", "Rol", "Detalles",
        ),
        [
            (
                item.id, _format_datetime(item.created_at), item.entity_type,
                item.entity_id, item.action, item.actor.full_name if item.actor else None,
                item.actor_role, item.details,
            )
            for item in audit_logs
        ],
    )
    counts = {
        "pqrsCount": len(pqrs_items),
        "pqrsMessagesCount": len(messages),
        "reservationsCount": len(reservations),
        "auditLogsCount": len(audit_logs),
    }
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue(), counts
