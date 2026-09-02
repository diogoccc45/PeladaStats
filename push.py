"""
Sends real Web Push notifications (OS-level, even with the app closed) to a
user's subscribed devices — the delivery side of the notifications system.

Never allowed to break the caller: a push failure (network hiccup, an
expired/revoked subscription) is swallowed here — the in-app notification
(bell + confetti) is already created regardless of whether the push
succeeds. A subscription the push service reports as gone (404/410) is
cleaned out of the database so we stop wasting a request on it.
"""
import json
import logging

from flask import current_app
from pywebpush import WebPushException, webpush

from database import get_db


def send_push_to_user(user_id, title, body):
    db = get_db()
    subs = db.execute("SELECT * FROM push_subscriptions WHERE user_id = ?", (user_id,)).fetchall()

    for sub in subs:
        subscription_info = {
            "endpoint": sub["endpoint"],
            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=current_app.config["VAPID_PRIVATE_KEY"],
                vapid_claims={"sub": current_app.config["VAPID_CLAIMS_SUB"]},
            )
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                db.execute("DELETE FROM push_subscriptions WHERE id = ?", (sub["id"],))
                db.commit()
            else:
                logging.warning("Push falhou para user_id=%s: %s", user_id, e)
        except Exception as e:
            logging.warning("Push falhou (erro inesperado) para user_id=%s: %s", user_id, e)
