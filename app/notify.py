"""Escalations to a human. Dashboard fallback first: every alert is an event with kind "alert"
(the dashboard shows those as a banner). If Twilio is configured via environment variables, the
same message is also texted. The app runs fine with Twilio unset or broken.

  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, ALERT_TO   (ALERT_TO must be a verified number)
"""
import os
import threading


def sms_configured():
    return all(os.environ.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "ALERT_TO"))


def _send_sms(body, on_error):
    try:
        from twilio.rest import Client
        Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]).messages.create(
            body=body, from_=os.environ["TWILIO_FROM"], to=os.environ["ALERT_TO"])
    except Exception as exc:  # never let a failed text take down the sim
        on_error(f"SMS failed ({type(exc).__name__}); alert shown on dashboard only")


def alert(w, message, robot_id=None, bin_id=None):
    """Raise an alert: always logged to the feed; also texted in live mode when Twilio is set up."""
    w.log("alert", f"ALERT: {message}", robot_id=robot_id, bin_id=bin_id)
    if w.live and sms_configured():
        threading.Thread(target=_send_sms, args=(f"[Waste Fleet] {message}", lambda m: w.log("alert_sms_failed", m)),
                         daemon=True).start()
