"""Rutas de la estructura de la unidad (API-EST-01 a API-EST-05).

Torres, apartamentos, parqueaderos y cuartos útiles los administra solo el
administrador (ADR-015). Las reglas están en services/structure_service.py; aquí
se lee la solicitud, se llama al servicio y se guarda. Quitar algo no lo borra:
queda retirado (ADR-013).
"""

from flask import Blueprint, g, jsonify, request

from auth import role_required, token_required
from errors import ApiError
from extensions import db
from models import Apartment, ParkingSpot, StorageRoom, Tower
from routes.common import bool_arg, json_object, paginated, save_changes
from services import structure_service as structure

bp = Blueprint("structure", __name__, url_prefix="/api/admin")

NOT_FOUND = {
    Tower: "La torre no existe o ya fue retirada.",
    Apartment: "El apartamento no existe o ya fue retirado.",
    ParkingSpot: "El parqueadero no existe o ya fue retirado.",
    StorageRoom: "El cuarto útil no existe o ya fue retirado.",
}


def _active(model, item_id):
    """El registro vigente con ese id; si no existe o está retirado, error 404."""
    item = db.session.get(model, item_id)
    if item is None or item.is_retired:
        raise ApiError(NOT_FOUND[model], 404)
    return item


# --- Torres (HU-013) --------------------------------------------------------

@bp.get("/towers")
@token_required
@role_required("ADMIN")
def list_towers():
    return jsonify({"towers": [tower.to_dict() for tower in structure.active_towers()]})


@bp.get("/towers/<int:tower_id>")
@token_required
@role_required("ADMIN")
def get_tower(tower_id):
    return jsonify({"tower": _active(Tower, tower_id).to_dict()})


@bp.post("/towers")
@token_required
@role_required("ADMIN")
def create_tower():
    tower = structure.create_tower(json_object(), g.current_user)
    save_changes("Ya existe una torre con ese nombre.")
    return jsonify({"message": "Torre creada", "tower": tower.to_dict()}), 201


@bp.put("/towers/<int:tower_id>")
@token_required
@role_required("ADMIN")
def update_tower(tower_id):
    tower = structure.update_tower(_active(Tower, tower_id), json_object(required=True), g.current_user)
    save_changes("Ya existe una torre con ese nombre.")
    return jsonify({"message": "Torre actualizada", "tower": tower.to_dict()})


@bp.delete("/towers/<int:tower_id>")
@token_required
@role_required("ADMIN")
def retire_tower(tower_id):
    tower = structure.retire_tower(_active(Tower, tower_id), g.current_user)
    db.session.commit()
    return jsonify({"message": "Torre retirada", "tower": tower.to_dict()})


# --- Apartamentos (HU-014 y HU-023) -------------------------------------------

@bp.get("/apartments")
@token_required
@role_required("ADMIN")
def list_apartments():
    tower_id = request.args.get("towerId")
    if tower_id is not None and not tower_id.isdigit():
        raise ApiError("El filtro 'towerId' debe ser un número entero.")
    query = structure.apartments_query(
        tower_id=int(tower_id) if tower_id else None,
        search=(request.args.get("search") or "").strip(),
    )
    return paginated(query, "apartments", default_size=50)


@bp.get("/apartments/<int:apartment_id>")
@token_required
@role_required("ADMIN")
def get_apartment(apartment_id):
    return jsonify({"apartment": _active(Apartment, apartment_id).to_dict()})


@bp.post("/apartments")
@token_required
@role_required("ADMIN")
def create_apartment():
    apartment = structure.create_apartment(json_object(), g.current_user)
    save_changes("Ese apartamento ya existe en la torre.")
    return jsonify({"message": "Apartamento creado", "apartment": apartment.to_dict()}), 201


@bp.post("/apartments/batch")
@token_required
@role_required("ADMIN")
def create_floor_apartments():
    apartments = structure.create_floor(json_object(), g.current_user)
    save_changes("Uno de los apartamentos ya existe en la torre.")
    first = apartments[0]
    return jsonify({
        "message": (
            f"Se crearon {len(apartments)} apartamento{'s' if len(apartments) != 1 else ''} "
            f"en el piso {first.floor} de {first.tower.name}."
        ),
        "apartments": [apartment.to_dict() for apartment in apartments],
    }), 201


