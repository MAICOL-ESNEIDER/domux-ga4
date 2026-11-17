package com.dracknoval.domux.pantallas

import com.dracknoval.domux.data.*
import com.dracknoval.domux.defaultSearchPlaces
import com.google.gson.Gson
import retrofit2.Response
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Method
import java.lang.reflect.ParameterizedType
import java.lang.reflect.Proxy
import java.lang.reflect.WildcardType

/**
 * Una conexión «de mentira» con el servidor para las pruebas de pantallas: contesta al instante con
 * datos de ejemplo (la unidad inventada «Altos de DOMUX») y nunca sale a internet.
 *
 * Cada llamada de [ApiService] y de [StructureApiService] devuelve el dato que se arma aquí según su
 * nombre. Lo que todavía no tiene dato de ejemplo contesta «vacío» (sin errores), para que la
 * pantalla se dibuje igual. Los datos respetan el rol de la sesión: un residente solo ve lo suyo,
 * como en el servidor de verdad. Las fechas son fijas y están escritas como las manda el servidor
 * («2026-11-20 10:05», hora de Colombia): así las fotos no cambian de un día a otro.
 */
object DatosDeMentira {

    fun api(): ApiService = falso(ApiService::class.java) { metodo, argumentos -> cuerpoPara(metodo, argumentos) }

    fun estructura(): StructureApiService =
        falso(StructureApiService::class.java) { metodo, argumentos -> cuerpoDeEstructura(metodo, argumentos) }

    private fun <T : Any> falso(clase: Class<T>, responder: (Method, Array<out Any?>) -> Any?): T {
        @Suppress("UNCHECKED_CAST")
        return Proxy.newProxyInstance(
            clase.classLoader,
            arrayOf(clase),
            InvocationHandler { proxy, metodo, argumentos ->
                val seguros: Array<out Any?> = argumentos ?: emptyArray<Any?>()
                when (metodo.name) {
                    "toString" -> "Conexión de mentira (${clase.simpleName})"
                    "hashCode" -> System.identityHashCode(proxy)
                    "equals" -> proxy === seguros.firstOrNull()
                    else -> Response.success(responder(metodo, seguros))
                }
            }
        ) as T
    }

    // --- Lo que contesta cada llamada --------------------------------------------------------

