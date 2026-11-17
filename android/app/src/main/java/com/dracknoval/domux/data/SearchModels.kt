// SearchModels.kt — Lo que responde el buscador general del servidor, GET /api/search (HU-089).
// Los nombres son los mismos del contrato de la API (docs/api/openapi.yaml: SearchResponse).

package com.dracknoval.domux.data

import com.google.gson.annotations.SerializedName

/** Una opción del filtro «Buscar en»: [value] es lo que se manda al servidor y [label] lo que se lee. */
data class SearchPlace(val value: String, val label: String)

/**
 * Un resultado, ya con el texto que se muestra. [id] es el del registro en su propia lista y
 * [apartmentLabel] es el apartamento escrito como «Torre 1 · Apto 101» (puede venir vacío).
 * [kind] solo viene en los vehículos: «residente» o «visitante».
 */
data class SearchResult(
    val type: String,
    val id: Int,
    val title: String,
    val subtitle: String?,
    val apartmentId: Int?,
    val apartmentLabel: String?,
    val kind: String?
)

/** Los resultados de un tipo; [more] dice si había más de los que se muestran. */
data class SearchGroup(
    val type: String,
    val label: String,
    val items: List<SearchResult>?,
    val more: Boolean?
)

/**
 * La respuesta completa. [place] es dónde se buscó (en el contrato se llama «in», que en Kotlin es
 * una palabra reservada), [places] las opciones del filtro que tiene este rol y [tooShort] avisa
 * que el texto era muy corto y no se buscó nada.
 */
data class SearchResponse(
    val query: String?,
    @SerializedName("in") val place: String?,
    val places: List<SearchPlace>?,
    val tooShort: Boolean?,
    val groups: List<SearchGroup>?
)
