import base64
import binascii
from datetime import date, datetime

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from auth import role_required, token_required
from errors import error_response
from extensions import db
from models import (
    DevicePushToken,
    HouseholdMember,
    ParkingSpot,
    Pet,
    ResidentialUnit,
    ROLES,
    StorageRoom,
    User,
    Vehicle,
    VisitQrPass,
)
from routes.common import json_body, page_args
from services.audit_service import add_audit_log
from services.login_attempt_service import LOGIN, PIN, register_success
from services.excel_service import (
    MIME_XLSX,
    generate_census_template_xlsx,
    generate_legal_report_xlsx,
    import_census_from_bytes,
)
from services.structure_service import (
    apartment_by_text,
    apartment_from_payload,
    ensure_unit,
    find_apartment,
)
from services.summary_service import admin_summary
from validators import (
    HOUSEHOLD_RELATIONSHIPS,
    OCCUPANCY_TYPES,
    normalize_phone,
    parse_optional_bool,
    require_non_empty_fields,
    validate_occupancy_type,
    validate_pin,
    validate_strong_password,
    validate_colombian_plate,
    validate_iso_date,
)
from time_utils import colombia_today, utc_now

bp = Blueprint("admin", __name__, url_prefix="/api")

#: Todo residente vinculado a un apartamento tiene tipo de ocupación (RN-007, HU-017).
OCCUPANCY_REQUIRED_MESSAGE = (
    "Indica el tipo de ocupación del residente: propietario, arrendatario o residente."
)


def _encode_base64(value):
    return base64.b64encode(value).decode("ascii")


def _normalize_role(value):
    return value.strip().upper() if isinstance(value, str) else None


@bp.get("/admin/census-template")
@token_required
@role_required("ADMIN")
def get_census_template():
    return jsonify({
        "fileName": "Plantilla_Censo_DOMUX.xlsx",
        "mimeType": MIME_XLSX,
        "base64": _encode_base64(generate_census_template_xlsx()),
    })


@bp.post("/admin/import-census")
@token_required
@role_required("ADMIN")
def post_import_census():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    encoded_file = data.get("fileBase64")
    filename = data.get("fileName")
    if not isinstance(encoded_file, str) or not encoded_file:
        return error_response(400, "fileBase64 es obligatorio.")
    if not isinstance(filename, str) or not filename.strip():
        return error_response(400, "fileName es obligatorio.")
    if encoded_file.startswith("data:"):
        header, separator, encoded_file = encoded_file.partition(",")
        if not separator or ";base64" not in header.lower():
            return error_response(400, "El prefijo data URL debe usar base64.")
    try:
        file_bytes = base64.b64decode(encoded_file, validate=True)
    except (binascii.Error, ValueError):
        return error_response(400, "fileBase64 no contiene datos base64 válidos.")
    try:
        result = import_census_from_bytes(file_bytes, filename.strip(), g.current_user)
    except ValueError as error:
        return error_response(400, str(error))
    message = "Importación del censo procesada."
    if result["createdUsers"]:
        # Las cuentas nuevas nacen con una clave al azar que nadie conoce (sin contraseña común).
        message += " Los residentes nuevos aún no tienen contraseña: asígnala desde la lista de usuarios."
    return jsonify({"message": message, **result})


@bp.get("/admin/summary")
@token_required
@role_required("ADMIN")
def get_admin_summary():
    """Lo pendiente de hoy: contadores y las PQRS y reservas más urgentes (HU-081)."""
    return jsonify(admin_summary(g.current_user))


@bp.get("/admin/export/legal-report")
@token_required
@role_required("ADMIN")
def get_legal_report():
    workbook_bytes, counts = generate_legal_report_xlsx()
    return jsonify({
        "message": "Reporte legal generado exitosamente.",
        "fileName": f"Reporte_Legal_DOMUX_{colombia_today().isoformat()}.xlsx",
        "mimeType": MIME_XLSX,
        "base64": _encode_base64(workbook_bytes),
        **counts,
    })