    private fun cuerpoPara(metodo: Method, a: Array<out Any?>): Any? = when (metodo.name) {
        "getComplexInfo" -> ComplexInfoResponse(unidad())
        "getNotifications" -> NotificationsListResponse(notificaciones())
        "getAdminSummary" -> resumenDeAdministracion()
        // getVisitsSummary(auth, status, dateFrom, inside, pageSize, view)
        "getVisitsSummary" -> {
            val lista = misVisitas().filter { visita ->
                if (a.getOrNull(3) == "true") dentro(visita) else visita.approvalStatus == "pendiente"
            }
            VisitsListResponse(lista, total = lista.size)
        }
        "getPackagesSummary" -> {
            val lista = misPaquetes().filter { it.status == "pendiente" }
            PackagesListResponse(lista, total = lista.size)
        }
        "getAnnouncementsSummary" -> AnnouncementsListResponse(comunicados(), total = 3, unreadCount = 2)
        "getReservationsSummary" -> ReservationsListResponse(misReservas().filter { it.status != "rechazada" })
        // search(auth, text, place)
        "search" -> busqueda(a.getOrNull(1) as? String ?: "", a.getOrNull(2) as? String)

        // Usuarios, perfiles y unidades
        "getUsers" -> {
            val texto = (a.getOrNull(3) as? String).orEmpty().trim().lowercase()
            val rol = (a.getOrNull(4) as? String).orEmpty()
            val lista = usuarios().filter { usuario ->
                (rol.isEmpty() || usuario.role == rol) &&
                    (texto.isEmpty() || (usuario.fullName.orEmpty() + " " + usuario.email).lowercase().contains(texto))
            }
            UsersListResponse(lista, page = 1, pageSize = 25, total = lista.size, totalPages = 1)
        }
        "getProfile", "currentSession" -> UserDataResponse(user = usuarios().first { it.id == (Session.userId ?: 6) })
        "getMyUnit", "getUnit" -> ResidentialUnitResponse(unidad101())
        "getResidents" -> {
            val id = a.getOrNull(2) as? Int
            val texto = (a.getOrNull(1) as? String).orEmpty().trim().lowercase()
            val lista = residentes().filter { residente ->
                (id == null || residente.id == id) &&
                    (texto.isEmpty() || (residente.name + " " + residente.apartment.orEmpty()).lowercase().contains(texto))
            }
            ResidentsListResponse(lista, more = false)
        }
        "getResidentContact" -> ResidentContactResponse(residentes().first { it.id == (a.getOrNull(1) as? Int ?: 6) })
        "getGuards" -> GuardsListResponse(listOf(GuardOption(2, "Guardia Principal"), GuardOption(3, "Guardia Nocturno")))

        // Comunicados, PQRS y reservas
        "getAnnouncements" -> AnnouncementsListResponse(comunicados(), total = 3, unreadCount = 2)
        "getPqrs" -> {
            val estado = (a.getOrNull(1) as? String).orEmpty()
            val categoria = (a.getOrNull(2) as? String).orEmpty()
            val texto = (a.getOrNull(3) as? String).orEmpty().trim().lowercase()
            val residente = a.getOrNull(4) as? Int
            PqrsListResponse(
                misPqrs().filter { pqrs ->
                    (estado.isEmpty() || pqrs.status == estado) &&
                        (categoria.isEmpty() || pqrs.category == categoria) &&
                        (residente == null || pqrs.residentId == residente) &&
                        (texto.isEmpty() || (pqrs.subject + " " + pqrs.residentName.orEmpty()).lowercase().contains(texto))
                }
            )
        }
        "getCommonAreas" -> CommonAreasListResponse(zonasComunes())
        "getReservations" -> ReservationsListResponse(misReservas())
        "getReservationAvailability" -> ReservationAvailabilityResponse(
            commonAreaId = a.getOrNull(1) as? Int ?: 1,
            date = a.getOrNull(2) as? String ?: "2026-11-24",
            availableSlots = listOf("08:00-12:00", "12:00-16:00", "16:00-20:00"),
            occupiedSlots = listOf("20:00-22:00"),
            slotMinutes = 240
        )
        "getReservationCalendar" -> ReservationCalendarResponse(
            commonAreaId = a.getOrNull(1) as? Int ?: 1,
            year = a.getOrNull(2) as? Int ?: 2026,
            month = a.getOrNull(3) as? Int ?: 11,
            blockedDates = listOf("2026-11-21", "2026-11-28"),
            closedDates = listOf("2026-11-30")
        )

        // Portería: paquetes, visitas y vehículos
        "getPackages" -> {
            val estado = (a.getOrNull(1) as? String).orEmpty()
            val lista = misPaquetes().filter { estado.isEmpty() || it.status == estado }
            PackagesListResponse(lista, total = lista.size)
        }
        "getVisits" -> {
            val estado = (a.getOrNull(2) as? String).orEmpty()
            val adentro = a.getOrNull(6) == "true"
            val lista = misVisitas().filter { visita ->
                (estado.isEmpty() || visita.approvalStatus == estado) && (!adentro || dentro(visita))
            }
            VisitsListResponse(lista, page = 1, pageSize = 50, total = lista.size, totalPages = 1)
        }
        "getVisitQrPasses" -> VisitQrPassListResponse(pasesQr())
        "getVisitorSpots" -> tableroDeVisitantes()
        "getVehicleEntries" -> {
            val adentro = a.getOrNull(1) == "true"
            val lista = entradasDeVehiculos().filter { !adentro || it.isInside }
            VehicleEntriesListResponse(lista, page = 1, pageSize = 25, total = lista.size, totalPages = 1)
        }
        "searchResidentVehicles" -> ResidentVehiclesResponse(vehiculosDeResidentes())

        // Textos legales
        "getLegalDocuments" -> LegalDocumentsResponse(documentosLegales())
        "getLegalDocument" -> documentoLegal(a.getOrNull(0) as? String ?: "")
        else -> cuerpoVacio(metodo)
    }

    private fun cuerpoDeEstructura(metodo: Method, a: Array<out Any?>): Any? = when (metodo.name) {
        "getTowers" -> TowersResponse(torres())
        "getApartments" -> {
            val torre = a.getOrNull(1) as? Int
            val texto = (a.getOrNull(2) as? String).orEmpty().trim().lowercase()
            val lista = apartamentos().filter { apto ->
                (torre == null || apto.towerId == torre) && (texto.isEmpty() || apto.label.lowercase().contains(texto))
            }
            ApartmentsResponse(lista, page = 1, pageSize = 50, total = lista.size, totalPages = 1)
        }
        "getParkingSpots" -> {
            val tipo = (a.getOrNull(1) as? String).orEmpty()
            val lista = parqueaderos().filter { tipo.isEmpty() || it.type == tipo }
            ParkingSpotsResponse(lista, page = 1, pageSize = 50, total = lista.size, totalPages = 1)
        }
        "getStorageRooms" -> StorageRoomsResponse(depositos(), page = 1, pageSize = 50, total = depositos().size, totalPages = 1)
        else -> cuerpoVacio(metodo)
    }

