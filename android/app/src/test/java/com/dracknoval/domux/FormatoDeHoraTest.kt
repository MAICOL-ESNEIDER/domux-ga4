package com.dracknoval.domux

import org.junit.Assert.assertEquals
import org.junit.Test

/** Las horas se muestran con a. m. / p. m. o en 24 horas, según la preferencia. */
class FormatoDeHoraTest {
    @Test
    fun doce_horas() {
        assertEquals("2:30 p. m.", clockText("14:30", use24 = false))
        assertEquals("12:05 a. m.", clockText("00:05", use24 = false))
        assertEquals("12:00 p. m.", clockText("12:00", use24 = false))
        assertEquals("20/11/2026 9:15 a. m.", whenText("2026-11-20 09:15", use24 = false))
        assertEquals("8:00 a. m. a 10:00 a. m.", whenText("08:00-10:00", use24 = false))
    }

    @Test
    fun veinticuatro_horas() {
        assertEquals("14:30", clockText("14:30", use24 = true))
        assertEquals("20/11/2026 21:00", whenText("2026-11-20 21:00", use24 = true))
    }

    @Test
    fun lo_que_no_es_una_hora_queda_igual() {
        assertEquals("Todo el día", whenText("Todo el día", use24 = false))
        assertEquals("", whenText(null))
    }
}

/** Cada rol ve los documentos legales que le tocan. */
class DocumentosPorRolTest {
    private fun doc(slug: String, audience: List<String>?) =
        com.dracknoval.domux.data.LegalDocumentSummary(slug, slug, "", "vigente", "0.1", null, audience)

    private val all = listOf(
        doc("terminos", listOf("RESIDENT", "GUARD", "ADMIN")),
        doc("compromiso-porteria", listOf("GUARD")),
        doc("compromiso-administracion", listOf("ADMIN")),
        doc("viejo", null)
    )

    @Test
    fun la_porteria_ve_su_compromiso() {
        assertEquals(listOf("terminos", "compromiso-porteria", "viejo"), forCurrentRole(all, "GUARD").map { it.slug })
    }

    @Test
    fun el_residente_no_ve_los_compromisos() {
        assertEquals(listOf("terminos", "viejo"), forCurrentRole(all, "RESIDENT").map { it.slug })
    }

    @Test
    fun sin_sesion_se_ven_todos() {
        assertEquals(4, forCurrentRole(all, null).size)
    }
}