@bp.get("/users")
@bp.get("/admin/users")
@token_required
@role_required("ADMIN")
def get_users():
    page, page_size = page_args()

    query = User.query
    search = (request.args.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        member_match = db.session.query(HouseholdMember.id).join(
            ResidentialUnit, HouseholdMember.unit_id == ResidentialUnit.id
        ).filter(
            ResidentialUnit.apartment_id == User.apartment_id,
            HouseholdMember.retired_at.is_(None),
            db.or_(
                HouseholdMember.name.ilike(pattern),
                HouseholdMember.last_name.ilike(pattern),
                HouseholdMember.document_id.ilike(pattern),
            ),
        ).exists()
        query = query.filter(db.or_(
            User.name.ilike(pattern),
            (User.name + " " + User.last_name).ilike(pattern),
            User.last_name.ilike(pattern),
            User.email.ilike(pattern),
            User.phone.ilike(pattern),
            User.document_id.ilike(pattern),
            User.apartment.ilike(pattern),
            member_match,
        ))

    role = request.args.get("role")
    if role:
        normalized_role = _normalize_role(role)
        if normalized_role not in ROLES:
            return error_response(400, "Rol inválido.")
        query = query.filter(User.role == normalized_role)

    occupancy = request.args.get("occupancyType")
    if occupancy:
        if occupancy not in OCCUPANCY_TYPES:
            return error_response(400, "Tipo de residente inválido.")
        query = query.filter(User.occupancy_type == occupancy, User.role == "RESIDENT")

    apartment_from = request.args.get("apartmentFrom")
    apartment_to = request.args.get("apartmentTo")
    if apartment_from:
        if not apartment_from.isdigit():
            return error_response(400, "El apartamento inicial debe ser numérico.")
        query = query.filter(User.apartment_number >= int(apartment_from))
    if apartment_to:
        if not apartment_to.isdigit():
            return error_response(400, "El apartamento final debe ser numérico.")
        query = query.filter(User.apartment_number <= int(apartment_to))
    if apartment_from and apartment_to and int(apartment_from) > int(apartment_to):
        return error_response(400, "El apartamento inicial no puede superar al final.")

    for parameter, column in (
        ("hasPets", db.session.query(Pet.id).join(
            ResidentialUnit, Pet.unit_id == ResidentialUnit.id
        ).filter(
            ResidentialUnit.apartment_id == User.apartment_id, Pet.retired_at.is_(None)
        ).exists()),
        ("hasVehicles", db.session.query(Vehicle.id).join(
            ResidentialUnit, Vehicle.unit_id == ResidentialUnit.id
        ).filter(
            ResidentialUnit.apartment_id == User.apartment_id, Vehicle.retired_at.is_(None)
        ).exists()),
        # Los parqueaderos y cuartos útiles se asignan al apartamento (HU-015 y HU-016).
        ("hasParking", db.session.query(ParkingSpot.id).filter(
            ParkingSpot.apartment_id == User.apartment_id,
            ParkingSpot.kind == "residente",
            ParkingSpot.retired_at.is_(None),
        ).exists()),
        ("hasStorage", db.session.query(StorageRoom.id).filter(
            StorageRoom.apartment_id == User.apartment_id,
            StorageRoom.retired_at.is_(None),
        ).exists()),
    ):
        value, error = parse_optional_bool(request.args.get(parameter), parameter)
        if error:
            return error_response(400, error)
        if value is not None:
            query = query.filter(column if value else ~column, User.role == "RESIDENT")

    active, error = parse_optional_bool(request.args.get("isActive"), "isActive")
    if error:
        return error_response(400, error)
    if active is not None:
        query = query.filter(User.is_active.is_(active))

    minimum_age = request.args.get("minAge")
    maximum_age = request.args.get("maxAge")
    if minimum_age is not None or maximum_age is not None:
        try:
            minimum_age = int(minimum_age) if minimum_age is not None else None
            maximum_age = int(maximum_age) if maximum_age is not None else None
        except ValueError:
            return error_response(400, "Los límites de edad deben ser números.")
        if (
            (minimum_age is not None and minimum_age < 0)
            or (maximum_age is not None and maximum_age < 0)
            or (minimum_age is not None and maximum_age is not None and minimum_age > maximum_age)
        ):
            return error_response(400, "El rango de edad es inválido.")
        today = colombia_today()

        def years_before(years):
            try:
                return today.replace(year=today.year - years)
            except ValueError:
                return today.replace(year=today.year - years, day=28)

        user_birth_date_conditions = [User.birth_date.isnot(None)]
        member_birth_date_conditions = []
        if minimum_age is not None:
            latest_birth_date = years_before(minimum_age)
            user_birth_date_conditions.append(User.birth_date <= latest_birth_date.isoformat())
            member_birth_date_conditions.append(
                HouseholdMember.birth_date <= latest_birth_date.isoformat()
            )
        if maximum_age is not None:
            earliest_birth_date = years_before(maximum_age + 1)
            user_birth_date_conditions.append(User.birth_date > earliest_birth_date.isoformat())
            member_birth_date_conditions.append(
                HouseholdMember.birth_date > earliest_birth_date.isoformat()
            )
        member_age_match = db.session.query(HouseholdMember.id).join(
            ResidentialUnit, HouseholdMember.unit_id == ResidentialUnit.id
        ).filter(
            ResidentialUnit.apartment_id == User.apartment_id,
            HouseholdMember.retired_at.is_(None),
            *member_birth_date_conditions,
        ).exists()
        query = query.filter(
            db.or_(db.and_(*user_birth_date_conditions), member_age_match),
            User.role == "RESIDENT",
        )

    total = query.count()
    users = query.order_by(User.apartment_number, User.apartment, User.id).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return jsonify({
        "users": [user.to_dict() for user in users],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": (total + page_size - 1) // page_size,
    })


@bp.get("/users/<int:user_id>")
@bp.get("/admin/users/<int:user_id>")
@token_required
@role_required("ADMIN")
def get_user(user_id):
    """Un usuario por su id: con él la web de administración abre la ficha para editarlo."""
    user = db.session.get(User, user_id)
    if user is None:
        return error_response(404, "Usuario no encontrado")
    return jsonify({"user": user.to_dict()})


@bp.post("/users")
@bp.post("/admin/users")
@token_required
@role_required("ADMIN")
def create_user():
    data, failure = json_body()
    if failure:
        return failure
    validation_error = require_non_empty_fields(
        data,
        (("name", "nombre"), ("email", "correo"), ("password", "contraseña")),
    )
    if validation_error:
        return error_response(400, validation_error)

    email = data["email"].strip().lower()
    role = _normalize_role(data.get("role"))
    occupancy_type = data.get("occupancyType", "propietario")
    if "@" not in email or role not in ROLES:
        return error_response(400, "Correo o rol inválido")
    password_error = validate_strong_password(data["password"])
    if password_error:
        return error_response(400, password_error)
    # El residente se vincula a un apartamento que existe en la estructura (HU-017).
    apartment = apartment_from_payload(data) if role == "RESIDENT" else None
    if role == "RESIDENT" and apartment is None:
        return error_response(400, "El residente necesita un apartamento")
    if role == "RESIDENT" and "occupancyType" not in data:
        return error_response(400, OCCUPANCY_REQUIRED_MESSAGE)
    if role == "RESIDENT" and data.get("dataProcessingConsent") is not True:
        return error_response(400, "Debes registrar la autorización de tratamiento de datos del residente.")
    if "birthDate" in data:
        if error := validate_iso_date(data["birthDate"]):
            return error_response(400, error)
        if datetime.strptime(data["birthDate"], "%Y-%m-%d").date() > colombia_today():
            return error_response(400, "La fecha de nacimiento no puede ser futura.")
    parental_consent = data.get("parentalConsent", False)
    if not isinstance(parental_consent, bool):
        return error_response(400, "parentalConsent debe ser verdadero o falso.")
    if not isinstance(occupancy_type, str) or occupancy_type not in OCCUPANCY_TYPES:
        return error_response(400, validate_occupancy_type(occupancy_type))
    for field in ("lastName", "phone", "documentId"):
        if field in data and not isinstance(data[field], str):
            return error_response(400, f"El campo '{field}' debe ser texto")
    phone, phone_error = normalize_phone(data.get("phone"))
    if phone_error:
        return error_response(400, phone_error)
    if User.query.filter(db.func.lower(User.email) == email).first():
        return error_response(409, "Ese correo ya está registrado")

    user = User(
        name=data["name"].strip(),
        last_name=data.get("lastName", "").strip(),
        email=email,
        phone=phone,
        document_id=data.get("documentId", "").strip(),
        password_hash=generate_password_hash(data["password"]),
        role=role,
        apartment_ref=apartment,
        occupancy_type=occupancy_type,
        social_networks="",
        birth_date=data.get("birthDate"),
        parental_consent=parental_consent,
        data_processing_consent=role == "RESIDENT",
        data_processing_consent_at=utc_now() if role == "RESIDENT" else None,
        is_active=True,
    )
    db.session.add(user)
    if apartment is not None:
        ensure_unit(apartment)
    db.session.commit()
    return jsonify({"message": "Usuario creado", "user": user.to_dict()}), 201


def _close_access_of_deactivated_user(user):
    """Cierra lo que un usuario desactivado todavía podría usar (TT-027).

    Anula sus QR de visita que siguen vigentes (CA-HU-008-02) y borra sus tokens
    de avisos al celular, que no se archivan (DEC-090). Su historial se queda.
    Devuelve cuántos QR se anularon y cuántos tokens se quitaron.
    """
    passes = VisitQrPass.query.filter(
        VisitQrPass.resident_id == user.id,
        VisitQrPass.revoked.is_(False),
        VisitQrPass.valid_until >= colombia_today().isoformat(),
    ).all()
    revoked_at = utc_now()
    for qr_pass in passes:
        qr_pass.revoked = True
        qr_pass.revoked_at = revoked_at
    removed_tokens = DevicePushToken.query.filter_by(user_id=user.id).delete()
    return {"revokedQrPasses": len(passes), "removedPushTokens": removed_tokens}


@bp.put("/users/<int:user_id>")
@bp.put("/admin/users/<int:user_id>")
@token_required
@role_required("ADMIN")
def update_user(user_id):
    data, failure = json_body()
    if failure:
        return failure
    if not data:
        return error_response(400, "Debes proporcionar al menos un dato para actualizar")
    if "password" in data or "passwordHash" in data or "password_hash" in data:
        return error_response(400, "Usa PUT /users/<id>/password para cambiar la contraseña")

    user = db.session.get(User, user_id)
    if user is None:
        return error_response(404, "Usuario no encontrado")
    # Quien administra no se cierra la puerta a sí mismo: si el único administrador se desactivara
    # o se cambiara el rol, nadie podría volver a entrar para arreglarlo.
    if user.id == g.current_user.id:
        if data.get("isActive") is False:
            return error_response(
                409, "No puedes desactivar tu propia cuenta. Pídele a otro administrador que lo haga."
            )
        if "role" in data and _normalize_role(data["role"]) != user.role:
            return error_response(
                409, "No puedes cambiar tu propio rol. Pídele a otro administrador que lo haga."
            )

    if "birthDate" in data:
        if error := validate_iso_date(data["birthDate"]):
            return error_response(400, error)
        if datetime.strptime(data["birthDate"], "%Y-%m-%d").date() > colombia_today():
            return error_response(400, "La fecha de nacimiento no puede ser futura.")
        user.birth_date = data["birthDate"]
    if "parentalConsent" in data:
        if not isinstance(data["parentalConsent"], bool):
            return error_response(400, "parentalConsent debe ser verdadero o falso.")
        user.parental_consent = data["parentalConsent"]

    if "name" in data:
        if not isinstance(data["name"], str):
            return error_response(400, "El nombre debe ser texto")
        user.name = data["name"].strip()
    if "lastName" in data:
        if not isinstance(data["lastName"], str):
            return error_response(400, "El apellido debe ser texto")
        user.last_name = data["lastName"].strip()
    if "email" in data:
        if not isinstance(data["email"], str) or "@" not in data["email"]:
            return error_response(400, "Correo inválido")
        email = data["email"].strip().lower()
        duplicate = User.query.filter(
            db.func.lower(User.email) == email,
            User.id != user.id,
        ).first()
        if duplicate:
            return error_response(409, "Ese correo ya está registrado")
        user.email = email
    if "phone" in data:
        phone, phone_error = normalize_phone(data["phone"])
        if phone_error:
            return error_response(400, phone_error)
        user.phone = phone
    if "documentId" in data:
        if not isinstance(data["documentId"], str):
            return error_response(400, "El documento debe ser texto")
        user.document_id = data["documentId"].strip()

    if "role" in data:
        role = _normalize_role(data["role"])
        if role not in ROLES:
            return error_response(400, "Rol inválido")
        if role == "RESIDENT" and user.role != "RESIDENT":
            if "occupancyType" not in data:
                return error_response(400, OCCUPANCY_REQUIRED_MESSAGE)
            if data.get("dataProcessingConsent") is not True:
                return error_response(
                    400,
                    "Debes registrar la autorización de tratamiento de datos del residente.",
                )
            user.data_processing_consent = True
            user.data_processing_consent_at = utc_now()
        user.role = role
    if user.role != "GUARD":
        # El PIN de turno es solo de los guardias: quien deja de serlo lo pierde (RN-029).
        user.pin_hash = None
    if "occupancyType" in data:
        error = validate_occupancy_type(data["occupancyType"])
        if error:
            return error_response(400, error)
        user.occupancy_type = data["occupancyType"]
    if "apartment" in data or "apartmentId" in data:
        # Un valor nulo desvincula al usuario; uno que no existe en la estructura se rechaza.
        user.apartment_ref = apartment_from_payload(data)
    if user.role == "RESIDENT" and user.apartment_ref is None:
        return error_response(400, "El residente necesita un apartamento")
    if user.role != "RESIDENT":
        user.apartment_ref = None
    else:
        ensure_unit(user.apartment_ref)
    if "isActive" in data:
        if not isinstance(data["isActive"], bool):
            return error_response(400, "isActive debe ser verdadero o falso")
        was_active = user.is_active
        user.is_active = data["isActive"]
        if was_active and not user.is_active:
            add_audit_log("user", user.id, "deactivated", _close_access_of_deactivated_user(user))
        elif not was_active and user.is_active:
            add_audit_log("user", user.id, "reactivated")

    if user.role == "RESIDENT" and user.is_active and user.apartment_ref.is_retired:
        return error_response(
            400, "El apartamento de este residente ya no existe: asígnale otro apartamento."
        )
    db.session.commit()
    return jsonify({"message": "Usuario actualizado", "user": user.to_dict()})


@bp.put("/users/<int:user_id>/password")
@bp.put("/admin/users/<int:user_id>/password")
@token_required
@role_required("ADMIN")
def reset_user_password(user_id):
    data, failure = json_body()
    if failure:
        return failure
    validation_error = require_non_empty_fields(data, (("password", "contraseña"),))
    if validation_error:
        return error_response(400, validation_error)
    password_error = validate_strong_password(data["password"])
    if password_error:
        return error_response(400, password_error)

    user = db.session.get(User, user_id)
    if user is None:
        return error_response(404, "Usuario no encontrado")
    user.password_hash = generate_password_hash(data["password"])
    # Con la clave nueva la persona debe poder entrar: se quita el bloqueo por intentos (HU-006).
    register_success(LOGIN, user.email.strip().lower()[:160])
    db.session.commit()
    return jsonify({"message": "Contraseña restablecida"})


@bp.put("/admin/users/<int:user_id>/pin")
@token_required
@role_required("ADMIN")
def set_guard_pin(user_id):
    """Asigna o cambia el PIN de 4 dígitos con el que un guardia toma el turno (HU-010).

    El PIN se guarda con hash y nunca se devuelve. Asignar uno nuevo también
    quita el bloqueo del PIN anterior, igual que restablecer una contraseña.
    """
    data, failure = json_body()
    if failure:
        return failure
    pin_error = validate_pin(data.get("pin"))
    if pin_error:
        return error_response(400, pin_error)

    user = db.session.get(User, user_id)
    if user is None:
        return error_response(404, "Usuario no encontrado")
    if user.role != "GUARD":
        return error_response(400, "Solo los guardias tienen PIN para cambiar de turno.")
    user.pin_hash = generate_password_hash(data["pin"])
    register_success(PIN, str(user.id))
    add_audit_log("user", user.id, "pin_set")
    db.session.commit()
    return jsonify({"message": "PIN asignado", "user": user.to_dict()})


#: Portería ve pocos residentes a la vez y solo después de escribir algo: así en la pantalla del
#: guardia no queda una lista de la unidad a la vista de quien esté en la portería.
GUARD_SEARCH_MIN_CHARS = 2
GUARD_SEARCH_LIMIT = 5
ADMIN_SEARCH_LIMIT = 30


@bp.get("/residents")
@token_required
@role_required("ADMIN", "GUARD")
def get_residents():
    """Busca residentes activos para elegirlos en un formulario.

    Portería solo recibe nombre y apartamento, no busca por correo (SEC-015) y
    no recibe nada hasta escribir 2 letras; ve máximo 5 a la vez. El teléfono lo
    pide aparte, del residente que elige (``/residents/<id>/contact``).
    ``more`` dice si hay más resultados de los que llegaron: hay que escribir más.

    Con ``id`` devuelve solo a ese residente: así una pantalla que llega con el
    residente ya elegido (por ejemplo desde el perfil de su apartamento) lo
    encuentra aunque no esté entre los primeros de la lista.
    """
    is_guard = g.current_user.role == "GUARD"
    query = User.query.filter_by(role="RESIDENT").filter(User.is_active.is_(True))
    resident_id = (request.args.get("id") or "").strip()
    if resident_id:
        if not resident_id.isdigit():
            return error_response(400, "El id del residente debe ser un número.")
        query = query.filter(User.id == int(resident_id))
    search = (request.args.get("search") or "").strip()
    if is_guard and not resident_id and len(search) < GUARD_SEARCH_MIN_CHARS:
        return jsonify({"residents": [], "more": False})
    if search:
        pattern = f"%{search}%"
        fields = [
            (User.name + " " + User.last_name).ilike(pattern),
            User.name.ilike(pattern),
            User.last_name.ilike(pattern),
            User.document_id.ilike(pattern),
            User.apartment.ilike(pattern),
        ]
        if not is_guard:
            fields.append(User.email.ilike(pattern))
        query = query.filter(db.or_(*fields))
    limit = GUARD_SEARCH_LIMIT if is_guard else ADMIN_SEARCH_LIMIT
    residents = query.order_by(User.name, User.last_name, User.id).limit(limit + 1).all()
    summary = User.to_guard_summary if is_guard else User.to_resident_summary
    return jsonify({
        "residents": [summary(resident) for resident in residents[:limit]],
        "more": len(residents) > limit,
    })


@bp.get("/residents/<int:resident_id>/contact")
@token_required
@role_required("ADMIN", "GUARD")
def get_resident_contact(resident_id):
    """El residente que portería eligió en el buscador, con su teléfono.

    Cada vez que un guardia lo pide queda anotado en el registro de auditoría:
    se sabe quién vio el teléfono de quién.
    """
    resident = User.query.filter_by(id=resident_id, role="RESIDENT").filter(User.is_active.is_(True)).first()
    if resident is None:
        return error_response(404, "Residente no encontrado.")
    if g.current_user.role == "GUARD":
        add_audit_log("user", resident.id, "contact_viewed")
        db.session.commit()
    return jsonify({"resident": resident.to_guard_contact()})


@bp.get("/admin/units")
@token_required
@role_required("ADMIN")
def get_unit_profile():
    """Ficha del hogar de un apartamento, por apartmentId o por el texto «Torre 1 · Apto 101»."""
    apartment_id = request.args.get("apartmentId")
    if apartment_id is not None:
        if not apartment_id.isdigit():
            return error_response(400, "El apartamento debe ser un número.")
        apartment = find_apartment(int(apartment_id))
    else:
        label = (request.args.get("apartment") or "").strip()
        if not label:
            return error_response(400, "El apartamento es obligatorio.")
        apartment = apartment_by_text(label)
    if apartment is None or apartment.unit is None:
        return error_response(404, "No se encontró el apartamento.")
    return jsonify({"unit": apartment.unit.to_dict()})


def _item_id_error(item, label, index):
    """Revisa el id opcional de un elemento de la ficha; devuelve el error o None."""
    item_id = item.get("id")
    if item_id is None or (isinstance(item_id, int) and not isinstance(item_id, bool)):
        return None
    return f"El id de {label} #{index + 1} no es válido."


#: Salud de cada mascota (RN-028): nombre, llave del JSON y columna del «al día»
#: y de la fecha de la última aplicación.
PET_HEALTH_FIELDS = (
    ("vacunación", "vaccinesUpToDate", "vaccines_up_to_date",
     "lastVaccinationDate", "last_vaccination_date"),
    ("desparasitación", "dewormingUpToDate", "deworming_up_to_date",
     "lastDewormingDate", "last_deworming_date"),
)


def _pet_health_fields(pet, index):
    """Lee la vacunación y la desparasitación de una mascota (RN-028, HU-021).

    Cada una dice si está al día y la fecha de la última (AAAA-MM-DD, no futura).
    Si está al día, la fecha es obligatoria. Devuelve (campos, error).
    """
    fields = {}
    for label, flag_key, flag_column, date_key, date_column in PET_HEALTH_FIELDS:
        up_to_date = pet.get(flag_key, False)
        if not isinstance(up_to_date, bool):
            return None, f"Mascota #{index + 1}: indica si la {label} está al día (sí o no)."
        last_date = pet.get(date_key)
        if last_date is not None:
            if validate_iso_date(last_date) or last_date > colombia_today().isoformat():
                return None, f"Mascota #{index + 1}: la fecha de la última {label} no es válida."
        elif up_to_date:
            return None, f"Mascota #{index + 1}: escribe la fecha de la última {label}."
        fields[flag_column] = up_to_date
        fields[date_column] = last_date
    return fields, None


def _natural_key(source, names):
    """Lo que identifica un registro que llega sin id: documento, placa o nombre y especie."""
    def value(name):
        raw = source[name] if isinstance(source, dict) else getattr(source, name)
        return str(raw).strip().lower()
    return tuple(value(name) for name in names)


def _sync_household_items(model, unit, current, incoming, natural_key=()):
    """Aplica una lista de la ficha del hogar sin borrar nada (TT-032, DEC-090).

    current son los registros vigentes del apartamento e incoming la lista que
    envió la app. Lo que llega con el id de un registro vigente (o sin id, pero
    con el mismo documento o la misma placa) se mantiene y se actualiza; lo
    nuevo se agrega; y lo vigente que ya no llega se retira con la fecha y
    quién lo hizo. Devuelve cuántos se agregaron, se mantuvieron y se retiraron.
    """
    pending = {item.id: item for item in current}
    by_key = {_natural_key(item, natural_key): item for item in current} if natural_key else {}
    kept, added = [], []
    for fields in incoming:
        fields = dict(fields)
        item = pending.pop(fields.pop("id", None), None)
        if item is None and natural_key:
            match = by_key.get(_natural_key(fields, natural_key))
            if match is not None and match.id in pending:
                item = pending.pop(match.id)
        if item is None:
            added.append(fields)
        else:
            kept.append((item, fields))

    # Primero se retira lo que salió de la lista: así una placa que pasa a otro
    # registro no choca con el registro que se va.
    for item in pending.values():
        item.retire(g.current_user)
    db.session.flush()
    for item, fields in kept:
        for name, value in fields.items():
            setattr(item, name, value)
    for fields in added:
        db.session.add(model(unit=unit, **fields))
    return {"added": len(added), "kept": len(kept), "retired": len(pending)}


@bp.put("/admin/units")
@token_required
@role_required("ADMIN")
def update_unit_profile():
    """Guarda la ficha del hogar de un apartamento (API-HOG-02).

    Nada se borra: lo que se quita de la ficha queda retirado (TT-032) y el
    cambio se anota en el registro de auditoría.
    """
    data, failure = json_body()
    if failure:
        return failure
    apartment = apartment_from_payload(data)
    if apartment is None:
        return error_response(400, "El apartamento es obligatorio.")
    for key in ("members", "pets", "vehicles"):
        if not isinstance(data.get(key), list):
            return error_response(400, f"El campo '{key}' debe ser una lista.")
    if "petInsurance" in data and not isinstance(data["petInsurance"], bool):
        return error_response(400, "El campo 'petInsurance' debe ser verdadero o falso.")
    if data.get("petInsurer") is not None and not isinstance(data["petInsurer"], str):
        return error_response(400, "El campo 'petInsurer' debe ser texto.")

    parsed_members = []
    for index, member in enumerate(data["members"]):
        if not isinstance(member, dict):
            return error_response(400, f"El miembro #{index + 1} no es válido.")
        required = require_non_empty_fields(
            member,
            (("name", "nombre"), ("documentId", "documento"), ("birthDate", "fecha de nacimiento"),
             ("relationship", "parentesco")),
        )
        if required:
            return error_response(400, f"Miembro #{index + 1}: {required}")
        if error := _item_id_error(member, "el miembro", index):
            return error_response(400, error)
        try:
            birth_date = date.fromisoformat(member["birthDate"])
        except ValueError:
            return error_response(400, f"La fecha de nacimiento del miembro #{index + 1} no es válida.")
        if birth_date.isoformat() != member["birthDate"] or birth_date > colombia_today():
            return error_response(400, f"La fecha de nacimiento del miembro #{index + 1} no es válida.")
        relationship = member["relationship"]
        if relationship not in HOUSEHOLD_RELATIONSHIPS:
            return error_response(400, f"El parentesco del miembro #{index + 1} no es válido.")
        other_relationship = member.get("otherRelationship")
        if relationship == "otro" and (
            not isinstance(other_relationship, str) or not other_relationship.strip()
        ):
            return error_response(400, "Especifica el parentesco cuando se selecciona 'otro'.")
        for field in ("lastName", "phone"):
            if member.get(field) is not None and not isinstance(member[field], str):
                return error_response(400, f"El campo '{field}' del miembro debe ser texto.")
        member_phone, phone_error = normalize_phone(member.get("phone"), f"El teléfono del miembro #{index + 1}")
        if phone_error:
            return error_response(400, phone_error)
        parsed_members.append({
            "id": member.get("id"),
            "name": member["name"].strip(),
            "last_name": (member.get("lastName") or "").strip(),
            "document_id": member["documentId"].strip(),
            "birth_date": birth_date.isoformat(),
            "phone": member_phone or None,
            "relationship": relationship,
            "other_relationship": (other_relationship or "").strip() or None,
        })

    parsed_pets = []
    for index, pet in enumerate(data["pets"]):
        if not isinstance(pet, dict):
            return error_response(400, f"La mascota #{index + 1} no es válida.")
        required = require_non_empty_fields(
            pet, (("name", "nombre"), ("species", "especie"), ("breed", "raza"))
        )
        if required:
            return error_response(400, f"Mascota #{index + 1}: {required}")
        if error := _item_id_error(pet, "la mascota", index):
            return error_response(400, error)
        age = pet.get("ageYears")
        if not isinstance(age, int) or isinstance(age, bool) or not 0 <= age <= 100:
            return error_response(400, f"La edad de la mascota #{index + 1} debe estar entre 0 y 100.")
        health, error = _pet_health_fields(pet, index)
        if error:
            return error_response(400, error)
        parsed_pets.append({
            "id": pet.get("id"),
            "name": pet["name"].strip(),
            "species": pet["species"].strip(),
            "breed": pet["breed"].strip(),
            "age_years": age,
            **health,
        })

    parsed_vehicles = []
    seen_plates = set()
    for index, vehicle in enumerate(data["vehicles"]):
        if not isinstance(vehicle, dict):
            return error_response(400, f"El vehículo #{index + 1} no es válido.")
        required = require_non_empty_fields(
            vehicle,
            (("plate", "placa"), ("type", "tipo"), ("makeModel", "marca y modelo"),
             ("registeredOwner", "titular registrado")),
        )
        if required:
            return error_response(400, f"Vehículo #{index + 1}: {required}")
        if error := _item_id_error(vehicle, "el vehículo", index):
            return error_response(400, error)
        plate = vehicle["plate"].replace("-", "").replace(" ", "").upper()
        if error := validate_colombian_plate(plate):
            return error_response(400, error)
        if plate in seen_plates:
            return error_response(409, f"La placa {plate} está repetida en esta unidad.")
        seen_plates.add(plate)
        if vehicle["type"] not in ("carro", "moto"):
            return error_response(400, f"El tipo del vehículo #{index + 1} debe ser carro o moto.")
        year = vehicle.get("year")
        if not isinstance(year, int) or isinstance(year, bool) or not 1950 <= year <= colombia_today().year + 1:
            return error_response(400, f"El año del vehículo #{index + 1} no es válido.")
        for field in ("color",):
            if vehicle.get(field) is not None and not isinstance(vehicle[field], str):
                return error_response(400, f"El campo '{field}' del vehículo debe ser texto.")
        parsed_vehicles.append({
            "id": vehicle.get("id"),
            "plate": plate,
            "vehicle_type": vehicle["type"],
            "make_model": vehicle["makeModel"].strip(),
            "year": year,
            "registered_owner": vehicle["registeredOwner"].strip(),
            "color": (vehicle.get("color") or "").strip() or None,
        })

    unit = ensure_unit(apartment)
    db.session.flush()
    # Solo chocan las placas vigentes de otro apartamento; las retiradas pueden volver.
    conflicts = Vehicle.query.filter(
        Vehicle.plate.in_(seen_plates),
        Vehicle.unit_id != unit.id,
        Vehicle.retired_at.is_(None),
    ).all() if seen_plates else []
    if conflicts:
        return jsonify({
            "error": "Una o más placas ya están registradas en otra unidad.",
            "status": 409,
            "plates": [vehicle.plate for vehicle in conflicts],
        }), 409

    # El parqueadero y el cuarto útil ya no se escriben aquí: se asignan al apartamento
    # en la estructura de la unidad (HU-015 y HU-016), y los que lleguen se ignoran.
    unit.pet_insurance = data.get("petInsurance", False)
    unit.pet_insurer = (data.get("petInsurer") or "").strip() or None if unit.pet_insurance else None
    changes = {
        "members": _sync_household_items(
            HouseholdMember, unit, unit.active_members, parsed_members, ("document_id",)
        ),
        "pets": _sync_household_items(
            Pet, unit, unit.active_pets, parsed_pets, ("name", "species")
        ),
        "vehicles": _sync_household_items(
            Vehicle, unit, unit.active_vehicles, parsed_vehicles, ("plate",)
        ),
    }
    add_audit_log("residential_unit", unit.id, "household_updated", {
        "apartment": unit.apartment, **changes,
    })
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response(409, "No se pudo guardar: una placa ya está registrada en otra unidad.")
    return jsonify({"message": "Ficha del apartamento actualizada", "unit": unit.to_dict()})


@bp.get("/profile")
@token_required
@role_required("RESIDENT")
def get_resident_profile():
    return jsonify({"user": g.current_user.to_dict()})


@bp.get("/profile/unit")
@token_required
@role_required("RESIDENT")
def get_resident_unit_profile():
    user = g.current_user
    if user.apartment_ref is None:
        return error_response(404, "Tu cuenta no tiene un apartamento asociado.")
    unit = user.apartment_ref.unit
    if unit is None:
        return error_response(404, "No se encontró la ficha de tu apartamento.")
    return jsonify({"unit": unit.to_dict()})


@bp.put("/profile")
@token_required
@role_required("RESIDENT")
def update_resident_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    allowed_fields = {"phone", "email", "socialNetworks"}
    unexpected_fields = set(data) - allowed_fields
    if unexpected_fields:
        return error_response(
            400,
            "Solo puedes editar teléfono, correo y redes sociales. "
            f"Campos no permitidos: {', '.join(sorted(unexpected_fields))}.",
        )
    if not data:
        return error_response(400, "Indica al menos un dato permitido para actualizar.")
    user = g.current_user
    if "phone" in data:
        phone, phone_error = normalize_phone(data["phone"])
        if phone_error:
            return error_response(400, phone_error)
        user.phone = phone
    if "socialNetworks" in data:
        if not isinstance(data["socialNetworks"], str) or len(data["socialNetworks"]) > 500:
            return error_response(400, "Las redes sociales deben ser texto de máximo 500 caracteres.")
        user.social_networks = data["socialNetworks"].strip()
    if "email" in data:
        if not isinstance(data["email"], str) or "@" not in data["email"] or len(data["email"]) > 160:
            return error_response(400, "Correo inválido.")
        email = data["email"].strip().lower()
        duplicate = User.query.filter(
            db.func.lower(User.email) == email,
            User.id != user.id,
        ).first()
        if duplicate:
            return error_response(409, "Ese correo ya está registrado.")
        user.email = email
    db.session.commit()
    return jsonify({"message": "Perfil actualizado", "user": user.to_dict()})