    /**
     * Lo que contesta una llamada que todavía no tiene dato de ejemplo: un objeto «vacío» del tipo
     * que la llamada espera (o nada, si no se puede armar). En una función «suspend» el último
     * parámetro es la continuación, y ahí está escrito el tipo de la respuesta.
     */
    private fun cuerpoVacio(metodo: Method): Any? {
        val continuacion = metodo.genericParameterTypes.lastOrNull() as? ParameterizedType ?: return null
        val argumento = continuacion.actualTypeArguments.firstOrNull() ?: return null
        val respuesta = (argumento as? WildcardType)?.lowerBounds?.firstOrNull() ?: argumento
        val tipoDelCuerpo = (respuesta as? ParameterizedType)?.actualTypeArguments?.firstOrNull() ?: return null
        return try {
            Gson().fromJson<Any?>("{}", tipoDelCuerpo)
        } catch (_: Exception) {
            null
        }
    }

    // --- Quién ve qué ---------------------------------------------------------------------------

    private val esResidente: Boolean get() = Session.role == "RESIDENT"
    private val miId: Int get() = Session.userId ?: 6

    private fun misVisitas() = visitas().filter { !esResidente || it.residentId == miId }
    private fun misPaquetes() = paquetes().filter { !esResidente || it.residentId == miId }
    private fun misReservas() = reservas().filter { !esResidente || it.residentId == miId }
    private fun misPqrs() = pqrsLista().filter { !esResidente || it.residentId == miId }
    private fun dentro(visita: Visit) = visita.enteredAt != null && visita.exitedAt == null

    // --- La unidad inventada «Altos de DOMUX» ---------------------------------------------------

    private fun unidad() = ComplexInfo(
        name = "Altos de DOMUX",
        address = "Calle 10 # 20-30, Medellín",
        portalPhone = "604 555 0100"
    )

    private fun residente(
        id: Int, nombre: String, apellido: String, apto: String, aptoId: Int, tipo: String, edad: Int
    ) = UserData(
        id = id, name = nombre, email = nombre.lowercase().replace("í", "i").replace("á", "a") + "@domux.com",
        role = "RESIDENT", apartment = apto, lastName = apellido, fullName = "$nombre $apellido",
        phone = "31000000" + id.toString().padStart(2, '0'), documentId = "100000" + id.toString().padStart(2, '0'),
        occupancyType = tipo, createdAt = "2026-09-02 10:00", dataProcessingConsent = true,
        apartmentId = aptoId, age = edad
    )

    private fun usuarios() = listOf(
        UserData(
            id = 1, name = "Administración", email = "admin@domux.com", role = "ADMIN", apartment = null,
            lastName = "Domux", fullName = "Administración Domux", phone = "3000000001", documentId = "9000000001",
            occupancyType = null, createdAt = "2026-09-01 08:00", dataProcessingConsent = true
        ),
        UserData(
            id = 2, name = "Guardia", email = "guardia@domux.com", role = "GUARD", apartment = null,
            lastName = "Principal", fullName = "Guardia Principal", phone = "3000000002", documentId = "1000000002",
            occupancyType = null, createdAt = "2026-09-01 08:05", dataProcessingConsent = true, hasPin = true
        ),
        UserData(
            id = 3, name = "Guardia", email = "nocturno@domux.com", role = "GUARD", apartment = null,
            lastName = "Nocturno", fullName = "Guardia Nocturno", phone = "3000000003", documentId = "1000000003",
            occupancyType = null, createdAt = "2026-09-01 08:10", dataProcessingConsent = true, hasPin = false
        ),
        residente(6, "María", "Gómez", "Torre 1 · Apto 101", 1, "propietario", 38),
        residente(7, "Gustavo", "Restrepo Arango", "Torre 1 · Apto 201", 3, "propietario", 52),
        residente(8, "Diana", "Ríos Zapata", "Torre 2 · Apto 202", 8, "arrendatario", 29),
        residente(9, "Carlos", "Pérez", "Torre 2 · Apto 202", 8, "propietario", 41),
        residente(10, "Natalia", "Correa Giraldo", "Torre 2 · Apto 101", 5, "propietario", 45),
        residente(17, "Mariana", "Ruiz Cano", "Torre 2 · Apto 301", 9, "arrendatario", 27)
    )

    private fun residentes() = usuarios().filter { it.role == "RESIDENT" }.map { usuario ->
        ResidentSummary(
            id = usuario.id, name = usuario.fullName.orEmpty(), apartment = usuario.apartment,
            email = usuario.email, phone = usuario.phone, occupancyType = usuario.occupancyType, age = usuario.age
        )
    }

