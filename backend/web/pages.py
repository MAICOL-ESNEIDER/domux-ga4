"""Piezas comunes de las páginas de la web: el menú, lo que ven todas las plantillas y los errores.

Aquí no hay reglas del conjunto: solo lo que se repite en cada página (la barra lateral, los íconos,
el código contra CSRF de los formularios y las páginas de error con el mismo diseño).
"""

from flask import current_app, g, render_template, request, url_for
from markupsafe import Markup

from extensions import db
from web import bp
from web.security import csrf_token, current_admin

#: El menú de la barra lateral. Es el mismo de la app, agrupado como lo aprobó el equipo (DEC-097):
#: cada página es (nombre, ruta, ícono, prefijo de sus rutas). Una página que todavía no existe
#: no se muestra.
MENU = (
    (None, (
        ("Inicio", "web.panel", "home", "web.panel"),
    )),
    ("Operación diaria", (
        ("PQRS", "web.pqrs_list", "chat", "web.pqrs"),
        ("Reservas", "web.reservations_list", "calendar", "web.reservation"),
        ("Comunicados", "web.announcements_list", "megaphone", "web.announcement"),
        ("Paquetería y visitas", "web.registry_packages", "package", "web.registry"),
        ("Notificaciones", "web.notifications_list", "bell", "web.notification"),
    )),
    ("Comunidad", (
        ("Usuarios", "web.users_list", "users", "web.user"),
        ("Estructura de la unidad", "web.structure_towers", "building", "web.structure"),
    )),
    ("Configuración", (
        ("Datos de la unidad", "web.unit_data", "card", "web.unit"),
        ("Zonas comunes y reglas", "web.zones_list", "sliders", "web.zone"),
    )),
)

#: Íconos de trazo (viewBox 24). Son texto fijo del programa, nunca datos de nadie.
ICONS = {
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
    "chat": '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "megaphone": '<path d="M3 11v3a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1z"/>'
                 '<path d="M15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12"/>',
    "package": '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "bell": '<path d="M18 16V11a6 6 0 1 0-12 0v5l-2 2h16z"/><path d="M10 21a2 2 0 0 0 4 0"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/>'
             '<path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5"/>',
    "building": '<rect x="4" y="3" width="16" height="18" rx="1"/>'
                '<path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/>',
    "card": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2"/>'
            '<path d="M6 16a3 3 0 0 1 6 0M14 10h4M14 14h4"/>',
    "sliders": '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "logout": '<path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4M16 8l4 4-4 4M20 12H9"/>',
}

ROLE_LABELS = {"ADMIN": "Administración", "GUARD": "Portería", "RESIDENT": "Residente"}


def icon(name):
    """El ícono como imagen vectorial; para lectores de pantalla no dice nada (el texto va al lado)."""
    return Markup(
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        f"{ICONS.get(name, '')}</svg>"
    )


def csrf_input():
    """El campo escondido con el código contra CSRF que lleva cada formulario que cambia algo."""
    return Markup('<input type="hidden" name="csrf_token" value="{}">').format(csrf_token())


def menu_groups():
    """Los grupos del menú con sus páginas, marcando en la que está la persona."""
    current = request.endpoint or ""
    groups = []
    for title, pages in MENU:
        items = []
        for label, endpoint, icon_name, prefix in pages:
            if endpoint not in current_app.view_functions:
                continue
            items.append({
                "label": label,
                "url": url_for(endpoint),
                "icon": icon_name,
                "active": current.startswith(prefix),
            })
        if items:
            groups.append({"title": title, "pages": items})
    return groups


@bp.app_context_processor
def inject_layout():
    """Lo que toda plantilla de la web puede usar sin que cada página lo pase."""
    return {
        "csrf_input": csrf_input,
        "icon": icon,
        "menu_groups": menu_groups,
        "web_user": g.get("web_user"),
        "role_labels": ROLE_LABELS,
    }


# --- Errores con el mismo diseño ------------------------------------------------------------------

#: Título y explicación de cada error, en palabras de la administración (nada técnico).
ERROR_TEXTS = {
    400: ("No pudimos procesar la solicitud", "Vuelve a la página anterior e inténtalo de nuevo."),
    403: ("Sin permiso", "Tu cuenta no tiene permiso para ver esta página."),
    404: ("No encontramos esa página", "La dirección no existe o ya no está disponible."),
    405: ("Acción no permitida", "Esa acción no se puede hacer desde esta página."),
    413: ("El archivo es muy grande", "El archivo supera el máximo permitido (12 MB). Elige uno más liviano."),
    429: ("Demasiadas solicitudes", "Espera un momento e inténtalo de nuevo."),
    500: (
        "Algo salió mal",
        "Tuvimos un problema en el servidor. Inténtalo de nuevo; si sigue pasando, avisa al equipo técnico.",
    ),
}

CSRF_TEXT = (
    "El formulario venció",
    "Por seguridad, ese formulario ya no es válido: la sesión venció o el navegador no está guardando "
    "cookies. Recarga la página e inténtalo de nuevo.",
)


def render_error(status, description=None):
    """La página de error de la web para el código HTTP dado, junto con ese código."""
    if status == 400 and description == "csrf":
        title, message = CSRF_TEXT
    else:
        title, message = ERROR_TEXTS.get(status, ERROR_TEXTS[500])
    try:
        # Si el error dejó la transacción a medias, se limpia antes de volver a leer la base.
        db.session.rollback()
        if g.get("web_user") is None:
            # Un error en una ruta que no pidió sesión (por ejemplo, una página que no existe):
            # si quien navega es un administrador con sesión, se le muestra el menú de siempre.
            g.web_user, _reason = current_admin()
        return render_template("web/error.html", status=status, title=title, message=message), status
    except Exception:  # noqa: BLE001 - la página de error nunca debe fallar por segunda vez
        return f"{status} · {title}", status
