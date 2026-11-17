package com.dracknoval.domux.pantallas

import com.dracknoval.domux.data.DocumentOption
import com.dracknoval.domux.data.UnitDocument
import com.dracknoval.domux.documentCountText
import com.dracknoval.domux.fileSizeText
import com.dracknoval.domux.groupDocuments
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Los textos y el orden de la pantalla de Documentos (DEC-032), sin dibujar nada: cómo se agrupan por
 * tipo, cómo se escribe el tamaño de un archivo y cuántos documentos hay.
 */
class DocumentosDeLaUnidadTest {

    private val tipos = listOf(
        DocumentOption("convivencia", "Manual de convivencia"),
        DocumentOption("reglas", "Reglas de la unidad"),
        DocumentOption("presupuesto", "Presupuestos aprobados"),
        DocumentOption("otro", "Otros")
    )

    private fun documento(id: Int, tipo: String?, etiqueta: String? = null) =
        UnitDocument(id = id, title = "Documento $id", category = tipo, categoryLabel = etiqueta)

    // --- Agrupar por tipo ---

    @Test
    fun los_documentos_salen_agrupados_en_el_orden_de_los_tipos_del_servidor() {
        val grupos = groupDocuments(
            listOf(
                documento(1, "otro"), documento(2, "presupuesto"), documento(3, "convivencia"),
                documento(4, "presupuesto"), documento(5, "reglas")
            ),
            tipos
        )

        assertEquals(
            listOf("Manual de convivencia", "Reglas de la unidad", "Presupuestos aprobados", "Otros"),
            grupos.map { it.first }
        )
        // Dentro de cada tipo se conserva el orden en que llegaron (los más nuevos primero).
        assertEquals(listOf(2, 4), grupos[2].second.map { it.id })
    }

    @Test
    fun solo_salen_los_tipos_que_tienen_documentos() {
        val grupos = groupDocuments(listOf(documento(1, "reglas")), tipos)

        assertEquals(listOf("Reglas de la unidad"), grupos.map { it.first })
    }

    @Test
    fun un_documento_sin_tipo_va_a_otros() {
        val grupos = groupDocuments(listOf(documento(1, null)), tipos)

        assertEquals(listOf("Otros"), grupos.map { it.first })
    }

    @Test
    fun un_tipo_que_el_servidor_no_conoce_va_al_final_con_su_propio_nombre() {
        val grupos = groupDocuments(
            listOf(documento(1, "inventado", "Tipo nuevo"), documento(2, "convivencia")),
            tipos
        )

        assertEquals(listOf("Manual de convivencia", "Tipo nuevo"), grupos.map { it.first })
    }

    @Test
    fun sin_la_lista_de_tipos_los_documentos_se_agrupan_por_su_propio_nombre_de_tipo() {
        val grupos = groupDocuments(listOf(documento(1, "reglas", "Reglas de la unidad")), emptyList())

        assertEquals(listOf("Reglas de la unidad"), grupos.map { it.first })
    }

    @Test
    fun una_lista_vacia_no_tiene_grupos() {
        assertEquals(emptyList<Pair<String, List<UnitDocument>>>(), groupDocuments(emptyList(), tipos))
    }

    // --- Textos ---

    @Test
    fun el_tamano_se_escribe_en_kb_o_en_mb_con_coma() {
        assertEquals("1 KB", fileSizeText(200))
        assertEquals("340 KB", fileSizeText(340 * 1024))
        assertEquals("1,2 MB", fileSizeText((1.2 * 1024 * 1024).toInt()))
        assertEquals("6,0 MB", fileSizeText(6 * 1024 * 1024))
    }

    @Test
    fun un_tamano_desconocido_no_escribe_nada() {
        assertEquals("", fileSizeText(0))
        assertEquals("", fileSizeText(-5))
    }

    @Test
    fun el_conteo_distingue_uno_de_varios() {
        assertEquals("1 documento", documentCountText(1))
        assertEquals("5 documentos", documentCountText(5))
    }
}