    private fun unidad101() = ResidentialUnitData(
        id = 1, apartment = "Torre 1 · Apto 101",
        residents = listOf(UnitResidentData(6, "María Gómez", "propietario")),
        parkingIdentifier = "P-101", storageIdentifier = "D-12",
        petInsurance = true, petInsurer = "Seguros del Valle",
        members = listOf(
            HouseholdMemberData(
                id = 1, name = "Sofía", lastName = "Gómez", documentId = "1000000020", birthDate = "2014-03-02",
                relationship = "hija"
            ),
            HouseholdMemberData(
                id = 2, name = "Andrés", lastName = "Londoño", documentId = "1000000021", birthDate = "1985-07-19",
                phone = "3100000021", relationship = "conyuge_pareja"
            )
        ),
        pets = listOf(
            PetData(
                id = 1, name = "Max", species = "Perro", breed = "Labrador", ageYears = 4,
                vaccinesUpToDate = true, lastVaccinationDate = "2026-08-10",
                dewormingUpToDate = true, lastDewormingDate = "2026-09-15"
            )
        ),
        vehicles = listOf(
            VehicleData(
                id = 1, plate = "MAR123", type = "carro", makeModel = "Mazda 3", year = 2021,
                registeredOwner = "María Gómez", color = "Rojo"
            ),
            VehicleData(
                id = 2, plate = "XYZ45F", type = "moto", makeModel = "Yamaha FZ", year = 2022,
                registeredOwner = "Andrés Londoño", color = "Negro"
            )
        )
    )

    private fun notificaciones() = listOf(
        NotificationItem(
            id = 1, userId = 1, title = "Reserva aprobada",
            message = "Tu reserva del Salón social para el 21/11/2026 fue aprobada.",
            type = "reserva", isRead = false, createdAt = "2026-11-19 09:30"
        ),
        NotificationItem(
            id = 2, userId = 1, title = "Paquete en portería",
            message = "Llegó un paquete de Servientrega a tu nombre.",
            type = "paquete", isRead = false, createdAt = "2026-11-18 16:10"
        ),
        NotificationItem(
            id = 3, userId = 1, title = "Comunicado nuevo",
            message = "Corte de agua el sábado 21/11 de 8:00 a 12:00.",
            type = "comunicado", isRead = true, createdAt = "2026-11-17 08:00"
        )
    )

    private fun resumenDeAdministracion() = AdminSummaryResponse(
        counts = AdminSummaryCounts(
            pqrsOpen = 7, pqrsOverdue = 2, pqrsDueSoon = 3,
            reservationsPending = 4, packagesOver48 = 3, packagesOver72 = 1, unreadNotifications = 2
        ),
        urgentPqrs = listOf(
            AdminUrgentPqrs(
                id = 12, radicado = "PQRS-2026-000012", subject = "Ruido en la torre 2 después de las 10 p. m.",
                category = "Queja", residentName = "Carlos Pérez", apartment = "Torre 2 · Apto 202",
                semaphore = "rojo", daysRemaining = -1
            ),
            AdminUrgentPqrs(
                id = 15, radicado = "PQRS-2026-000015", subject = "Bombillo dañado en el pasillo del piso 2",
                category = "Petición", residentName = "Gustavo Restrepo Arango", apartment = "Torre 1 · Apto 201",
                semaphore = "amarillo", daysRemaining = 2
            )
        ),
        pendingReservations = listOf(
            AdminPendingReservation(
                id = 42, commonAreaName = "Piscina", date = "2026-11-23", timeSlot = "10:00-12:00",
                attendees = 6, residentName = "Diana Ríos Zapata", apartment = "Torre 2 · Apto 202"
            ),
            AdminPendingReservation(
                id = 43, commonAreaName = "Salón social", date = "2026-11-28", timeSlot = "14:00-18:00",
                attendees = 25, residentName = "Natalia Correa Giraldo", apartment = "Torre 2 · Apto 101"
            )
        )
    )

    // --- Portería -------------------------------------------------------------------------------

    private fun visitas() = listOf(
        Visit(
            id = 11, visitorName = "Laura Restrepo", type = "visitante", createdAt = "2026-11-20 10:05",
            residentName = "María Gómez", registeredByName = "Guardia Principal", residentId = 6,
            apartment = "Torre 1 · Apto 101", visitorDocument = "1000000031", expectedStayMinutes = 120
        ),
        Visit(
            id = 12, visitorName = "Andrés Ocampo (Rappi)", type = "domiciliario", createdAt = "2026-11-20 10:20",
            residentName = "María Gómez", registeredByName = "Guardia Principal", residentId = 6,
            apartment = "Torre 1 · Apto 101", documentRefused = true
        ),
        Visit(
            id = 13, visitorName = "Carlos Vélez", type = "contratista", createdAt = "2026-11-20 08:30",
            residentName = "Carlos Pérez", registeredByName = "Guardia Principal", residentId = 9,
            apartment = "Torre 2 · Apto 202", visitorDocument = "1000000032", approvalStatus = "aprobada",
            authorizationMethod = "app", enteredAt = "2026-11-20 08:40", expectedStayMinutes = 180, insideMinutes = 95
        ),
        Visit(
            id = 14, visitorName = "Juliana Marín", type = "visitante", createdAt = "2026-11-20 09:00",
            residentName = "Gustavo Restrepo Arango", registeredByName = "Guardia Principal", residentId = 7,
            apartment = "Torre 1 · Apto 201", visitorDocument = "1000000033", approvalStatus = "aprobada",
            authorizationMethod = "llamada", enteredAt = "2026-11-20 09:10", exitedAt = "2026-11-20 09:55"
        ),
        Visit(
            id = 15, visitorName = "Pedro Salazar", type = "visitante", createdAt = "2026-11-19 17:30",
            residentName = "Diana Ríos Zapata", registeredByName = "Guardia Nocturno", residentId = 8,
            apartment = "Torre 2 · Apto 202", visitorDocument = "1000000034", approvalStatus = "rechazada"
        ),
        Visit(
            id = 16, visitorName = "Camila Torres", type = "visitante", createdAt = "2026-11-20 11:00",
            residentName = "María Gómez", registeredByName = "Guardia Principal", residentId = 6,
            apartment = "Torre 1 · Apto 101", visitorDocument = "1000000035", approvalStatus = "aprobada",
            authorizationMethod = "qr", enteredAt = "2026-11-20 11:02", qrPassId = 1, expectedStayMinutes = 240,
            insideMinutes = 30
        )
    )

