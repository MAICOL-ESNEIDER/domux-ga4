"""Rutas de la portería vehicular (API-VEH-01 a API-VEH-06).

Vehículos de visitantes con su parqueadero (HU-035 a HU-039 y HU-041) y vehículos
de residentes (HU-040). Las reglas están en services/vehicle_service.py; aquí se
lee la solicitud, se llama al servicio y se guarda. Los residentes no ven estas
rutas: es información de la portería y la administración.
"""

from flask import Blueprint, g, jsonify, request

from auth import role_required, token_required
from errors import ApiError
from extensions import db
from models import VisitorVehicleEntry
from routes.common import bool_arg, int_arg, json_object, paginated, save_changes
from services import vehicle_service as vehicles
from services.alert_service import run_alerts

bp = Blueprint("vehicles", __name__, url_prefix="/api")


# --- Parqueaderos de visitantes (HU-037) ------------------------------------

@bp.get("/parking/visitor-spots")
@token_required
@role_required("GUARD", "ADMIN")
def visitor_spots():
    """Los parqueaderos de visitantes libres y ocupados, como están en el servidor."""
    run_alerts()
    return jsonify(vehicles.visitor_board())


# --- Vehículos visitantes (HU-035, HU-036, HU-038, HU-039 y HU-041) ---------

@bp.post("/vehicle-entries")
@token_required
@role_required("GUARD")
def register_vehicle_entry():
    entry = vehicles.register_visitor_entry(json_object(), g.current_user)
    save_changes("No se pudo registrar la entrada del vehículo: inténtalo de nuevo.")
    message = (
        f"Entrada registrada. Parqueadero {entry.spot.code}."
        if entry.spot else "Entrada registrada sin parqueadero."
    )
    return jsonify({"message": message, "vehicleEntry": entry.to_dict()}), 201


@bp.put("/vehicle-entries/<int:entry_id>/exit")
@token_required
@role_required("GUARD")
def register_vehicle_exit(entry_id):
    entry = db.session.get(VisitorVehicleEntry, entry_id)
    if entry is None:
        raise ApiError("La entrada del vehículo no existe.", 404)
    vehicles.register_visitor_exit(entry, g.current_user)
    save_changes()
    message = "Salida registrada."
    if entry.spot:
        message += f" El parqueadero {entry.spot.code} quedó libre."
    return jsonify({"message": message, "vehicleEntry": entry.to_dict()})


@bp.get("/vehicle-entries")
@token_required
@role_required("GUARD", "ADMIN")
def list_vehicle_entries():
    """Historial de entradas; con inside=true solo los que siguen adentro y con overdue=true los vencidos.

    Con counts=true la respuesta trae además ``counts``: cuántas entradas hay adentro, vencidas, ya
    salidas y en total entre las de esa placa y ese apartamento, para las pestañas de la web (HU-088).
    """
    run_alerts()
    plate = (request.args.get("plate") or "").strip()
    apartment_id = int_arg("apartmentId")
    query = vehicles.entries_query(
        inside=bool_arg("inside"),
        overdue=bool_arg("overdue"),
        plate=plate,
        apartment_id=apartment_id,
    )
    extra = {"counts": vehicles.entry_counts(plate, apartment_id)} if bool_arg("counts") else None
    return paginated(query, "vehicleEntries", default_size=25, extra=extra)


# --- Vehículos de residentes (HU-040) ---------------------------------------

@bp.get("/resident-vehicles")
@token_required
@role_required("GUARD", "ADMIN")
def search_resident_vehicles():
    """Busca por una parte de la placa y dice si cada vehículo está adentro."""
    found = vehicles.search_resident_vehicles(request.args.get("search"))
    return jsonify({"vehicles": found})


@bp.post("/resident-vehicles/<string:plate>/movements")
@token_required
@role_required("GUARD")
def register_resident_movement(plate):
    data = json_object()
    vehicle, movement, warning = vehicles.register_resident_movement(
        plate, data.get("type"), g.current_user
    )
    save_changes()
    body = {
        "message": f"{movement.movement_type.capitalize()} registrada: {movement.plate}.",
        "movement": movement.to_dict(),
        "vehicle": vehicles.resident_vehicle_dict(vehicle, movement),
    }
    if warning:
        body["warning"] = warning
    return jsonify(body), 201