@bp.put("/apartments/<int:apartment_id>")
@token_required
@role_required("ADMIN")
def update_apartment(apartment_id):
    apartment = structure.update_apartment(
        _active(Apartment, apartment_id), json_object(required=True), g.current_user
    )
    save_changes("Ese apartamento ya existe en la torre.")
    return jsonify({"message": "Apartamento actualizado", "apartment": apartment.to_dict()})


@bp.delete("/apartments/<int:apartment_id>")
@token_required
@role_required("ADMIN")
def retire_apartment(apartment_id):
    apartment = structure.retire_apartment(_active(Apartment, apartment_id), g.current_user)
    db.session.commit()
    return jsonify({"message": "Apartamento retirado", "apartment": apartment.to_dict()})


# --- Parqueaderos (HU-015) ----------------------------------------------------

@bp.get("/parking-spots")
@token_required
@role_required("ADMIN")
def list_parking_spots():
    kind = request.args.get("type")
    if kind is not None and kind not in structure.PARKING_KINDS:
        raise ApiError("El filtro 'type' debe ser 'residente' o 'visitante'.")
    query = structure.parking_query(
        kind=kind,
        assigned=bool_arg("assigned"),
        occupied=bool_arg("occupied"),
        search=(request.args.get("search") or "").strip(),
    )
    return paginated(query, "parkingSpots", default_size=50)


@bp.get("/parking-spots/<int:spot_id>")
@token_required
@role_required("ADMIN")
def get_parking_spot(spot_id):
    return jsonify({"parkingSpot": _active(ParkingSpot, spot_id).to_dict()})


@bp.post("/parking-spots")
@token_required
@role_required("ADMIN")
def create_parking_spot():
    spot = structure.create_parking(json_object(), g.current_user)
    save_changes("Ya existe un parqueadero con ese código.")
    return jsonify({"message": "Parqueadero creado", "parkingSpot": spot.to_dict()}), 201


@bp.put("/parking-spots/<int:spot_id>")
@token_required
@role_required("ADMIN")
def update_parking_spot(spot_id):
    spot = structure.update_parking(_active(ParkingSpot, spot_id), json_object(required=True), g.current_user)
    save_changes("Ya existe un parqueadero con ese código.")
    return jsonify({"message": "Parqueadero actualizado", "parkingSpot": spot.to_dict()})


@bp.delete("/parking-spots/<int:spot_id>")
@token_required
@role_required("ADMIN")
def retire_parking_spot(spot_id):
    spot = structure.retire_parking(_active(ParkingSpot, spot_id), g.current_user)
    db.session.commit()
    return jsonify({"message": "Parqueadero retirado", "parkingSpot": spot.to_dict()})


# --- Cuartos útiles (HU-016) --------------------------------------------------

@bp.get("/storage-rooms")
@token_required
@role_required("ADMIN")
def list_storage_rooms():
    query = structure.storage_rooms_query(
        assigned=bool_arg("assigned"),
        search=(request.args.get("search") or "").strip(),
    )
    return paginated(query, "storageRooms", default_size=50)


@bp.get("/storage-rooms/<int:room_id>")
@token_required
@role_required("ADMIN")
def get_storage_room(room_id):
    return jsonify({"storageRoom": _active(StorageRoom, room_id).to_dict()})


@bp.post("/storage-rooms")
@token_required
@role_required("ADMIN")
def create_storage_room():
    room = structure.create_storage_room(json_object(), g.current_user)
    save_changes("Ya existe un cuarto útil con ese código.")
    return jsonify({"message": "Cuarto útil creado", "storageRoom": room.to_dict()}), 201


@bp.put("/storage-rooms/<int:room_id>")
@token_required
@role_required("ADMIN")
def update_storage_room(room_id):
    room = structure.update_storage_room(_active(StorageRoom, room_id), json_object(required=True), g.current_user)
    save_changes("Ya existe un cuarto útil con ese código.")
    return jsonify({"message": "Cuarto útil actualizado", "storageRoom": room.to_dict()})


@bp.delete("/storage-rooms/<int:room_id>")
@token_required
@role_required("ADMIN")
def retire_storage_room(room_id):
    room = structure.retire_storage_room(_active(StorageRoom, room_id), g.current_user)
    db.session.commit()
    return jsonify({"message": "Cuarto útil retirado", "storageRoom": room.to_dict()})