    private fun paquetes() = listOf(
        PackageItem(
            id = 31, description = "Caja mediana", status = "pendiente", createdAt = "2026-11-18 16:10",
            deliveredAt = null, residentName = "María Gómez", registeredByName = "Guardia Principal",
            residentId = 6, apartment = "Torre 1 · Apto 101", carrier = "Servientrega",
            trackingNumber = "SV-100234", arrivedAt = "2026-11-18 16:10", hoursWaiting = 50, claimAlert = "naranja"
        ),
        PackageItem(
            id = 32, description = "Sobre de documentos", status = "pendiente", createdAt = "2026-11-20 09:00",
            deliveredAt = null, residentName = "María Gómez", registeredByName = "Guardia Principal",
            residentId = 6, apartment = "Torre 1 · Apto 101", carrier = "Coordinadora",
            trackingNumber = "CO-558120", arrivedAt = "2026-11-20 09:00", hoursWaiting = 6
        ),
        PackageItem(
            id = 33, description = "Caja grande", status = "pendiente", createdAt = "2026-11-17 14:00",
            deliveredAt = null, residentName = "Diana Ríos Zapata", registeredByName = "Guardia Nocturno",
            residentId = 8, apartment = "Torre 2 · Apto 202", carrier = "Interrapidísimo",
            trackingNumber = "IR-778201", arrivedAt = "2026-11-17 14:00", hoursWaiting = 76, claimAlert = "rojo"
        ),
        PackageItem(
            id = 30, description = "Bolsa de mercado", status = "entregado", createdAt = "2026-11-19 12:00",
            deliveredAt = "2026-11-19 18:20", residentName = "María Gómez", registeredByName = "Guardia Principal",
            residentId = 6, apartment = "Torre 1 · Apto 101", carrier = "Rappi", deliveredTo = "María Gómez",
            arrivedAt = "2026-11-19 12:00"
        )
    )

    private fun pasesQr() = listOf(
        VisitQrPass(
            id = 1, residentId = 6, validFrom = "2026-11-20 08:00", validUntil = "2026-11-20 20:00",
            maxPeople = 4, registeredPeople = 1, remainingPeople = 3, revoked = false,
            token = "demo-token-1", qrData = "DOMUX-DEMO-QR-1", visitorNames = listOf("Camila Torres", "Laura Restrepo")
        )
    )

    private fun tableroDeVisitantes() = VisitorBoardResponse(
        spots = listOf(
            VisitorSpotItem(
                id = 1, code = "V-01", location = "Sótano 1", isOccupied = true,
                entry = entradaDeVehiculo(1, "KLM456", "Carlos Vélez", "Carlos Pérez", "Torre 2 · Apto 202", 1, "V-01")
            ),
            VisitorSpotItem(id = 2, code = "V-02", location = "Sótano 1", isOccupied = false),
            VisitorSpotItem(id = 3, code = "V-03", location = "Sótano 1", isOccupied = false),
            VisitorSpotItem(
                id = 4, code = "V-04", location = "Sótano 2", isOccupied = true,
                entry = entradaDeVehiculo(2, "QRS789", "Camila Torres", "María Gómez", "Torre 1 · Apto 101", 4, "V-04")
            )
        ),
        total = 4, free = 2, occupied = 2, suggestedSpotId = 2, withoutSpot = emptyList(), overdue = 0, maxDays = 3
    )

    private fun entradaDeVehiculo(
        id: Int, placa: String, visitante: String, residente: String, apto: String, puesto: Int, codigo: String
    ) = VisitorVehicleEntryData(
        id = id, plate = placa, visitId = 13, visitorName = visitante, residentName = residente,
        apartment = apto, spotId = puesto, spotCode = codigo, spotLocation = "Sótano 1",
        enteredAt = "2026-11-20 08:45", isInside = true, parkedMinutes = 120, maxDays = 3,
        registeredByName = "Guardia Principal"
    )

