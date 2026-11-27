package com.dracknoval.domux

import org.junit.Assert.assertEquals
import org.junit.Test

/** El escáner único de la portería reconoce de qué es cada código. */
class CodigoEscaneadoTest {
    @Test
    fun el_codigo_de_entrega_es_de_un_paquete() {
        assertEquals(ScannedCode.PACKAGE, scannedCodeKind("DOMUX-PKG:abc123"))
    }

    @Test
    fun el_qr_de_visitas_es_de_una_visita() {
        assertEquals(ScannedCode.VISIT, scannedCodeKind("DOMUX:xyz789"))
    }

    @Test
    fun otros_codigos_o_vacios_no_sirven() {
        assertEquals(ScannedCode.UNKNOWN, scannedCodeKind("https://ejemplo.com"))
        assertEquals(ScannedCode.UNKNOWN, scannedCodeKind("DOMUX:"))
        assertEquals(ScannedCode.UNKNOWN, scannedCodeKind("DOMUX-PKG:"))
    }
}
