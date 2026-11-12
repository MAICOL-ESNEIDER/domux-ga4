package com.dracknoval.domux.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Los colores de DOMUX con nombre. Son los mismos de la web de administración (las variables de
 * domux.css) y cada uno tiene un solo significado:
 *
 * - Azul ([Primary]) es lo que se toca.
 * - Verde, amarillo y rojo son estados, y siempre van con un ícono y una palabra.
 * - Cian y violeta solo adornan; nunca son botones.
 *
 * Ninguna pantalla escribe un color a mano: lo toma de aquí o del tema.
 */
object DomuxColor {
    // Fondos
    /** Fondo de todas las pantallas (--bg). */
    val Background = Color(0xFF0B172A)

    /** Paneles y barras (--surface). */
    val Surface = Color(0xFF091426)

    /** Tarjetas (--card). */
    val Card = Color(0xFF0F1E33)

    /** Barra superior, barra de abajo y el texto que va sobre el azul. */
    val Deep = Color(0xFF07111F)

    /** Lo elegido en un menú o en una pestaña. */
    val Selected = Color(0xFF152C4A)

    // Líneas
    /** Solo separa tarjetas; es un adorno (--line). */
    val Line = Color(0xFF1E334D)

    /** Borde de las cajas de texto y las listas: se distingue del fondo (3,5 a 1). */
    val FieldBorder = Color(0xFF64748B)

    // Texto
    /** Títulos y texto (--text). */
    val Text = Color(0xFFF1F5F9)

    /** Texto sobre lo elegido. */
    val TextBright = Color(0xFFF8FAFC)

    /** Texto de apoyo (--soft). */
    val TextSoft = Color(0xFFCBD5E1)

    /** Fechas y ayudas (--muted). */
    val TextMuted = Color(0xFF94A3B8)

    // Acción
    /** Lo que se toca (--primary). */
    val Primary = Color(0xFF38BDF8)

    /** Texto y dibujo sobre el azul de acción (--on-primary). */
    val OnPrimary = Color(0xFF07111F)

    // Adorno: nunca botones
    val Cyan = Color(0xFF22D3EE)
    val Violet = Color(0xFF818CF8)
    val Purple = Color(0xFFA855F7)

    // Estados: siempre con ícono y palabra
    /** Hecho, aprobado, entregado (--ok). */
    val Ok = Color(0xFF34D399)
    val OkBackground = Color(0xFF064E3B)
    val OkLine = Color(0xFF065F46)

    /** Fondo y borde del aviso verde de «salió bien». */
    val OkNotice = Color(0xFF052E16)
    val OkNoticeLine = Color(0xFF10B981)

    /** Pendiente, en proceso, por vencer (--warn). */
    val Warn = Color(0xFFFBBF24)
    val WarnBackground = Color(0xFF451A03)
    val WarnLine = Color(0xFF78350F)

    /** Error, rechazado, vencido (--bad). */
    val Bad = Color(0xFFF87171)
    val BadBackground = Color(0xFF450A0A)
    val BadLine = Color(0xFF7F1D1D)

    /** Borde del aviso rojo de error y punto de «grabando». */
    val BadNoticeLine = Color(0xFFEF4444)

    // Visor de fotos y videos
    /** Fondo de los botones que van encima de una foto o un video. */
    val Scrim = Color(0x99000000)

    /** Círculo del botón «reproducir» encima de un video. */
    val Overlay = Color(0xBF07111F)
}