    private fun entradasDeVehiculos() = listOf(
        entradaDeVehiculo(1, "KLM456", "Carlos Vélez", "Carlos Pérez", "Torre 2 · Apto 202", 1, "V-01"),
        entradaDeVehiculo(2, "QRS789", "Camila Torres", "María Gómez", "Torre 1 · Apto 101", 4, "V-04"),
        VisitorVehicleEntryData(
            id = 3, plate = "TUV321", visitId = 14, visitorName = "Juliana Marín",
            residentName = "Gustavo Restrepo Arango", apartment = "Torre 1 · Apto 201", spotCode = "V-02",
            spotLocation = "Sótano 1", enteredAt = "2026-11-20 09:10", exitedAt = "2026-11-20 09:55",
            isInside = false, parkedMinutes = 45, registeredByName = "Guardia Principal", exitedByName = "Guardia Principal"
        )
    )

    private fun vehiculosDeResidentes() = listOf(
        ResidentVehicleItem(
            id = 7, plate = "MAR123", type = "carro", makeModel = "Mazda 3", year = 2021,
            registeredOwner = "María Gómez", color = "Rojo", apartmentId = 1, apartment = "Torre 1 · Apto 101",
            isInside = true, lastMovementType = "entrada", lastMovementAt = "2026-11-20 07:50"
        ),
        ResidentVehicleItem(
            id = 8, plate = "XYZ45F", type = "moto", makeModel = "Yamaha FZ", year = 2022,
            registeredOwner = "Andrés Londoño", color = "Negro", apartmentId = 1, apartment = "Torre 1 · Apto 101",
            isInside = false, lastMovementType = "salida", lastMovementAt = "2026-11-20 06:30"
        ),
        ResidentVehicleItem(
            id = 9, plate = "DEF456", type = "carro", makeModel = "Renault Duster", year = 2019,
            registeredOwner = "Carlos Pérez", color = "Gris", apartmentId = 8, apartment = "Torre 2 · Apto 202",
            isInside = true, lastMovementType = "entrada", lastMovementAt = "2026-11-19 22:10"
        )
    )

    // --- Comunicados, PQRS y reservas ------------------------------------------------------------

    private fun comunicados() = listOf(
        Announcement(
            id = 21, title = "Corte de agua el sábado",
            message = "El sábado 21 de noviembre no habrá agua de 8:00 a 12:00 por el lavado de los tanques.",
            createdAt = "2026-11-17 08:00", authorName = "Administración Domux",
            category = "mantenimiento", categoryLabel = "Mantenimiento", readApartments = 6, totalApartments = 10
        ),
        Announcement(
            id = 22, title = "Asamblea general de copropietarios",
            message = "Se cita a la asamblea general para revisar el presupuesto del próximo año.",
            createdAt = "2026-11-16 15:00", authorName = "Administración Domux",
            eventDate = "2026-11-28", eventTime = "18:00", category = "asamblea", categoryLabel = "Asamblea",
            readApartments = 4, totalApartments = 10
        ),
        Announcement(
            id = 23, title = "Nuevo horario de la piscina",
            message = "Desde diciembre la piscina abre de 9:00 a. m. a 8:00 p. m., de martes a domingo.",
            createdAt = "2026-11-12 10:30", authorName = "Administración Domux",
            category = "general", categoryLabel = "General", isRead = true, readApartments = 9, totalApartments = 10
        )
    )

    private fun pqrsLista() = listOf(
        Pqrs(
            id = 12, subject = "Ruido en la torre 2 después de las 10 p. m.",
            message = "Desde hace una semana hay música muy alta casi todas las noches en la torre 2.",
            status = "en_proceso", adminResponse = null, createdAt = "2026-11-12 21:15",
            residentName = "Carlos Pérez", residentId = 9, category = "Queja", apartment = "Torre 2 · Apto 202",
            radicado = "PQRS-2026-000012", semaphore = "rojo", daysRemaining = -1, dueDate = "2026-11-19",
            messages = listOf(
                PqrsMessageItem(
                    id = 1, pqrsId = 12, authorId = 1, authorName = "Administración Domux", authorRole = "ADMIN",
                    message = "Recibimos tu queja y ya hablamos con el apartamento de la torre 2.",
                    mediaUrl = null, mediaType = null, createdAt = "2026-11-13 09:00"
                )
            )
        ),
        Pqrs(
            id = 15, subject = "Bombillo dañado en el pasillo del piso 2",
            message = "El bombillo del pasillo de la torre 1, piso 2, lleva tres días sin encender.",
            status = "abierta", adminResponse = null, createdAt = "2026-11-17 08:40",
            residentName = "Gustavo Restrepo Arango", residentId = 7, category = "Petición", apartment = "Torre 1 · Apto 201",
            radicado = "PQRS-2026-000015", semaphore = "amarillo", daysRemaining = 2, dueDate = "2026-11-23"
        ),
        Pqrs(
            id = 16, subject = "Mejorar la iluminación del parqueadero",
            message = "Sería bueno poner más luz cerca de los puestos 10 al 15 porque de noche queda muy oscuro.",
            status = "abierta", adminResponse = null, createdAt = "2026-11-18 19:00",
            residentName = "María Gómez", residentId = 6, category = "Sugerencia", apartment = "Torre 1 · Apto 101",
            radicado = "PQRS-2026-000016", semaphore = "verde", daysRemaining = 8, dueDate = "2026-11-30"
        ),
        Pqrs(
            id = 9, subject = "Cobro duplicado de la cuota de administración",
            message = "En octubre me cobraron dos veces la cuota. Adjunto el soporte del pago.",
            status = "resuelta",
            adminResponse = "Se corrigió el cobro y el saldo a favor se aplicó en la cuota de diciembre.",
            createdAt = "2026-11-03 10:00", residentName = "María Gómez", residentId = 6, category = "Reclamo",
            apartment = "Torre 1 · Apto 101", radicado = "PQRS-2026-000009", semaphore = "verde",
            satisfactionRating = 5, satisfactionComment = "Atendieron rápido."
        )
    )

