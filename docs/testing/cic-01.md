# CIC-01 · Línea base de las pruebas automáticas del servidor

Evidencias EV-001, EV-002 y EV-003 del Plan de Calidad, Pruebas y Aceptación (CAL-01).

| Campo | Valor |
| --- | --- |
| Ciclo y ejecución | CIC-01 · EJ-2026-01 |
| Fecha | 8 de noviembre de 2026; se repitió el 9 de noviembre de 2026 con el mismo resultado |
| Versión | commit 1d7d7a4 (rama feature/pqrs-chat-usuarios-reservas-porteria) |
| Ambiente | Copia del commit con Python 3.13.16, SQLite en memoria y Firebase simulado con unittest.mock |
| Comando | `cd backend` y luego `python -m unittest discover -s tests -v` |
| Resultado | 8/11/2026: `Ran 45 tests in 21.300s` · `OK`. 9/11/2026: `Ran 45 tests in 22.222s` · `OK` |
| Responsable | Maicol Esneider Posada Callejas |

## EV-001 · Resultado de cada prueba

| Archivo | Prueba | Resultado |
| --- | --- | --- |
| test_admin_resident_actions.py | test_admin_can_filter_pqrs_by_resident_but_resident_cannot | Aprobada |
| test_admin_resident_actions.py | test_admin_can_respond_to_the_pqrs_created_for_resident | Aprobada |
| test_admin_resident_actions.py | test_admin_creates_pqrs_for_resident_with_audit_and_notification | Aprobada |
| test_admin_resident_actions.py | test_admin_creates_reservation_for_resident_with_audit_and_notification | Aprobada |
| test_admin_resident_actions.py | test_guard_cannot_create_on_behalf_of_a_resident | Aprobada |
| test_admin_resident_actions.py | test_resident_cannot_create_requests_for_another_resident | Aprobada |
| test_pqrs.py | test_admin_can_create_pqrs_for_a_resident | Aprobada |
| test_pqrs.py | test_admin_cannot_resolve_pqrs_without_text_response | Aprobada |
| test_pqrs.py | test_batch_response_is_atomic_and_notifies_once_per_resident | Aprobada |
| test_pqrs.py | test_guard_cannot_create_pqrs | Aprobada |
| test_pqrs.py | test_legacy_description_and_response_are_migrated_once | Aprobada |
| test_pqrs.py | test_resident_cannot_write_to_another_residents_pqrs | Aprobada |
| test_pqrs.py | test_resident_message_reopens_resolved_pqrs_and_notifies_admin | Aprobada |
| test_pqrs.py | test_satisfaction_only_for_own_resolved_pqrs_and_keeps_reopen_history | Aprobada |
| test_reservations.py | test_admin_reply_notifies_resident_and_resident_message_notifies_admin | Aprobada |
| test_reservations.py | test_calendar_blocks_only_fully_occupied_days | Aprobada |
| test_reservations.py | test_guard_cannot_create_or_message_reservations | Aprobada |
| test_reservations.py | test_pending_requests_do_not_occupy_but_approval_rechecks_conflicts | Aprobada |
| test_reservations.py | test_rejecting_and_cancelling_reservation_notify_resident | Aprobada |
| test_reservations.py | test_reservation_request_is_pending_and_optional_message_is_saved | Aprobada |
| test_reservations.py | test_resident_can_cancel_before_date_but_not_on_or_after_reserved_date | Aprobada |
| test_reservations.py | test_resident_cannot_cancel_or_message_another_residents_reservation | Aprobada |
| test_security_workflows.py | test_admin_cannot_create_a_resident_owned_qr_pass | Aprobada |
| test_security_workflows.py | test_call_authorization_is_guard_only_and_guard_can_record_resident_search | Aprobada |
| test_security_workflows.py | test_invalid_default_firebase_credentials_do_not_fail_committed_notification | Aprobada |
| test_security_workflows.py | test_manual_visit_can_be_linked_to_qr_without_duplicating_history | Aprobada |
| test_security_workflows.py | test_manual_visitor_cannot_return_after_definitive_exit | Aprobada |
| test_security_workflows.py | test_package_delivery_requires_receiver_and_notifies_resident | Aprobada |
| test_security_workflows.py | test_package_listing_automatically_trashes_and_purges_expired_items | Aprobada |
| test_security_workflows.py | test_package_registration_status_trash_restore_and_purge | Aprobada |
| test_security_workflows.py | test_push_from_rolled_back_notification_is_not_sent_later | Aprobada |
| test_security_workflows.py | test_push_is_sent_after_commit_with_route_and_high_priority_for_visitors | Aprobada |
| test_security_workflows.py | test_push_tokens_are_scoped_to_authenticated_user | Aprobada |
| test_security_workflows.py | test_qr_limits_new_people_allows_same_day_reentry_and_revokes | Aprobada |
| test_security_workflows.py | test_qr_rejects_invalid_duration_and_foreign_resident_cannot_revoke | Aprobada |
| test_security_workflows.py | test_resident_decision_call_authorization_entry_and_exit_are_audited | Aprobada |
| test_security_workflows.py | test_visit_needs_consent_for_document_and_notifies_resident | Aprobada |
| test_user_profiles.py | test_admin_must_record_consent_when_creating_resident | Aprobada |
| test_user_profiles.py | test_admin_user_search_filters_and_paginates | Aprobada |
| test_user_profiles.py | test_household_presence_filter_is_applied_on_the_server | Aprobada |
| test_user_profiles.py | test_profile_endpoints_are_role_restricted | Aprobada |
| test_user_profiles.py | test_promoting_account_to_resident_requires_consent | Aprobada |
| test_user_profiles.py | test_resident_profile_rejects_protected_fields_and_allows_profile_fields | Aprobada |
| test_user_profiles.py | test_unit_profile_saves_household_and_normalizes_plate | Aprobada |
| test_user_profiles.py | test_vehicle_plate_cannot_be_reused_in_another_unit | Aprobada |

Notas:

- Se quitaron de esta evidencia las líneas del registro de solicitudes, porque las rutas del QR llevan su token
  (SEC-012), y lo que imprime la semilla, porque muestra las contraseñas de prueba (SEC-013).
- Las trazas de error que aparecen en la salida completa son de pruebas que simulan fallas a propósito.
- La advertencia `DeprecationWarning` de `datetime.utcnow()` corresponde a la hora sin zona que corrige ADR-011 (TT-031).

## EV-002 · Revisión de rutas

Se comparó el mapa de rutas de Flask (url_map, sin la ruta static) con el catálogo de ARQ-01 (sección 9.2):
56 pares de método y ruta, que son las 52 rutas construidas más 4 alias sin «/admin» de las rutas de usuarios.
Resultado del 8/11/2026: ninguna ruta falta en el documento y ninguna del documento falta en el código.

## EV-003 · Revisión del código contra ARQ-01

- Una revisión independiente del documento de arquitectura contra el código encontró 25 diferencias, que se
  corrigieron en ARQ-01 v1.0 antes de aprobarlo (9/11/2026).
- De esa revisión y de REQ-02 y DSN-01 salen los defectos DEF-001 a DEF-013 (CAL-01, 14.2) y los hallazgos de
  seguridad de CAL-01 (11.3).
- Medición del inicio de sesión (SEC-011), 9/11/2026, SQLite en memoria, mediana de 15 intentos: un correo que no
  existe responde en cerca de 1 ms y uno que existe con la contraseña errada, en cerca de 103 ms.
