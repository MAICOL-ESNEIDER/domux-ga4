package com.dracknoval.domux

import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavController
import com.dracknoval.domux.data.Session

/**
 * El menú de cada rol. En el celular va abajo (barra de 5 botones) y en la tablet a la izquierda
 * (riel). Lo que no cabe va en «Más» (en el residente, «Mi hogar»). Los nombres son los mismos de
 * la web y de Jira: «Comunicados», «Usuarios», «Archivados».
 */
data class DomuxDestination(val label: String, val route: String, val icon: Int) {
    /** La ruta sin lo que va después del «?», como la registra la navegación. */
    val base: String get() = route.substringBefore("?")

    /** La pestaña que abre en portería («visitas» o «paquetes»), si la ruta la dice. */
    val tab: String? get() = route.substringAfter("tab=", "").takeIf { it.isNotEmpty() }

    /** true si [entry] es esta misma pantalla (y la misma pestaña de portería, si la tiene). */
    fun matches(entry: NavBackStackEntry?): Boolean {
        val current = entry?.destination?.route?.substringBefore("?") ?: return false
        if (current != base) return false
        val wanted = tab ?: return true
        val open = entry?.arguments?.getString("tab").orEmpty().ifEmpty { "paquetes" }
        return open == wanted
    }
}

private val Home = DomuxDestination("Inicio", "home", R.drawable.ic_home)
private val Announcements = DomuxDestination("Comunicados", "announcements", R.drawable.ic_campaign)
private val Reservations = DomuxDestination("Reservas", "reservations", R.drawable.ic_event)
private val Pqrs = DomuxDestination("PQRS", "pqrs", R.drawable.ic_forum)
private val Vehicles = DomuxDestination("Vehículos", "vehicles", R.drawable.ic_car)
private val Notifications = DomuxDestination("Notificaciones", "notifications", R.drawable.ic_notifications)

/** Los botones principales del rol que tiene la sesión. */
fun mainDestinations(): List<DomuxDestination> = when {
    Session.isAdmin -> listOf(
        Home,
        Pqrs,
        Reservations,
        DomuxDestination("Portería", "registry", R.drawable.ic_shield),
        DomuxDestination("Más", "more", R.drawable.ic_more)
    )
    Session.isGuard -> listOf(
        DomuxDestination("Portería", "home", R.drawable.ic_shield),
        DomuxDestination("Visitas", "registry?tab=visitas", R.drawable.ic_person),
        DomuxDestination("Paquetes", "registry?tab=paquetes", R.drawable.ic_package),
        Vehicles,
        DomuxDestination("Más", "more", R.drawable.ic_more)
    )
    else -> listOf(
        Home,
        Announcements,
        Reservations,
        Pqrs,
        DomuxDestination("Mi hogar", "more", R.drawable.ic_my_home)
    )
}

/** Lo que aparece en «Más» (o en «Mi hogar») para el rol que tiene la sesión. */
fun moreDestinations(): List<DomuxDestination> = when {
    Session.isAdmin -> listOf(
        Announcements,
        Vehicles,
        DomuxDestination("Usuarios", "createUser", R.drawable.ic_group),
        DomuxDestination("Estructura de la unidad", "structure", R.drawable.ic_building),
        Notifications
    )
    Session.isGuard -> listOf(Announcements, Notifications)
    else -> listOf(
        DomuxDestination("Mi perfil", "profile", R.drawable.ic_person),
        DomuxDestination("Mis paquetes", "registry?tab=paquetes", R.drawable.ic_package),
        DomuxDestination("Mis visitas y mi QR", "registry?tab=visitas", R.drawable.ic_qr_scan),
        Notifications
    )
}

/**
 * Abre un botón del menú principal. El inicio queda siempre debajo: «atrás» desde cualquier
 * botón vuelve al inicio y no se apilan pantallas repetidas. Cada vez que se abre, la pantalla
 * pide sus datos de nuevo (nada se queda viejo).
 */
fun NavController.openMainDestination(route: String) {
    navigate(route) {
        popUpTo("home")
        launchSingleTop = true
    }
}