    private fun zonasComunes() = listOf(
        CommonArea(
            id = 1, name = "Salón social", openTime = "08:00", closeTime = "22:00", slotMinutes = 240,
            slots = listOf("08:00-12:00", "12:00-16:00", "16:00-20:00"), capacity = 40, minAdvanceDays = 2,
            maxAdvanceDays = 60, cancelDeadlineDays = 2, weeklyLimit = 1
        ),
        CommonArea(
            id = 2, name = "Piscina", openTime = "09:00", closeTime = "20:00", slotMinutes = 120,
            slots = listOf("09:00-11:00", "11:00-13:00", "14:00-16:00", "16:00-18:00"), capacity = 12,
            minAdvanceDays = 1, maxAdvanceDays = 30, cancelDeadlineDays = 1, weeklyLimit = 2, maintenanceWeekday = 0
        ),
        CommonArea(
            id = 3, name = "Zona BBQ", openTime = "10:00", closeTime = "22:00", slotMinutes = 240,
            slots = listOf("10:00-14:00", "14:00-18:00", "18:00-22:00"), capacity = 15, minAdvanceDays = 2,
            maxAdvanceDays = 45, cancelDeadlineDays = 2, weeklyLimit = 1
        )
    )

    private fun reservas() = listOf(
        Reservation(
            id = 41, commonAreaId = 1, commonAreaName = "Salón social", date = "2026-11-21",
            timeSlot = "14:00-18:00", status = "aprobada", residentName = "María Gómez", residentId = 6,
            apartment = "Torre 1 · Apto 101", attendees = 20, canCancel = true, cancelUntil = "2026-11-19"
        ),
        Reservation(
            id = 42, commonAreaId = 2, commonAreaName = "Piscina", date = "2026-11-23",
            timeSlot = "10:00-12:00", status = "pendiente", residentName = "Diana Ríos Zapata", residentId = 8,
            apartment = "Torre 2 · Apto 202", attendees = 6, canCancel = true
        ),
        Reservation(
            id = 43, commonAreaId = 1, commonAreaName = "Salón social", date = "2026-11-28",
            timeSlot = "14:00-18:00", status = "pendiente", residentName = "Natalia Correa Giraldo", residentId = 10,
            apartment = "Torre 2 · Apto 101", attendees = 25, canCancel = true
        ),
        Reservation(
            id = 44, commonAreaId = 2, commonAreaName = "Piscina", date = "2026-11-23",
            timeSlot = "14:00-16:00", status = "pendiente", residentName = "María Gómez", residentId = 6,
            apartment = "Torre 1 · Apto 101", attendees = 4, canCancel = true
        ),
        Reservation(
            id = 40, commonAreaId = 3, commonAreaName = "Zona BBQ", date = "2026-11-14",
            timeSlot = "12:00-16:00", status = "rechazada", residentName = "María Gómez", residentId = 6,
            apartment = "Torre 1 · Apto 101", attendees = 10
        )
    )

    // --- Estructura de la unidad -----------------------------------------------------------------

    private fun torres() = listOf(
        TowerData(id = 1, name = "Torre 1", floors = 2, apartmentCount = 4),
        TowerData(id = 2, name = "Torre 2", floors = 3, apartmentCount = 6)
    )

    private fun apartamento(id: Int, torre: Int, codigo: String, piso: Int, residentes: Int) = ApartmentData(
        id = id, towerId = torre, tower = "Torre $torre", code = codigo, floor = piso, number = codigo.toInt(),
        label = "Torre $torre · Apto $codigo", residentCount = residentes
    )

