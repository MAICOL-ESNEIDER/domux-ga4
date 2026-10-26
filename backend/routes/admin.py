from datetime import date, datetime

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from auth import role_required, token_required
from errors import error_response
from extensions import db
from models import (
    HouseholdMember,
    Pet,
    ResidentialUnit,
    ROLES,
    User,
    Vehicle,
)
from validators import (
    HOUSEHOLD_RELATIONSHIPS,
    OCCUPANCY_TYPES,
    apartment_number_from_label,
    parse_optional_bool,
    require_non_empty_fields,
    validate_no_empty_strings,
    validate_occupancy_type,
    validate_strong_password,
    validate_colombian_plate,
)

bp = Blueprint("admin", __name__, url_prefix="/api")


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response(400, "El cuerpo de la solicitud debe ser un objeto JSON válido.")
    message = validate_no_empty_strings(data)
    if message:
        return None, error_response(400, message)
    return data, None


def _normalize_role(value):
    return value.strip().upper() if isinstance(value, str) else None


@bp.get("/users")
@bp.get("/admin/users")
@token_required
@role_required("ADMIN")
def get_users():
    page = request.args.get("page", default=1, type=int)
    page_size = request.args.get("pageSize", default=25, type=int)
    if page is None or page < 1 or page_size is None or not 1 <= page_size <= 100:
        return error_response(400, "La página debe ser positiva y pageSize debe estar entre 1 y 100.")

    query = User.query
    search = (request.args.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        member_match = db.session.query(HouseholdMember.id).join(
            ResidentialUnit, HouseholdMember.unit_id == ResidentialUnit.id
        ).filter(
            ResidentialUnit.apartment == User.apartment,
            db.or_(
                HouseholdMember.name.ilike(pattern),
                HouseholdMember.last_name.ilike(pattern),
                HouseholdMember.document_id.ilike(pattern),
            ),
        ).exists()
        query = query.filter(db.or_(
            User.name.ilike(pattern),
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
        ).filter(ResidentialUnit.apartment == User.apartment).exists()),
        ("hasVehicles", db.session.query(Vehicle.id).join(
            ResidentialUnit, Vehicle.unit_id == ResidentialUnit.id
        ).filter(ResidentialUnit.apartment == User.apartment).exists()),
        ("hasParking", db.session.query(ResidentialUnit.id).filter(
            ResidentialUnit.apartment == User.apartment,
            ResidentialUnit.parking_identifier.isnot(None),
            ResidentialUnit.parking_identifier != "",
        ).exists()),
        ("hasStorage", db.session.query(ResidentialUnit.id).filter(
            ResidentialUnit.apartment == User.apartment,
            ResidentialUnit.storage_identifier.isnot(None),
            ResidentialUnit.storage_identifier != "",
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
        today = date.today()

        def years_before(years):
            try:
                return today.replace(year=today.year - years)
            except ValueError:
                return today.replace(year=today.year - years, day=28)

        birth_date_conditions = []
        if minimum_age is not None:
            latest_birth_date = years_before(minimum_age)
            birth_date_conditions.append(HouseholdMember.birth_date <= latest_birth_date.isoformat())
        if maximum_age is not None:
            earliest_birth_date = years_before(maximum_age + 1)
            birth_date_conditions.append(HouseholdMember.birth_date > earliest_birth_date.isoformat())
        age_match = db.session.query(HouseholdMember.id).join(
            ResidentialUnit, HouseholdMember.unit_id == ResidentialUnit.id
        ).filter(
            ResidentialUnit.apartment == User.apartment,
            *birth_date_conditions,
        ).exists()
        query = query.filter(age_match, User.role == "RESIDENT")

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


@bp.post("/users")
@bp.post("/admin/users")
@token_required
@role_required("ADMIN")
def create_user():
    data, failure = _json_body()
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
    apartment = data.get("apartment")
    occupancy_type = data.get("occupancyType", "propietario")
    if "@" not in email or role not in ROLES:
        return error_response(400, "Correo o rol inválido")
    password_error = validate_strong_password(data["password"])
    if password_error:
        return error_response(400, password_error)
    if role == "RESIDENT" and (
        not isinstance(apartment, str) or not apartment.strip()
    ):
        return error_response(400, "El residente necesita un apartamento")
    if role == "RESIDENT" and data.get("dataProcessingConsent") is not True:
        return error_response(400, "Debes registrar la autorización de tratamiento de datos del residente.")
    if not isinstance(occupancy_type, str) or occupancy_type not in OCCUPANCY_TYPES:
        return error_response(400, validate_occupancy_type(occupancy_type))
    for field in ("lastName", "phone", "documentId"):
        if field in data and not isinstance(data[field], str):
            return error_response(400, f"El campo '{field}' debe ser texto")
    if User.query.filter(db.func.lower(User.email) == email).first():
        return error_response(409, "Ese correo ya está registrado")

    user = User(
        name=data["name"].strip(),
        last_name=data.get("lastName", "").strip(),
        email=email,
        phone=data.get("phone", "").strip(),
        document_id=data.get("documentId", "").strip(),
        password_hash=generate_password_hash(data["password"]),
        role=role,
        apartment=apartment.strip() if role == "RESIDENT" else None,
        apartment_number=apartment_number_from_label(apartment) if role == "RESIDENT" else None,
        occupancy_type=occupancy_type,
        social_networks="",
        data_processing_consent=role == "RESIDENT",
        data_processing_consent_at=datetime.utcnow() if role == "RESIDENT" else None,
        is_active=True,
    )
    db.session.add(user)
    if role == "RESIDENT":
        unit = ResidentialUnit.query.filter_by(apartment=user.apartment).first()
        if unit is None:
            db.session.add(ResidentialUnit(apartment=user.apartment))
    db.session.commit()
    return jsonify({"message": "Usuario creado", "user": user.to_dict()}), 201


@bp.put("/users/<int:user_id>")
@bp.put("/admin/users/<int:user_id>")
@token_required
@role_required("ADMIN")
def update_user(user_id):
    data, failure = _json_body()
    if failure:
        return failure
    if not data:
        return error_response(400, "Debes proporcionar al menos un dato para actualizar")
    if "password" in data or "passwordHash" in data or "password_hash" in data:
        return error_response(400, "Usa PUT /users/<id>/password para cambiar la contraseña")

    user = db.session.get(User, user_id)
    if user is None:
        return error_response(404, "Usuario no encontrado")

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
    for field, attribute, label in (
        ("phone", "phone", "teléfono"),
        ("documentId", "document_id", "documento"),
    ):
        if field in data:
            if not isinstance(data[field], str):
                return error_response(400, f"El {label} debe ser texto")
            setattr(user, attribute, data[field].strip())

    if "role" in data:
        role = _normalize_role(data["role"])
        if role not in ROLES:
            return error_response(400, "Rol inválido")
        if role == "RESIDENT" and user.role != "RESIDENT":
            if data.get("dataProcessingConsent") is not True:
                return error_response(
                    400,
                    "Debes registrar la autorización de tratamiento de datos del residente.",
                )
            user.data_processing_consent = True
            user.data_processing_consent_at = datetime.utcnow()
        user.role = role
    if "occupancyType" in data:
        error = validate_occupancy_type(data["occupancyType"])
        if error:
            return error_response(400, error)
        user.occupancy_type = data["occupancyType"]
    if "apartment" in data:
        apartment = data["apartment"]
        if apartment is not None and not isinstance(apartment, str):
            return error_response(400, "El apartamento debe ser texto")
        user.apartment = apartment.strip() if apartment else None
        user.apartment_number = apartment_number_from_label(user.apartment)
    if user.role == "RESIDENT" and not user.apartment:
        return error_response(400, "El residente necesita un apartamento")
    if user.role != "RESIDENT":
        user.apartment = None
        user.apartment_number = None
    else:
        unit = ResidentialUnit.query.filter_by(apartment=user.apartment).first()
        if unit is None:
            db.session.add(ResidentialUnit(apartment=user.apartment))
    if "isActive" in data:
        if not isinstance(data["isActive"], bool):
            return error_response(400, "isActive debe ser verdadero o falso")
        user.is_active = data["isActive"]

    db.session.commit()
    return jsonify({"message": "Usuario actualizado", "user": user.to_dict()})


@bp.put("/users/<int:user_id>/password")
@bp.put("/admin/users/<int:user_id>/password")
@token_required
@role_required("ADMIN")
def reset_user_password(user_id):
    data, failure = _json_body()
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
    db.session.commit()
    return jsonify({"message": "Contraseña restablecida"})


@bp.get("/residents")
@token_required
@role_required("ADMIN", "GUARD")
def get_residents():
    residents = User.query.filter_by(role="RESIDENT").order_by(User.name).all()
    return jsonify({"residents": [resident.to_resident_summary() for resident in residents]})


@bp.get("/admin/units")
@token_required
@role_required("ADMIN")
def get_unit_profile():
    apartment = (request.args.get("apartment") or "").strip()
    if not apartment:
        return error_response(400, "El apartamento es obligatorio.")
    unit = ResidentialUnit.query.filter_by(apartment=apartment).first()
    if unit is None:
        return error_response(404, "No se encontró el apartamento.")
    return jsonify({"unit": unit.to_dict()})


@bp.put("/admin/units")
@token_required
@role_required("ADMIN")
def update_unit_profile():
    data, failure = _json_body()
    if failure:
        return failure
    apartment = data.get("apartment")
    if not isinstance(apartment, str) or not apartment.strip():
        return error_response(400, "El apartamento es obligatorio.")
    for key in ("members", "pets", "vehicles"):
        if not isinstance(data.get(key), list):
            return error_response(400, f"El campo '{key}' debe ser una lista.")
    for key in ("petInsurance", "funeralPlan"):
        if key in data and not isinstance(data[key], bool):
            return error_response(400, f"El campo '{key}' debe ser verdadero o falso.")
    for key in ("parkingIdentifier", "storageIdentifier", "petInsurer", "funeralProvider"):
        if data.get(key) is not None and not isinstance(data[key], str):
            return error_response(400, f"El campo '{key}' debe ser texto.")

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
        try:
            birth_date = date.fromisoformat(member["birthDate"])
        except ValueError:
            return error_response(400, f"La fecha de nacimiento del miembro #{index + 1} no es válida.")
        if birth_date.isoformat() != member["birthDate"] or birth_date > date.today():
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
        parsed_members.append({
            "name": member["name"].strip(),
            "last_name": (member.get("lastName") or "").strip(),
            "document_id": member["documentId"].strip(),
            "birth_date": birth_date.isoformat(),
            "phone": (member.get("phone") or "").strip() or None,
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
        age = pet.get("ageYears")
        if not isinstance(age, int) or isinstance(age, bool) or not 0 <= age <= 100:
            return error_response(400, f"La edad de la mascota #{index + 1} debe estar entre 0 y 100.")
        parsed_pets.append({
            "name": pet["name"].strip(),
            "species": pet["species"].strip(),
            "breed": pet["breed"].strip(),
            "age_years": age,
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
        plate = vehicle["plate"].replace("-", "").replace(" ", "").upper()
        if error := validate_colombian_plate(plate):
            return error_response(400, error)
        if plate in seen_plates:
            return error_response(409, f"La placa {plate} está repetida en esta unidad.")
        seen_plates.add(plate)
        if vehicle["type"] not in ("carro", "moto"):
            return error_response(400, f"El tipo del vehículo #{index + 1} debe ser carro o moto.")
        year = vehicle.get("year")
        if not isinstance(year, int) or isinstance(year, bool) or not 1950 <= year <= date.today().year + 1:
            return error_response(400, f"El año del vehículo #{index + 1} no es válido.")
        for field in ("color",):
            if vehicle.get(field) is not None and not isinstance(vehicle[field], str):
                return error_response(400, f"El campo '{field}' del vehículo debe ser texto.")
        parsed_vehicles.append({
            "plate": plate,
            "vehicle_type": vehicle["type"],
            "make_model": vehicle["makeModel"].strip(),
            "year": year,
            "registered_owner": vehicle["registeredOwner"].strip(),
            "color": (vehicle.get("color") or "").strip() or None,
        })

    unit = ResidentialUnit.query.filter_by(apartment=apartment.strip()).first()
    if unit is None:
        return error_response(404, "No se encontró el apartamento.")
    conflicts = Vehicle.query.filter(
        Vehicle.plate.in_(seen_plates),
        Vehicle.unit_id != unit.id,
    ).all() if seen_plates else []
    if conflicts:
        return jsonify({
            "error": "Una o más placas ya están registradas en otra unidad.",
            "status": 409,
            "plates": [vehicle.plate for vehicle in conflicts],
        }), 409

    unit.parking_identifier = (data.get("parkingIdentifier") or "").strip() or None
    unit.storage_identifier = (data.get("storageIdentifier") or "").strip() or None
    unit.pet_insurance = data.get("petInsurance", False)
    unit.pet_insurer = (data.get("petInsurer") or "").strip() or None if unit.pet_insurance else None
    unit.funeral_plan = data.get("funeralPlan", False)
    unit.funeral_provider = (data.get("funeralProvider") or "").strip() or None if unit.funeral_plan else None
    unit.members.clear()
    unit.pets.clear()
    unit.vehicles.clear()
    db.session.flush()
    unit.members.extend(HouseholdMember(unit=unit, **member) for member in parsed_members)
    unit.pets.extend(Pet(unit=unit, **pet) for pet in parsed_pets)
    unit.vehicles.extend(Vehicle(unit=unit, **vehicle) for vehicle in parsed_vehicles)
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
    if not user.apartment:
        return error_response(404, "Tu cuenta no tiene un apartamento asociado.")
    unit = ResidentialUnit.query.filter_by(apartment=user.apartment).first()
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
        if not isinstance(data["phone"], str) or len(data["phone"]) > 30:
            return error_response(400, "El teléfono debe ser texto.")
        user.phone = data["phone"].strip()
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
