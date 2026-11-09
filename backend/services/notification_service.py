"""Persist notifications and dispatch FCM only after their transaction commits."""

import json
import logging
import os
from threading import Lock

from google.auth.exceptions import DefaultCredentialsError
from firebase_admin import credentials, initialize_app, messaging
from firebase_admin.exceptions import FirebaseError
from extensions import db
from models import DevicePushToken, Notification, User
from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_firebase_app = None
_firebase_lock = Lock()
_missing_credentials_logged = False


def _get_firebase_app():
    global _firebase_app, _missing_credentials_logged
    if _firebase_app is not None:
        return _firebase_app
    with _firebase_lock:
        if _firebase_app is not None:
            return _firebase_app
        service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        application_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not service_account_json and not application_credentials:
            if not _missing_credentials_logged:
                logger.warning(
                    "FCM push is disabled: configure FIREBASE_SERVICE_ACCOUNT_JSON "
                    "or GOOGLE_APPLICATION_CREDENTIALS."
                )
                _missing_credentials_logged = True
            return None
        try:
            if service_account_json:
                credential = credentials.Certificate(json.loads(service_account_json))
                _firebase_app = initialize_app(credential)
            else:
                _firebase_app = initialize_app()
        except (DefaultCredentialsError, ValueError, OSError, FirebaseError):
            logger.exception("Firebase Admin could not be initialized.")
            return None
    return _firebase_app


def _dispatch_after_commit(session):
    queued = session.info.pop("domux_push_queue", [])
    if not queued:
        return
    app = _get_firebase_app()
    if app is None:
        return
    for item in queued:
        for offset in range(0, len(item["tokens"]), 500):
            tokens = item["tokens"][offset:offset + 500]
            message = messaging.MulticastMessage(
                tokens=tokens,
                notification=messaging.Notification(
                    title=item["title"],
                    body=item["message"],
                ),
                data={
                    "type": item["type"],
                    "route": item["route"],
                    "notificationId": str(item["notification"].id),
                },
                android=messaging.AndroidConfig(
                    priority="high" if item["type"] == "visit" else "normal"
                ),
            )
            try:
                result = messaging.send_each_for_multicast(message, app=app)
                if result.failure_count:
                    logger.warning(
                        "FCM delivery had failures for user %s: %s/%s",
                        item["user_id"],
                        result.failure_count,
                        len(tokens),
                    )
                    for token, response in zip(tokens, result.responses):
                        if not response.success:
                            logger.warning(
                                "FCM delivery failed for a device token: %s",
                                response.exception,
                            )
            except (FirebaseError, ValueError):
                logger.exception("FCM delivery failed for user %s.", item["user_id"])


def _clear_queued_pushes(session):
    session.info.pop("domux_push_queue", None)


event.listen(Session, "after_commit", _dispatch_after_commit)
event.listen(Session, "after_rollback", _clear_queued_pushes)


def _queue_push(user_id, title, message, notification_type, notification):
    tokens = [
        row[0]
        for row in db.session.query(DevicePushToken.token)
        .filter_by(user_id=user_id)
        .all()
    ]
    if not tokens:
        return
    route = {
        "pqrs": "pqrs",
        "reservation": "reservations",
        "package": "registry",
        "visit": "registry",
        "announcement": "announcements",
    }.get(notification_type, "notifications")
    db.session.info.setdefault("domux_push_queue", []).append({
        "user_id": user_id,
        "tokens": tokens,
        "title": title,
        "message": message,
        "type": notification_type,
        "route": route,
        "notification": notification,
    })


def notify_user(user_id, title, message, notification_type):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
    )
    db.session.add(notification)
    _queue_push(user_id, title, message, notification_type, notification)
    return notification


def notify_residents(title, message, notification_type):
    residents = db.session.query(User.id).filter_by(role="RESIDENT").all()
    notifications = [
        Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=notification_type,
        )
        for (user_id,) in residents
    ]
    db.session.add_all(notifications)
    for notification in notifications:
        _queue_push(
            notification.user_id,
            title,
            message,
            notification_type,
            notification,
        )
    return notifications
