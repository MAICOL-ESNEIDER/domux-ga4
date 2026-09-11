# app.py — backend REST de Domux. Flask + SQLAlchemy (base de datos real:
# SQLite en local, PostgreSQL cuando se despliega en Render).
#
# Cómo correrlo local:
#   pip install -r requirements.txt
#   python app.py
#   -> queda escuchando en http://localhost:5000/
#
# Ver README.md para la lista completa de endpoints y usuarios de prueba.

import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db
from models import User, Announcement, Pqrs, CommonArea, Reservation, PackageItem, Visit
from auth import generate_token, token_required, role_required
from seed import seed_if_empty

load_dotenv()


def create_app():
    app = Flask(__name__)
    CORS(app)  # permite que la app Android (y cualquier cliente) consuma la API

    database_url = os.environ.get("DATABASE_URL", "sqlite:///domux.db")
    # Render entrega la URL de Postgres como "postgres://...", pero SQLAlchemy
    # moderno exige el prefijo "postgresql://...". Este ajuste evita el error
    # más común al desplegar Flask + Postgres en Render.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        seed_if_empty()

    register_routes(app)
    return app


def register_routes(app):

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # ============================= AUTH =============================

    @app.post("/api/auth/login")
    def login():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        user = User.query.filter(db.func.lower(User.email) == email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Credenciales inválidas"}), 401

        token = generate_token(user)
        return jsonify({"message": "Login exitoso", "token": token, "user": user.to_dict()})

    # ======================= USUARIOS (solo Admin) =======================

    @app.get("/api/users")
    @token_required
    @role_required("ADMIN")
    def get_users():
        users = User.query.order_by(User.id).all()
        return jsonify({"users": [u.to_dict() for u in users]})

    @app.post("/api/users")
    @token_required
    @role_required("ADMIN")
    def create_user():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        role = data.get("role")
        apartment = data.get("apartment")

        if not name or not email or not password or role not in ("RESIDENT", "GUARD"):
            return jsonify({"error": "Datos incompletos o rol inválido"}), 400
        if role == "RESIDENT" and not apartment:
            return jsonify({"error": "El residente necesita un apartamento"}), 400
        if User.query.filter(db.func.lower(User.email) == email).first():
            return jsonify({"error": "Ese correo ya está registrado"}), 409

        nuevo = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            apartment=apartment if role == "RESIDENT" else None,
        )
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({"message": "Usuario creado", "user": nuevo.to_dict()}), 201

    # Lista liviana de residentes: Admin Y Guardia pueden verla (para asignar
    # paquetes/visitas a un residente concreto).
    @app.get("/api/residents")
    @token_required
    @role_required("ADMIN", "GUARD")
    def get_residents():
        residentes = User.query.filter_by(role="RESIDENT").order_by(User.name).all()
        return jsonify({"residents": [r.to_resident_summary() for r in residentes]})

    # ======================= ANUNCIOS =======================

    @app.get("/api/announcements")
    @token_required
    def get_announcements():
        anuncios = Announcement.query.order_by(Announcement.created_at.desc()).all()
        return jsonify({"announcements": [a.to_dict() for a in anuncios]})

    @app.post("/api/announcements")
    @token_required
    @role_required("ADMIN")
    def create_announcement():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        message = (data.get("message") or "").strip()
        if not title or not message:
            return jsonify({"error": "Título y mensaje son obligatorios"}), 400

        anuncio = Announcement(title=title, message=message, author_id=g.current_user.id)
        db.session.add(anuncio)
        db.session.commit()
        return jsonify({"message": "Anuncio publicado", "announcement": anuncio.to_dict()}), 201

    # ======================= PQRS =======================
    # GET se comporta distinto según el rol: el backend decide, no la app.

    @app.get("/api/pqrs")
    @token_required
    def get_pqrs():
        user = g.current_user
        if user.role == "ADMIN":
            items = Pqrs.query.order_by(Pqrs.created_at.desc()).all()
        elif user.role == "RESIDENT":
            items = Pqrs.query.filter_by(resident_id=user.id).order_by(Pqrs.created_at.desc()).all()
        else:
            return jsonify({"error": "No tienes permiso para ver las PQRS"}), 403
        return jsonify({"pqrs": [p.to_dict() for p in items]})

    @app.post("/api/pqrs")
    @token_required
    @role_required("RESIDENT")
    def create_pqrs():
        data = request.get_json(silent=True) or {}
        subject = (data.get("subject") or "").strip()
        message = (data.get("message") or "").strip()
        if not subject or not message:
            return jsonify({"error": "Asunto y mensaje son obligatorios"}), 400

        pqrs = Pqrs(resident_id=g.current_user.id, subject=subject, message=message)
        db.session.add(pqrs)
        db.session.commit()
        return jsonify({"message": "PQRS enviada", "pqrs": pqrs.to_dict()}), 201

    @app.put("/api/pqrs/<int:pqrs_id>/respond")
    @token_required
    @role_required("ADMIN")
    def respond_pqrs(pqrs_id):
        pqrs = Pqrs.query.get(pqrs_id)
        if not pqrs:
            return jsonify({"error": "PQRS no encontrada"}), 404

        data = request.get_json(silent=True) or {}
        status = data.get("status")
        response_text = data.get("adminResponse")
        if status not in ("abierta", "en_proceso", "resuelta"):
            return jsonify({"error": "Estado inválido"}), 400

        pqrs.status = status
        pqrs.admin_response = response_text
        db.session.commit()
        return jsonify({"message": "PQRS actualizada", "pqrs": pqrs.to_dict()})

    # ======================= ZONAS COMUNES Y RESERVAS =======================

    @app.get("/api/common-areas")
    @token_required
    def get_common_areas():
        areas = CommonArea.query.order_by(CommonArea.name).all()
        return jsonify({"areas": [a.to_dict() for a in areas]})

    @app.get("/api/reservations")
    @token_required
    def get_reservations():
        user = g.current_user
        if user.role == "ADMIN":
            items = Reservation.query.order_by(Reservation.created_at.desc()).all()
        elif user.role == "RESIDENT":
            items = Reservation.query.filter_by(resident_id=user.id).order_by(Reservation.created_at.desc()).all()
        else:
            return jsonify({"error": "No tienes permiso para ver las reservas"}), 403
        return jsonify({"reservations": [r.to_dict() for r in items]})

    @app.post("/api/reservations")
    @token_required
    @role_required("RESIDENT")
    def create_reservation():
        data = request.get_json(silent=True) or {}
        common_area_id = data.get("commonAreaId")
        date = (data.get("date") or "").strip()
        time_slot = (data.get("timeSlot") or "").strip()

        area = CommonArea.query.get(common_area_id) if common_area_id else None
        if not area or not date or not time_slot:
            return jsonify({"error": "Zona, fecha y horario son obligatorios"}), 400

        reserva = Reservation(
            resident_id=g.current_user.id,
            common_area_id=area.id,
            date=date,
            time_slot=time_slot,
        )
        db.session.add(reserva)
        db.session.commit()
        return jsonify({"message": "Reserva creada", "reservation": reserva.to_dict()}), 201

    @app.put("/api/reservations/<int:res_id>/cancel")
    @token_required
    @role_required("RESIDENT", "ADMIN")
    def cancel_reservation(res_id):
        reserva = Reservation.query.get(res_id)
        if not reserva:
            return jsonify({"error": "Reserva no encontrada"}), 404
        if g.current_user.role == "RESIDENT" and reserva.resident_id != g.current_user.id:
            return jsonify({"error": "Esa reserva no es tuya"}), 403

        reserva.status = "cancelada"
        db.session.commit()
        return jsonify({"message": "Reserva cancelada", "reservation": reserva.to_dict()})

    # ======================= PAQUETES =======================

    @app.get("/api/packages")
    @token_required
    def get_packages():
        user = g.current_user
        if user.role == "RESIDENT":
            items = PackageItem.query.filter_by(resident_id=user.id).order_by(PackageItem.created_at.desc()).all()
        else:  # ADMIN y GUARD ven todos los paquetes registrados
            items = PackageItem.query.order_by(PackageItem.created_at.desc()).all()
        return jsonify({"packages": [p.to_dict() for p in items]})

    @app.post("/api/packages")
    @token_required
    @role_required("GUARD")
    def register_package():
        data = request.get_json(silent=True) or {}
        resident_id = data.get("residentId")
        description = data.get("description")

        residente = User.query.filter_by(id=resident_id, role="RESIDENT").first()
        if not residente:
            return jsonify({"error": "Selecciona un residente válido"}), 400

        paquete = PackageItem(
            resident_id=residente.id,
            registered_by=g.current_user.id,
            description=description,
        )
        db.session.add(paquete)
        db.session.commit()
        return jsonify({"message": "Paquete registrado", "packageItem": paquete.to_dict()}), 201

    @app.put("/api/packages/<int:pkg_id>/deliver")
    @token_required
    @role_required("GUARD")
    def deliver_package(pkg_id):
        paquete = PackageItem.query.get(pkg_id)
        if not paquete:
            return jsonify({"error": "Paquete no encontrado"}), 404

        paquete.status = "entregado"
        paquete.delivered_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"message": "Paquete marcado como entregado", "packageItem": paquete.to_dict()})

    # ======================= VISITANTES / DOMICILIARIOS =======================

    @app.get("/api/visits")
    @token_required
    def get_visits():
        user = g.current_user
        if user.role == "RESIDENT":
            items = Visit.query.filter_by(resident_id=user.id).order_by(Visit.created_at.desc()).all()
        else:  # ADMIN y GUARD ven todas las visitas registradas
            items = Visit.query.order_by(Visit.created_at.desc()).all()
        return jsonify({"visits": [v.to_dict() for v in items]})

    @app.post("/api/visits")
    @token_required
    @role_required("GUARD")
    def register_visit():
        data = request.get_json(silent=True) or {}
        resident_id = data.get("residentId")
        visitor_name = (data.get("visitorName") or "").strip()
        tipo = data.get("type")

        residente = User.query.filter_by(id=resident_id, role="RESIDENT").first()
        if not residente or not visitor_name or tipo not in ("visitante", "domiciliario"):
            return jsonify({"error": "Datos incompletos para registrar el ingreso"}), 400

        visita = Visit(
            resident_id=residente.id,
            registered_by=g.current_user.id,
            visitor_name=visitor_name,
            type=tipo,
        )
        db.session.add(visita)
        db.session.commit()
        return jsonify({"message": "Ingreso registrado", "visit": visita.to_dict()}), 201

    # ======================= ERRORES GENÉRICOS =======================

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Recurso no encontrado"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Error interno del servidor"}), 500


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
