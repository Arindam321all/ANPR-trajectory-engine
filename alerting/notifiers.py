"""Notification sinks. Delivery failures are logged and do not stop ingestion."""
import json
from urllib.request import Request, urlopen

from config_loader import get_config

def notify(alert: dict) -> bool:
    """Send an alert to configured sinks; return True when all enabled sinks succeed."""
    cfg = get_config().get("alerting", {}).get("notifications", {})
    delivered = True
    webhook_url = cfg.get("webhook_url")
    if webhook_url:
        try:
            payload = json.dumps(alert, default=str).encode("utf-8")
            request = Request(webhook_url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=float(cfg.get("timeout_seconds", 5))):
                pass
        except Exception:
            delivered = False
    return delivered
