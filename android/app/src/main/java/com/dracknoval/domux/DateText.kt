package com.dracknoval.domux

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/*
 * Fechas de la app. El servidor guarda los días como AAAA-MM-DD y los cuenta con la hora de
 * Colombia; aquí se hace lo mismo para que "hoy" sea el mismo día en los dos lados.
 */

private const val COLOMBIA_ZONE = "America/Bogota"

private fun isoFormat(zone: String): SimpleDateFormat =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).apply {
        timeZone = TimeZone.getTimeZone(zone)
        isLenient = false
    }

/** Hoy en Colombia, como AAAA-MM-DD. */
fun colombiaToday(): String = isoFormat(COLOMBIA_ZONE).format(Date())

/** Suma (o resta, si es negativo) días a una fecha AAAA-MM-DD; si la fecha no se entiende, la devuelve igual. */
fun addDaysIso(iso: String, days: Int): String {
    val format = isoFormat("UTC")
    return try {
        val base = format.parse(iso) ?: return iso
        val calendar = Calendar.getInstance(TimeZone.getTimeZone("UTC")).apply {
            time = base
            add(Calendar.DAY_OF_MONTH, days)
        }
        format.format(calendar.time)
    } catch (_: Exception) {
        iso
    }
}

/** La fecha como se escribe en Colombia: 2026-11-20 pasa a 20/11/2026. */
fun humanDate(iso: String?): String {
    if (iso.isNullOrBlank()) return ""
    val parts = iso.take(10).split("-")
    if (parts.size != 3) return iso
    return "${parts[2]}/${parts[1]}/${parts[0]}"
}

/** "1 día" o "3 días". */
fun daysText(days: Int): String = if (days == 1) "1 día" else "$days días"

/** "1 día hábil" o "3 días hábiles": los plazos de las PQRS no cuentan fines de semana ni festivos. */
fun businessDaysText(days: Int): String = if (days == 1) "1 día hábil" else "$days días hábiles"

/**
 * El día (AAAA-MM-DD) que representa una marca de tiempo en UTC a medianoche, que es como el
 * calendario de Material entrega los días que se eligen.
 */
fun isoFromUtcMillis(utcMillis: Long): String = isoFormat("UTC").format(Date(utcMillis))

/** La marca de tiempo en UTC (medianoche) de un día AAAA-MM-DD; null si el texto no es una fecha válida. */
fun utcMillisFromIso(iso: String): Long? = try {
    isoFormat("UTC").parse(iso)?.time
} catch (_: Exception) {
    null
}

/** El mes de una fecha, como AAAA-MM: sirve para reconocer los días de un mes. */
fun monthPrefix(year: Int, month: Int): String = String.format(Locale.US, "%04d-%02d", year, month)

private val weekdayNames = listOf("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

/** Nombre del día de la semana, contando desde 0 = lunes, igual que el servidor. */
fun weekdayName(weekday: Int): String = weekdayNames.getOrElse(weekday) { "" }

/** El día de la semana en plural, para «los lunes», «los sábados». */
fun weekdayPlural(weekday: Int): String {
    val name = weekdayName(weekday)
    return if (name.endsWith("s")) name else name + "s"
}

/** "2 horas", "1 hora" o "45 minutos": cuánto dura cada franja de una zona común. */
fun slotLengthText(minutes: Int): String = when {
    minutes <= 0 -> ""
    minutes == 60 -> "1 hora"
    minutes % 60 == 0 -> "${minutes / 60} horas"
    else -> "$minutes minutos"
}
