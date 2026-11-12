// LoginScreen.kt — pantalla de inicio de sesión. Es la MISMA pantalla para los 3
// roles (Administrador, Residente, Guardia): el backend le dice a la app qué rol
// tiene el usuario, y a partir de ahí HomeScreen decide qué mostrarle.

package com.dracknoval.domux

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.dracknoval.domux.ui.theme.DomuxColor

/**
 * Inicio de sesión (HU-001). La pantalla solo dibuja: la revisión de los campos y la llamada al
 * servidor están en [LoginViewModel].
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

    LaunchedEffect(state.loggedIn) {
        if (state.loggedIn) {
            navController.navigate("home") { popUpTo("login") { inclusive = true } }
            onLoginComplete()
        }
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
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(24.dp))

        Button(
            onClick = { viewModel.login(appContext) },
            enabled = !state.busy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (state.busy) "Entrando..." else "Entrar")
        }

        if (state.message.isNotBlank()) {
            Spacer(Modifier.height(20.dp))
            DomuxMessageBanner(state.message, state.messageIsError) { viewModel.dismissMessage() }
        }
    }
}
