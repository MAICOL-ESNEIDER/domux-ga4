import base64
import binascii
from datetime import datetime

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from auth import close_sessions, role_required, token_required
from errors import ApiError, error_response
from extensions import db
from models import (
    DevicePushToken,
    HouseholdMember,
    Pet,
    ROLES,
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
from services.household_service import parse_members, parse_pets, parse_vehicles, sync_items
from services.structure_service import (
    apartment_by_text,
    apartment_from_payload,
    ensure_unit,
    find_apartment,
)
from services.summary_service import admin_summary
from services.user_search import filtered_users, normalize_role
from validators import (
    OCCUPANCY_TYPES,
    normalize_phone,
    require_non_empty_fields,
    validate_occupancy_type,
    validate_pin,
    validate_strong_password,
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
    # El censo deja a cada residente con la autorización de tratamiento de datos: quien lo sube
    # confirma que la unidad la tiene (Ley 1581 de 2012).
    if data.get("dataProcessingConsent") is not True:
        return error_response(
            400,
            "Confirma que la unidad tiene la autorización de tratamiento de datos de cada residente del archivo.",
        )
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
    query = filtered_users(request.args)
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


def _checked_birth_date(value):
    """Una fecha de nacimiento AAAA-MM-DD que no sea futura."""
    if error := validate_iso_date(value):
        raise ApiError(error)
    if datetime.strptime(value, "%Y-%m-%d").date() > colombia_today():
        raise ApiError("La fecha de nacimiento no puede ser futura.")
    return value


def _new_account_identity(data):
    """El correo, el rol y el apartamento de una cuenta nueva, ya revisados."""
    email = data["email"].strip().lower()
    role = normalize_role(data.get("role"))
    if "@" not in email or role not in ROLES:
        raise ApiError("Correo o rol inválido")
    if password_error := validate_strong_password(data["password"]):
        raise ApiError(password_error)
    if role != "RESIDENT":
        return email, role, None
    # El residente se vincula a un apartamento que existe en la estructura (HU-017).
    apartment = apartment_from_payload(data)
    if apartment is None:
        raise ApiError("El residente necesita un apartamento")
    if "occupancyType" not in data:
        raise ApiError(OCCUPANCY_REQUIRED_MESSAGE)
    if data.get("dataProcessingConsent") is not True:
        raise ApiError("Debes registrar la autorización de tratamiento de datos del residente.")
    return email, role, apartment


def _new_account_profile(data):
    """Los datos personales opcionales de una cuenta nueva, ya revisados."""
    if "birthDate" in data:
        _checked_birth_date(data["birthDate"])
    parental_consent = data.get("parentalConsent", False)
    if not isinstance(parental_consent, bool):
        raise ApiError("parentalConsent debe ser verdadero o falso.")
    occupancy_type = data.get("occupancyType", "propietario")
    if not isinstance(occupancy_type, str) or occupancy_type not in OCCUPANCY_TYPES:
        raise ApiError(validate_occupancy_type(occupancy_type))
    for field in ("lastName", "phone", "documentId"):
        if field in data and not isinstance(data[field], str):
            raise ApiError(f"El campo '{field}' debe ser texto")
    phone, phone_error = normalize_phone(data.get("phone"))
    if phone_error:
        raise ApiError(phone_error)
    return {"occupancy_type": occupancy_type, "phone": phone, "parental_consent": parental_consent}


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

    email, role, apartment = _new_account_identity(data)
    profile = _new_account_profile(data)
    if User.query.filter(db.func.lower(User.email) == email).first():
        return error_response(409, "Ese correo ya está registrado")

    user = User(
        name=data["name"].strip(),
        last_name=data.get("lastName", "").strip(),
        email=email,
        phone=profile["phone"],
        document_id=data.get("documentId", "").strip(),
        password_hash=generate_password_hash(data["password"]),
        role=role,
        apartment_ref=apartment,
        occupancy_type=profile["occupancy_type"],
        social_networks="",
        birth_date=data.get("birthDate"),
        parental_consent=profile["parental_consent"],
        data_processing_consent=role == "RESIDENT",
        data_processing_consent_at=utc_now() if role == "RESIDENT" else None,
        is_active=True,
        # La contraseña la escribió el administrador: es temporal y la persona pone una propia al entrar.
        must_change_password=True,
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


def _refuse_own_lockout(user, data):
    """Quien administra no se cierra la puerta a sí mismo.

    Si el único administrador se desactivara o se cambiara el rol, nadie podría volver a entrar
    para arreglarlo.
    """
    if user.id != g.current_user.id:
        return
    if data.get("isActive") is False:
        raise ApiError("No puedes desactivar tu propia cuenta. Pídele a otro administrador que lo haga.", 409)
    if "role" in data and normalize_role(data["role"]) != user.role:
        raise ApiError("No puedes cambiar tu propio rol. Pídele a otro administrador que lo haga.", 409)


def _require_text(data, key, message):
    if not isinstance(data[key], str):
        raise ApiError(message)
    return data[key].strip()


def _checked_new_email(user, value):
    """Un correo válido que no sea de otra cuenta."""
    if not isinstance(value, str) or "@" not in value:
        raise ApiError("Correo inválido")
    email = value.strip().lower()
    if User.query.filter(db.func.lower(User.email) == email, User.id != user.id).first():
        raise ApiError("Ese correo ya está registrado", 409)
    return email


def _update_personal_data(user, data):
    """Fecha de nacimiento, consentimiento de padres, nombre, apellido, correo, teléfono y documento."""
    if "birthDate" in data:
        user.birth_date = _checked_birth_date(data["birthDate"])
    if "parentalConsent" in data:
        if not isinstance(data["parentalConsent"], bool):
            raise ApiError("parentalConsent debe ser verdadero o falso.")
        user.parental_consent = data["parentalConsent"]
    if "name" in data:
        user.name = _require_text(data, "name", "El nombre debe ser texto")
    if "lastName" in data:
        user.last_name = _require_text(data, "lastName", "El apellido debe ser texto")
    if "email" in data:
        user.email = _checked_new_email(user, data["email"])
    if "phone" in data:
        phone, phone_error = normalize_phone(data["phone"])
        if phone_error:
            raise ApiError(phone_error)
        user.phone = phone
    if "documentId" in data:
        user.document_id = _require_text(data, "documentId", "El documento debe ser texto")


def _update_role(user, data):
    """El rol. Quien pasa a ser residente necesita su ocupación y la autorización de datos (RN-007)."""
    if "role" in data:
        role = normalize_role(data["role"])
        if role not in ROLES:
            raise ApiError("Rol inválido")
        if role == "RESIDENT" and user.role != "RESIDENT":
            if "occupancyType" not in data:
                raise ApiError(OCCUPANCY_REQUIRED_MESSAGE)
            if data.get("dataProcessingConsent") is not True:
                raise ApiError("Debes registrar la autorización de tratamiento de datos del residente.")
            user.data_processing_consent = True
            user.data_processing_consent_at = utc_now()
        user.role = role
    if user.role != "GUARD":
        # El PIN de turno es solo de los guardias: quien deja de serlo lo pierde (RN-029).
        user.pin_hash = None


def _update_occupancy_and_apartment(user, data):
    """El tipo de ocupación y el apartamento; solo los residentes tienen apartamento."""
    if "occupancyType" in data:
        if error := validate_occupancy_type(data["occupancyType"]):
            raise ApiError(error)
        user.occupancy_type = data["occupancyType"]
    if "apartment" in data or "apartmentId" in data:
        # Un valor nulo desvincula al usuario; uno que no existe en la estructura se rechaza.
        user.apartment_ref = apartment_from_payload(data)
    if user.role == "RESIDENT" and user.apartment_ref is None:
        raise ApiError("El residente necesita un apartamento")
    if user.role != "RESIDENT":
        user.apartment_ref = None
    else:
        ensure_unit(user.apartment_ref)


def _update_active_flag(user, data):
    """Activar o desactivar la cuenta; al desactivar se cierra lo que aún podría usar (TT-027)."""
    if "isActive" not in data:
        return
    if not isinstance(data["isActive"], bool):
        raise ApiError("isActive debe ser verdadero o falso")
    was_active = user.is_active
    user.is_active = data["isActive"]
    if was_active and not user.is_active:
        add_audit_log("user", user.id, "deactivated", _close_access_of_deactivated_user(user))
    elif not was_active and user.is_active:
        add_audit_log("user", user.id, "reactivated")


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

    _refuse_own_lockout(user, data)
    _update_personal_data(user, data)
    _update_role(user, data)
    _update_occupancy_and_apartment(user, data)
    _update_active_flag(user, data)
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
    # Las sesiones abiertas con la clave anterior se cierran.
    close_sessions(user)
    # Esta contraseña la conoce el administrador: la persona debe poner una propia al entrar.
    user.must_change_password = user.id != g.current_user.id
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

    members = parse_members(data["members"])
    pets = parse_pets(data["pets"])
    vehicles = parse_vehicles(data["vehicles"])

    unit = ensure_unit(apartment)
    db.session.flush()
    # Solo chocan las placas vigentes de otro apartamento; las retiradas pueden volver.
    plates = {vehicle["plate"] for vehicle in vehicles}
    conflicts = Vehicle.query.filter(
        Vehicle.plate.in_(plates),
        Vehicle.unit_id != unit.id,
        Vehicle.retired_at.is_(None),
    ).all() if plates else []
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
    actor = g.current_user
    changes = {
        "members": sync_items(HouseholdMember, unit, unit.active_members, members, actor, ("document_id",)),
        "pets": sync_items(Pet, unit, unit.active_pets, pets, actor, ("name", "species")),
        "vehicles": sync_items(Vehicle, unit, unit.active_vehicles, vehicles, actor, ("plate",)),
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
