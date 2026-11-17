package com.dracknoval.domux

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.AppPreferences
import com.dracknoval.domux.data.RecentAccount
import com.dracknoval.domux.data.TextSize
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Preferencias, para todos los roles: el tamaño del texto de la app y las cuentas que este
 * celular recuerda al iniciar sesión. Todo se guarda en el celular, nada va al servidor. La misma
 * opción existe en la web, que además cambia la apariencia (Mixto u Oscuro): ese cambio de colores
 * llega a la app en la versión completa.
 */
@Composable
fun PreferencesScreen(navController: NavController, viewModel: PreferencesViewModel = viewModel()) {
    val state by viewModel.state.collectAsState()
    val context = LocalContext.current.applicationContext

    LaunchedEffect(Unit) { viewModel.load(context) }

    DomuxScreenScaffold(title = "Preferencias", navController = navController) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            DomuxMessageBanner(state.message, isError = false) { viewModel.dismissMessage() }
            TextSizeCard(current = AppPreferences.textSize) { AppPreferences.saveTextSize(context, it) }
            AccountsCard(
                accounts = state.accounts,
                onForget = { viewModel.forget(context, it) },
                onForgetAll = { viewModel.forgetAll(context) }
            )
            Text(
                "Los colores de la app (Mixto u Oscuro) se podrán cambiar en la versión completa.",
                color = DomuxColor.TextMuted,
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

/** «Tamaño del texto»: normal, grande o muy grande; el cambio se ve de una vez en toda la app. */
@Composable
private fun TextSizeCard(current: TextSize, onChoose: (TextSize) -> Unit) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                "Tamaño del texto",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.semantics { heading() }
            )
            Text(
                "Se aplica a toda la app en este celular y se suma al tamaño que ya tenga el celular.",
                color = DomuxColor.TextMuted,
                style = MaterialTheme.typography.bodySmall
            )
            Column(Modifier.selectableGroup()) {
                TextSize.values().forEach { option ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 48.dp)
                            .selectable(
                                selected = option == current,
                                onClick = { onChoose(option) },
                                role = Role.RadioButton
                            ),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(selected = option == current, onClick = null)
                        Text(option.label, modifier = Modifier.padding(start = 12.dp))
                    }
                }
            }
            Text("Así se ve el texto con este tamaño.", color = DomuxColor.TextSoft)
        }
    }
}

/** «Cuentas recordadas en este celular», con su X para quitar cada una y «Quitar todas». */
@Composable
private fun AccountsCard(
    accounts: List<RecentAccount>,
    onForget: (RecentAccount) -> Unit,
    onForgetAll: () -> Unit
) {
    DomuxCard(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                "Cuentas recordadas en este celular",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.semantics { heading() }
            )
            Text(
                "Solo se guardan el correo y el nombre, nunca la contraseña. Salen al iniciar sesión para " +
                    "elegir la cuenta sin escribir el correo.",
                color = DomuxColor.TextMuted,
                style = MaterialTheme.typography.bodySmall
            )
            if (accounts.isEmpty()) {
                Text("No hay cuentas recordadas. Se recuerdan al iniciar sesión si marcas «Recordar mi correo en este celular».")
            } else {
                accounts.forEach { account ->
                    key(account.email) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            AccountAvatar(account)
                            Spacer(Modifier.width(12.dp))
                            AccountNameAndEmail(account, Modifier.weight(1f))
                            IconButton(onClick = { onForget(account) }) {
                                Icon(
                                    painterResource(R.drawable.ic_close),
                                    contentDescription = "Quitar ${account.email} de este celular",
                                    tint = DomuxColor.TextMuted,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                        }
                    }
                }
                OutlinedButton(
                    onClick = onForgetAll,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                ) {
                    Text("Quitar todas")
                }
            }
        }
    }
}
