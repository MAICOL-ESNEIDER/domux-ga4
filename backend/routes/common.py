"""Piezas que comparten las rutas de la API."""

from flask import jsonify, request
from sqlalchemy.exc import IntegrityError

from errors import ApiError, error_response
from extensions import db
from validators import validate_no_empty_strings


def _body_problem(data):
    """Qué está mal en un cuerpo JSON (no es un objeto o trae textos vacíos), o None."""
    if not isinstance(data, dict):
        return "El cuerpo de la solicitud debe ser un objeto JSON válido."
    return validate_no_empty_strings(data)


def json_body():
    """Lee el cuerpo JSON de la solicitud y revisa que no traiga textos vacíos.

    Devuelve ``(datos, None)`` si todo está bien, o ``(None, respuesta_de_error)``
    para que la ruta responda con el error tal cual.
    """
    data = request.get_json(silent=True)
    message = _body_problem(data)
    if message:
        return None, error_response(400, message)
    return data, None


def json_object(required=False):
    """Como json_body, pero un cuerpo inválido lanza ApiError (400).

    Con required=True el objeto tampoco puede venir vacío: es lo que piden las
    rutas que modifican, que necesitan al menos un dato.
    """
    data = request.get_json(silent=True)
    message = _body_problem(data)
    if message:
        raise ApiError(message)
    if required and not data:
        raise ApiError("Debes proporcionar al menos un dato para actualizar.")
    return data


def page_args(default_size=25, max_size=100):
    """Lee page y pageSize de la URL; devuelve (página, tamaño) o lanza un error 400."""
    page = request.args.get("page", default=1, type=int)
    size = request.args.get("pageSize", default=default_size, type=int)
    if page is None or page < 1 or size is None or not 1 <= size <= max_size:
        raise ApiError(f"La página debe ser positiva y pageSize debe estar entre 1 y {max_size}.")
    return page, size


def paginated(query, key, default_size=25, max_size=100):
    """Responde una lista paginada: {key: [...], page, pageSize, total, totalPages}."""
    page, size = page_args(default_size, max_size)
    total = query.count()
    items = query.offset((page - 1) * size).limit(size).all()
    return jsonify({
        key: [item.to_dict() for item in items],
        "page": page,
        "pageSize": size,
        "total": total,
        "totalPages": (total + size - 1) // size,
    })


def save_changes(duplicate_message="Ese dato ya está registrado."):
    """Guarda los cambios; si la base rechaza un duplicado, responde 409.

    Las rutas ya revisan los duplicados antes de guardar; esto cubre el caso de
    dos solicitudes que llegan a la vez con el mismo código.
    """
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise ApiError(duplicate_message, 409) from error
