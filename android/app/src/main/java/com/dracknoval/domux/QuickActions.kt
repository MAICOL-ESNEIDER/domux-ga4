package com.dracknoval.domux

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.RowScope
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
 * atajos de la web; la portería, los tres registros que más hace. Los residentes no lo tienen.
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
    else -> emptyList()
}

/** true si a este rol se le muestran los botones «Buscar» y «+ Nuevo» en la barra de arriba. */
fun hasQuickActions(): Boolean = Session.isAdmin || Session.isGuard

/**
 * Los dos botones de la barra de arriba de la administración y la portería: la lupa abre el
 * buscador general y «+ Nuevo» abre un menú para crear algo sin pasar por el menú de abajo.
 */
@Composable
fun RowScope.DomuxQuickActions(navController: NavController) {
    var menuOpen by remember { mutableStateOf(false) }
    IconButton(onClick = { navController.navigate("search") { launchSingleTop = true } }) {
        Icon(painterResource(R.drawable.ic_search), contentDescription = "Buscar")
    }
    Box {
        IconButton(onClick = { menuOpen = true }) {
            Icon(painterResource(R.drawable.ic_add), contentDescription = "Nuevo: crear algo")
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
