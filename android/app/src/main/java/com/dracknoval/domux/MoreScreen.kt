package com.dracknoval.domux

import android.util.Log
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.background
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.dracknoval.domux.data.ComplexInfoStore
import com.dracknoval.domux.data.PushRegistration
import com.dracknoval.domux.data.Session
import com.dracknoval.domux.ui.theme.DomuxColor
import kotlinx.coroutines.launch

/**
 * «Más» (en el residente se llama «Mi hogar»): quién tiene la sesión, lo que no cabe en el menú
 * de abajo y el botón para cerrar sesión.
 */
@Composable
fun MoreScreen(navController: NavController) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var logoutError by remember { mutableStateOf("") }
    // Se lee para que el nombre cambie si otro guardia recibe el turno.
    @Suppress("UNUSED_VARIABLE")
    val sessionVersion = Session.changeCount
    val title = if (Session.isResident) "Mi hogar" else "Más"

    DomuxScreenScaffold(title = title, navController = navController) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            DomuxCard(Modifier.fillMaxWidth()) {
                Row(
                    Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    ComplexLogo(size = 48.dp, describe = false)
                    Column(Modifier.padding(start = 14.dp)) {
                        Text(
                            Session.userName?.takeIf { it.isNotBlank() } ?: "Usuario",
                            style = MaterialTheme.typography.titleMedium
                        )
                        Text(
                            listOfNotNull(roleLabel(Session.role), Session.apartment?.takeIf { it.isNotBlank() })
                                .joinToString(" · "),
                            color = DomuxColor.TextMuted,
                            style = MaterialTheme.typography.bodySmall
                        )
                        Text(ComplexInfoStore.displayName, color = DomuxColor.TextMuted, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }

            DomuxCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(vertical = 6.dp)) {
                    moreDestinations().forEach { destination ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(min = 56.dp)
                                .clickable(role = Role.Button) { navController.navigate(destination.route) }
                                .padding(horizontal = 16.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(16.dp)
                        ) {
                            Box(
                                Modifier
                                    .size(40.dp)
                                    .background(DomuxColor.Selected, CircleShape),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(
                                    painterResource(destination.icon),
                                    contentDescription = null,
                                    tint = DomuxColor.Primary,
                                    modifier = Modifier.size(22.dp)
                                )
                            }
                            Text(destination.label, style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                        }
                    }
                }
            }

            Text(
                "Sesión",
                style = MaterialTheme.typography.titleSmall,
                color = DomuxColor.TextMuted,
                modifier = Modifier.semantics { heading() }
            )
            DomuxMessageBanner(logoutError, isError = true) { logoutError = "" }
            OutlinedButton(
                onClick = {
                    scope.launch {
                        logoutError = ""
                        try {
                            PushRegistration.removeCurrentDevice(context.applicationContext)
                        } catch (exception: Exception) {
                            Log.e("DomuxPush", "Could not unregister FCM token during logout.", exception)
                        }
                        try {
                            Session.clear(context)
                            navController.navigate("login") { popUpTo(0) }
                        } catch (exception: Exception) {
                            Log.e("DomuxSession", "Could not clear the session during logout.", exception)
                            logoutError = "No se pudo cerrar la sesión. Intenta de nuevo."
                        }
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp)
            ) {
                Icon(painterResource(R.drawable.ic_logout), contentDescription = null, tint = DomuxColor.Bad)
                Text("Cerrar sesión", color = DomuxColor.Bad, modifier = Modifier.padding(start = 10.dp))
            }
        }
    }
}