    private fun apartamentos() = listOf(
        apartamento(1, 1, "101", 1, 3), apartamento(2, 1, "102", 1, 0),
        apartamento(3, 1, "201", 2, 2), apartamento(4, 1, "202", 2, 0),
        apartamento(5, 2, "101", 1, 1), apartamento(6, 2, "102", 1, 0),
        apartamento(7, 2, "201", 2, 0), apartamento(8, 2, "202", 2, 2),
        apartamento(9, 2, "301", 3, 1), apartamento(10, 2, "302", 3, 0)
    )

    private fun parqueaderos() = listOf(
        ParkingSpotData(1, "P-101", "residente", "Sótano 1", 1, "Torre 1 · Apto 101", true),
        ParkingSpotData(2, "P-201", "residente", "Sótano 1", 3, "Torre 1 · Apto 201", false),
        ParkingSpotData(3, "P-202", "residente", "Sótano 2", 8, "Torre 2 · Apto 202", true),
        ParkingSpotData(4, "V-01", "visitante", "Sótano 1", null, null, true),
        ParkingSpotData(5, "V-02", "visitante", "Sótano 1", null, null, false),
        ParkingSpotData(6, "V-03", "visitante", "Sótano 1", null, null, false),
        ParkingSpotData(7, "V-04", "visitante", "Sótano 2", null, null, true)
    )

    private fun depositos() = listOf(
        StorageRoomData(1, "D-12", 1, "Torre 1 · Apto 101"),
        StorageRoomData(2, "D-21", 3, "Torre 1 · Apto 201"),
        StorageRoomData(3, "D-30", null, null)
    )

    // --- Textos legales (de ejemplo, solo para las fotos) ------------------------------------------

    private fun documentosLegales() = listOf(
        LegalDocumentSummary(
            slug = "terminos-y-condiciones", title = "Términos y condiciones de uso",
            summary = "Las reglas para usar la app y la página de DOMUX.", status = "vigente",
            version = "1.0", effectiveFrom = "2026-11-01"
        ),
        LegalDocumentSummary(
            slug = "politica-de-privacidad", title = "Política de privacidad",
            summary = "Qué datos se guardan, para qué y cómo pedir que se corrijan o se borren.",
            status = "vigente", version = "1.0", effectiveFrom = "2026-11-01"
        ),
        LegalDocumentSummary(
            slug = "aviso-de-tratamiento-de-datos", title = "Aviso sobre el tratamiento de datos personales",
            summary = "Borrador pendiente de revisión.", status = "borrador", version = null, effectiveFrom = null
        )
    )

    private fun documentoLegal(slug: String) = LegalDocument(
        slug = slug, title = "Política de privacidad",
        summary = "Qué datos se guardan, para qué y cómo pedir que se corrijan o se borren.",
        status = "vigente", version = "1.0", effectiveFrom = "2026-11-01",
        blocks = listOf(
            LegalBlock("heading", 2, "1. Quién cuida tus datos", null, null),
            LegalBlock(
                "paragraph", null,
                "Texto de ejemplo para las fotos de pantalla. La administración de la unidad es quien decide para qué se usan los datos de los residentes.",
                null, null
            ),
            LegalBlock("heading", 2, "2. Qué datos se guardan", null, null),
            LegalBlock(
                "list", null, null, false,
                listOf("Nombre y apartamento", "Teléfono y correo", "Visitas, paquetes y reservas")
            ),
            LegalBlock("heading", 2, "3. Tus derechos", null, null),
            LegalBlock("paragraph", null, "Puedes pedir que corrijan o borren tus datos escribiendo a la administración.", null, null)
        )
    )

    // --- El buscador ---------------------------------------------------------------------------------

    private fun busqueda(texto: String, lugar: String?) = SearchResponse(
        query = texto,
        place = lugar ?: "todo",
        places = defaultSearchPlaces(),
        tooShort = false,
        groups = listOf(
            SearchGroup(
                type = "personas", label = "Personas", more = false,
                items = listOf(
                    SearchResult("personas", 6, "María Gómez", "Residente · propietaria", 1, "Torre 1 · Apto 101", null),
                    SearchResult("personas", 17, "Mariana Ruiz Cano", "Residente · arrendataria", 9, "Torre 2 · Apto 301", null)
                )
            ),
            SearchGroup(
                type = "apartamentos", label = "Apartamentos", more = false,
                items = listOf(
                    SearchResult("apartamentos", 1, "Torre 1 · Apto 101", "3 personas · 2 vehículos", 1, "Torre 1 · Apto 101", null)
                )
            ),
            SearchGroup(
                type = "vehiculos", label = "Vehículos", more = false,
                items = listOf(
                    SearchResult("vehiculos", 7, "MAR123", "Mazda 3 · María Gómez", 1, "Torre 1 · Apto 101", "residente")
                )
            ),
            SearchGroup(
                type = "pqrs", label = "PQRS", more = true,
                items = listOf(
                    SearchResult("pqrs", 12, "PQRS-2026-000012 · Ruido en la torre 2", "Queja · en proceso", 8, "Torre 2 · Apto 202", null)
                )
            )
        )
    )
}
