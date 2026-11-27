package com.dracknoval.domux

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Un atajo del botón «+ Nuevo»: lo que dice y la ruta que abre. Cada atajo abre la pantalla donde
 * se crea eso, ya en la pestaña (o con la ventana) de crear.
 */
data class QuickCreateItem(val label: String, val route: String)

/**
 * Lo que el botón «+ Nuevo» deja crear según el rol (HU-089). La administración tiene los mismos
 * atajos de la web; la portería, los tres registros que más hace; el residente, lo que más usa
 * (QR para una visita, reserva, PQRS y ver sus paquetes y visitas).
 */
fun quickCreateItems(): List<QuickCreateItem> = when {
    Session.isAdmin -> listOf(
        QuickCreateItem("Comunicado", "announcements?tab=publicar"),
        QuickCreateItem("Usuario", "createUser?tab=crear"),
        QuickCreateItem("Torre", "structure?action=torre"),
        QuickCreateItem("Apartamento", "structure?action=apartamento"),
        QuickCreateItem("PQRS para un residente", "pqrs?tab=nueva")
    )
    Session.isGuard -> listOf(
        QuickCreateItem("Visita", "registry?tab=registrar-visita"),
        QuickCreateItem("Paquete", "registry?tab=registrar-paquete"),
        QuickCreateItem("Entrada de vehículo", "vehicles?tab=registrar-entrada")
    )
    Session.isResident -> listOf(
        QuickCreateItem("QR para una visita", "registry?tab=qr"),
        QuickCreateItem("Reserva de zona común", "reservations?tab=nueva"),
        QuickCreateItem("PQRS (petición, queja o reclamo)", "pqrs?tab=nueva"),
        QuickCreateItem("Ver mis paquetes", "registry?tab=paquetes"),
        QuickCreateItem("Ver mis visitas", "registry?tab=visitas")
    )
    else -> emptyList()
}

/** true si a este rol se le muestra el buscador general (lupa); el residente no lo tiene. */
fun hasQuickActions(): Boolean = Session.isAdmin || Session.isGuard

/** true si a este rol se le muestra el botón «+ Nuevo» en la barra de arriba (todos los roles). */
fun hasNewMenu(): Boolean = quickCreateItems().isNotEmpty()

/**
 * Los botones de la barra de arriba: la lupa (administración y portería) abre el buscador general y
 * «+ Nuevo» (todos los roles, como en la web) abre un menú para crear algo sin pasar por el menú de abajo.
 */
@Composable
fun RowScope.DomuxQuickActions(navController: NavController) {
    var menuOpen by remember { mutableStateOf(false) }
    if (hasQuickActions()) {
        IconButton(onClick = { navController.navigate("search") { launchSingleTop = true } }) {
            Icon(painterResource(R.drawable.ic_search), contentDescription = "Buscar")
        }
    }
    Box(Modifier.padding(end = 8.dp)) {
        Button(
            onClick = { menuOpen = true },
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
            modifier = Modifier.heightIn(min = 40.dp)
        ) {
            Icon(painterResource(R.drawable.ic_add), contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(4.dp))
            Text("Nuevo")
        }
        DropdownMenu(
            expanded = menuOpen,
            onDismissRequest = { menuOpen = false },
            modifier = Modifier.background(DomuxColor.Card)
        ) {
            quickCreateItems().forEach { item ->
                DropdownMenuItem(
                    text = { Text(item.label, color = DomuxColor.Text) },
                    onClick = {
                        menuOpen = false
                        navController.navigate(item.route)
                    }
                )
            }
        }
    }
}
