// LoginScreen.kt — pantalla de inicio de sesión. Es la MISMA pantalla para los 3
// roles (Administrador, Residente, Guardia): el backend le dice a la app qué rol
// tiene el usuario, y a partir de ahí HomeScreen decide qué mostrarle.

package com.dracknoval.domux

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.data.RecentAccount
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Inicio de sesión (HU-001). La pantalla solo dibuja: la revisión de los campos, la llamada al
 * servidor y las cuentas recordadas están en [LoginViewModel].
 *
 * Si en este celular hay cuentas recordadas, primero sale la lista «Cuentas recientes en este
 * celular»: se toca la cuenta y solo falta la contraseña. Si no hay, sale el formulario de siempre.
 */
@Composable
fun LoginScreen(
    navController: NavController,
    onLoginComplete: () -> Unit = {},
    viewModel: LoginViewModel = viewModel()
) {
    val state by viewModel.state.collectAsState()
    val appContext = LocalContext.current.applicationContext
    // Mostrar u ocultar la contraseña es solo de la pantalla; por defecto va oculta.
    var showPassword by rememberSaveable { mutableStateOf(false) }
    val passwordFocus = remember { FocusRequester() }

    LaunchedEffect(Unit) { viewModel.loadRecentAccounts(appContext) }

    LaunchedEffect(state.loggedIn) {
        if (state.loggedIn) {
            navController.navigate("home") { popUpTo("login") { inclusive = true } }
            onLoginComplete()
        }
    }

    // Al tocar una cuenta de la lista, el cursor pasa directo a la contraseña.
    LaunchedEffect(state.chosenAccount) {
        if (state.chosenAccount != null) runCatching { passwordFocus.requestFocus() }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        DomuxBrandMark(size = 64.dp)
        Spacer(Modifier.height(14.dp))
        Text("DOMUX", fontSize = 27.sp, fontWeight = FontWeight.Bold, letterSpacing = 3.sp)
        Text("Residential Security OS", color = DomuxColor.TextMuted, fontSize = 13.sp)
        Spacer(Modifier.height(22.dp))
        Surface(
            color = DomuxColor.Selected,
            shape = RoundedCornerShape(50),
            border = BorderStroke(1.dp, DomuxColor.Line)
        ) {
            Text(
                "SISTEMA INTELIGENTE DE OPERACIÓN RESIDENCIAL",
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                color = DomuxColor.Primary,
                fontSize = 9.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 0.7.sp
            )
        }
        Spacer(Modifier.height(20.dp))
        Text(
            buildAnnotatedString {
                append("Tu comunidad, en modo\n")
                withStyle(
                    SpanStyle(
                        brush = Brush.linearGradient(
                            listOf(DomuxColor.Cyan, DomuxColor.Violet, DomuxColor.Purple)
                        ),
                        fontWeight = FontWeight.Bold
                    )
                ) {
                    append("premium.")
                }
            },
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.SemiBold,
            lineHeight = 34.sp,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        state.removedAccount?.let { removed ->
            RemovedAccountNotice(
                account = removed,
                onUndo = { viewModel.undoForgetAccount(appContext) },
                onDismiss = viewModel::dismissRemovedNotice
            )
            Spacer(Modifier.height(16.dp))
        }

        when {
            // Mientras se leen las cuentas recordadas no se dibuja nada, para que no parpadee.
            !state.accountsLoaded -> Unit
            state.showingAccounts -> RecentAccountsSection(
                accounts = state.recentAccounts,
                onChoose = viewModel::chooseAccount,
                onForget = { viewModel.forgetAccount(appContext, it) },
                onUseAnother = viewModel::useAnotherAccount
            )
            else -> {
                val chosen = state.chosenAccount
                if (chosen != null) {
                    ChosenAccountCard(chosen, onChange = viewModel::backToAccounts)
                } else {
                    OutlinedTextField(
                        value = state.email,
                        onValueChange = viewModel::onEmail,
                        label = { Text("Correo") },
                        singleLine = true,
                        isError = state.emailMissing || state.emailInvalid,
                        supportingText = {
                            if (state.emailMissing) Text("El correo es obligatorio")
                            else if (state.emailInvalid) Text("Ingresa un correo válido")
                        },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                Spacer(Modifier.height(12.dp))

                OutlinedTextField(
                    value = state.password,
                    onValueChange = viewModel::onPassword,
                    label = { Text("Contraseña") },
                    singleLine = true,
                    visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = {
                        TextButton(onClick = { showPassword = !showPassword }) {
                            Text(if (showPassword) "Ocultar" else "Mostrar")
                        }
                    },
                    isError = state.passwordMissing,
                    supportingText = { if (state.passwordMissing) Text("La contraseña es obligatoria") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { viewModel.login(appContext) }),
                    modifier = Modifier
                        .fillMaxWidth()
                        .focusRequester(passwordFocus)
                )

                // La casilla solo sale al escribir el correo a mano: una cuenta elegida ya está recordada.
                if (chosen == null) {
                    DomuxCheckRow(
                        label = "Recordar mi correo en este celular",
                        checked = state.rememberEmail,
                        onCheckedChange = viewModel::onRememberEmail
                    )
                    Text(
                        "Solo el correo, nunca la contraseña. No la marques en un celular compartido.",
                        color = DomuxColor.TextMuted,
                        fontSize = 12.sp,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(start = 4.dp)
                    )
                }
                Spacer(Modifier.height(24.dp))

                Button(
                    onClick = { viewModel.login(appContext) },
                    enabled = !state.busy,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(if (state.busy) "Entrando..." else "Entrar")
                }

                if (chosen == null && state.recentAccounts.isNotEmpty()) {
                    Spacer(Modifier.height(4.dp))
                    TextButton(onClick = viewModel::backToAccounts, modifier = Modifier.fillMaxWidth()) {
                        Text("Volver a las cuentas recientes")
                    }
                }
            }
        }

        if (state.message.isNotBlank()) {
            Spacer(Modifier.height(20.dp))
            DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
        }

        // Los documentos legales se pueden leer antes de iniciar sesión.
        Spacer(Modifier.height(12.dp))
        TextButton(onClick = { navController.navigate("legal") }) {
            Text("Política de datos, términos y más", color = DomuxColor.TextMuted)
        }
    }
}

/** La lista «Cuentas recientes en este celular», con su X para quitar cada una. */
@Composable
private fun RecentAccountsSection(
    accounts: List<RecentAccount>,
    onChoose: (RecentAccount) -> Unit,
    onForget: (RecentAccount) -> Unit,
    onUseAnother: () -> Unit
) {
    Column(Modifier.fillMaxWidth()) {
        Text(
            "Cuentas recientes en este celular",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.semantics { heading() }
        )
        Text(
            "Toca tu cuenta y escribe solo la contraseña.",
            color = DomuxColor.TextMuted,
            fontSize = 13.sp,
            modifier = Modifier.padding(top = 2.dp, bottom = 12.dp)
        )
        accounts.forEach { account ->
            key(account.email) {
                RecentAccountRow(account, onChoose = { onChoose(account) }, onForget = { onForget(account) })
                Spacer(Modifier.height(8.dp))
            }
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(onClick = onUseAnother, modifier = Modifier.fillMaxWidth()) {
            Text("Usar otra cuenta")
        }
    }
}

@Composable
private fun RecentAccountRow(account: RecentAccount, onChoose: () -> Unit, onForget: () -> Unit) {
    Surface(
        color = DomuxColor.Card,
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, DomuxColor.Line),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            // Toda la fila (círculo, nombre y correo) es un solo botón; la X va aparte.
            Row(
                modifier = Modifier
                    .weight(1f)
                    .clickable(onClickLabel = "entrar con esta cuenta", role = Role.Button, onClick = onChoose)
                    .padding(horizontal = 14.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                AccountAvatar(account)
                Spacer(Modifier.width(12.dp))
                AccountNameAndEmail(account, Modifier.weight(1f))
            }
            IconButton(onClick = onForget) {
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

/** La cuenta elegida, arriba de la contraseña, con «Cambiar» para volver a la lista. */
@Composable
private fun ChosenAccountCard(account: RecentAccount, onChange: () -> Unit) {
    Surface(
        color = DomuxColor.Selected,
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, DomuxColor.Line),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(start = 14.dp, top = 10.dp, bottom = 10.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            AccountAvatar(account)
            Spacer(Modifier.width(12.dp))
            AccountNameAndEmail(
                account,
                Modifier
                    .weight(1f)
                    .semantics(mergeDescendants = true) {}
            )
            TextButton(
                onClick = onChange,
                modifier = Modifier.semantics { contentDescription = "Cambiar de cuenta" }
            ) {
                Text("Cambiar")
            }
        }
    }
}

/** Círculo con las iniciales; el lector de pantalla lo salta porque el nombre ya se lee al lado. */
@Composable
private fun AccountAvatar(account: RecentAccount, size: Dp = 40.dp) {
    Box(
        modifier = Modifier
            .size(size)
            .background(Brush.linearGradient(listOf(DomuxColor.Cyan, DomuxColor.Violet)), CircleShape)
            .clearAndSetSemantics {},
        contentAlignment = Alignment.Center
    ) {
        Text(account.initials, color = DomuxColor.OnPrimary, fontWeight = FontWeight.Bold, fontSize = 15.sp)
    }
}

@Composable
private fun AccountNameAndEmail(account: RecentAccount, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(account.displayName, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(
            account.email,
            color = DomuxColor.TextMuted,
            fontSize = 13.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

/** Aviso después de tocar la X: la cuenta se puede devolver con «Deshacer». */
@Composable
private fun RemovedAccountNotice(account: RecentAccount, onUndo: () -> Unit, onDismiss: () -> Unit) {
    Surface(
        color = DomuxColor.Card,
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, DomuxColor.Line),
        modifier = Modifier
            .fillMaxWidth()
            .semantics { liveRegion = LiveRegionMode.Polite }
    ) {
        Row(
            modifier = Modifier.padding(start = 14.dp, top = 6.dp, bottom = 6.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                "Se quitó ${account.email} de este celular.",
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.bodyMedium
            )
            TextButton(onClick = onUndo) { Text("Deshacer") }
            IconButton(onClick = onDismiss) {
                Icon(
                    painterResource(R.drawable.ic_close),
                    contentDescription = "Cerrar el aviso",
                    tint = DomuxColor.TextMuted,
                    modifier = Modifier.size(20.dp)
                )
            }
        }
    }
}
