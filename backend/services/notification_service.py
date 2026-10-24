"""Notification creation helpers used by endpoint workflows."""

from models import Notification, User
from extensions import db


def notify_user(user_id, title, message, notification_type):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
    )
    db.session.add(notification)
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
    return notifications
