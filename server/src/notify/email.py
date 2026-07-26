"""
Escalation email — the handoff from BEACON to a person who can send help.

WHY EMAIL AT ALL
An escalation that only exists inside our dashboard is not an escalation. The
moment an operator decides something is real, that decision has to leave our
system and land somewhere a private security company actually watches. Email is
the lowest-friction version of that: no integration to negotiate, no app to
install, works from a laptop in a demo and from a control room in production.
It is not the end state — a real deployment would push to the security
provider's own dispatch system — and the copy says so rather than implying we
are wired into anyone.

PROVIDERS
Resend and SendGrid, chosen because both give a working API key on a free tier
with no domain verification, so this can be demonstrated the same day. The two
APIs differ only in URL and body shape, so one adapter covers both and the
choice is a single env var.

WHAT THIS DELIBERATELY DOES NOT DO
It does not send on the machine's say-so. `send_escalation` takes a Situation
that must already be ESCALATED, which under decision.py means a named human put
their name on it. An automated system emailing armed response about a 53%
detection is exactly the outcome the whole honesty design exists to prevent.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import Optional

from ..vision.decision import Level, Situation

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"

# Resend's shared sender works with no domain setup, which is why it is the
# default — a demo should not be blocked on DNS propagation.
DEFAULT_FROM = "BEACON <onboarding@resend.dev>"


class NotConfigured(RuntimeError):
    """Raised instead of silently no-op'ing, so a demo fails loudly at setup."""


@dataclass(frozen=True)
class EmailResult:
    ok: bool
    provider: str
    to: list[str]
    detail: str = ""
    message_id: Optional[str] = None


def _config() -> tuple[str, str, str, list[str]]:
    provider = (os.getenv("EMAIL_PROVIDER") or "resend").lower()
    key = os.getenv("RESEND_API_KEY") if provider == "resend" else os.getenv("SENDGRID_API_KEY")
    if not key:
        raise NotConfigured(
            f"{provider} selected but its API key is not set. Add "
            f"{'RESEND_API_KEY' if provider == 'resend' else 'SENDGRID_API_KEY'} "
            f"to server/.env — never to the repo, which is public."
        )
    sender = os.getenv("ESCALATION_FROM") or DEFAULT_FROM
    to = [a.strip() for a in (os.getenv("ESCALATION_TO") or "").split(",") if a.strip()]
    if not to:
        raise NotConfigured("ESCALATION_TO is not set — no one would receive the escalation.")
    return provider, key, sender, to


def render_escalation(
    situation: Situation,
    *,
    location: str = "Unknown location",
    camera_label: Optional[str] = None,
    clip_url: Optional[str] = None,
) -> tuple[str, str, str]:
    """
    Returns (subject, html, plaintext).

    The email leads with what a dispatcher needs in the first two seconds —
    where, what, who said so — and puts the model's confidence below that
    rather than at the top. A confidence percentage is our internal evidence,
    not the headline; the headline is that a person reviewed footage and asked
    for help.
    """
    c = situation.to_dict()["counts"]
    where = camera_label or situation.source_id
    label = max(situation.weapon_labels, key=lambda k: situation.weapon_labels[k]) if situation.weapon_labels else None
    when = datetime.fromtimestamp(situation.escalated_at or 0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    headline = f"Possible {label}" if label else "Possible incident"
    subject = f"BEACON escalation — {headline} at {location}"

    rows = [
        ("Location", location),
        ("Camera", where),
        ("Escalated by", situation.escalated_by or "unknown"),
        ("Time", when),
    ]
    if label:
        rows.append(("Detected", f"{label} — seen in {c['weapon_frames']} of {c['frames']} frames, "
                                 f"peak confidence {int(c['weapon_peak_confidence'] * 100)}%"))
    if situation.first_weapon_at_s is not None:
        rows.append(("First seen at", f"{situation.first_weapon_at_s:.0f}s into the clip"))
    if c["plates_read"]:
        rows.append(("Plates read", ", ".join(c["plates_read"])))
    elif c["plate_frames"]:
        rows.append(("Plates", f"{c['plate_frames']} seen, none legible"))

    evidence_lines = [f"- {e.text}" for e in situation.evidence]

    # The disclaimer is not boilerplate. If a security company acts on this and
    # it turns out to be a phone in someone's hand, they need to have known from
    # the first email what kind of claim we were making.
    disclaimer = (
        "This is a machine detection reviewed and escalated by a named human operator. "
        "It is a lead, not an identification, and it has not been verified against any "
        "official record. BEACON has no dispatch authority — this email is a request "
        "for a person to look, not an automated alarm."
    )

    text = "\n".join([
        f"BEACON ESCALATION — {headline}",
        "",
        *[f"{k}: {v}" for k, v in rows],
        "",
        "Why this was raised:",
        situation.level_reason,
        "",
        "Evidence:",
        *evidence_lines,
        "",
        *([f"Clip: {clip_url}", ""] if clip_url else []),
        disclaimer,
    ])

    row_html = "".join(
        f'<tr><td style="padding:6px 14px 6px 0;color:#6b7280;font-size:13px;white-space:nowrap">{escape(k)}</td>'
        f'<td style="padding:6px 0;color:#111827;font-size:14px;font-weight:600">{escape(str(v))}</td></tr>'
        for k, v in rows
    )
    ev_html = "".join(
        f'<li style="margin-bottom:6px;color:#374151;font-size:13px">{escape(e.text)}'
        + (f'<br><span style="color:#9ca3af;font-size:12px">{escape(e.weight_note)}</span>' if e.weight_note else "")
        + "</li>"
        for e in situation.evidence
    )
    html = f"""
<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;margin:0 auto">
  <div style="background:#111827;padding:18px 22px;border-radius:12px 12px 0 0">
    <div style="color:#9ca3af;font-size:11px;letter-spacing:.12em;text-transform:uppercase">BEACON escalation</div>
    <div style="color:#fff;font-size:20px;font-weight:700;margin-top:4px">{escape(headline)} at {escape(location)}</div>
  </div>
  <div style="border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;padding:22px">
    <table style="border-collapse:collapse;width:100%">{row_html}</table>
    <div style="margin-top:18px;padding:14px;background:#fef2f2;border-left:3px solid #dc2626;border-radius:4px">
      <div style="color:#991b1b;font-size:13px;line-height:1.5">{escape(situation.level_reason)}</div>
    </div>
    <div style="margin-top:18px">
      <div style="color:#6b7280;font-size:11px;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px">Evidence</div>
      <ul style="margin:0;padding-left:18px">{ev_html}</ul>
    </div>
    {f'<div style="margin-top:18px"><a href="{escape(clip_url)}" style="color:#2563eb;font-size:13px">View the clip</a></div>' if clip_url else ''}
    <div style="margin-top:22px;padding-top:16px;border-top:1px solid #e5e7eb;color:#9ca3af;font-size:12px;line-height:1.6">
      {escape(disclaimer)}
    </div>
  </div>
</div>""".strip()

    return subject, html, text


async def send_member_report(
    *,
    subject: str,
    text: str,
    html: Optional[str] = None,
) -> EmailResult:
    """
    A named member tapping "Report to security" on a recorded clip is the same
    kind of human decision `send_escalation` requires for a vision job — it's
    just not tied to a `Situation` from the jobs pipeline (Cam tab clips are
    pre-recorded detection tracks, not live jobs.py runs). Same provider/config
    plumbing as send_escalation, same all-or-nothing config check, no Situation
    object required.
    """
    import httpx

    provider, key, sender, default_to = _config()
    body_html = html or f"<pre style='white-space:pre-wrap;font-family:inherit'>{escape(text)}</pre>"

    if provider == "resend":
        url, headers = RESEND_URL, {"Authorization": f"Bearer {key}"}
        body = {"from": sender, "to": default_to, "subject": subject, "html": body_html, "text": text}
    else:
        url, headers = SENDGRID_URL, {"Authorization": f"Bearer {key}"}
        addr = sender.split("<")[-1].strip("<> ")
        body = {
            "personalizations": [{"to": [{"email": r} for r in default_to]}],
            "from": {"email": addr, "name": "BEACON"},
            "subject": subject,
            "content": [{"type": "text/plain", "value": text}, {"type": "text/html", "value": body_html}],
        }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, json=body)

    if r.status_code >= 300:
        logger.error("member report email failed: %s %s", r.status_code, r.text[:400])
        return EmailResult(ok=False, provider=provider, to=default_to,
                           detail=f"HTTP {r.status_code}: {r.text[:200]}")

    msg_id = r.headers.get("X-Message-Id") if provider == "sendgrid" else None
    logger.info("member report email sent to %s via %s", default_to, provider)
    return EmailResult(ok=True, provider=provider, to=default_to, detail="sent", message_id=msg_id)


async def send_escalation(
    situation: Situation,
    *,
    location: str = "Unknown location",
    camera_label: Optional[str] = None,
    clip_url: Optional[str] = None,
    to: Optional[list[str]] = None,
) -> EmailResult:
    """
    Send the escalation. Refuses anything the machine raised on its own.
    """
    if situation.level is not Level.ESCALATED:
        raise ValueError(
            f"Refusing to email: {situation.source_id} is at {situation.level.name}. "
            "Only a human escalation leaves this system."
        )

    import httpx

    provider, key, sender, default_to = _config()
    recipients = to or default_to
    subject, html, text = render_escalation(
        situation, location=location, camera_label=camera_label, clip_url=clip_url
    )

    if provider == "resend":
        url, headers = RESEND_URL, {"Authorization": f"Bearer {key}"}
        body = {"from": sender, "to": recipients, "subject": subject, "html": html, "text": text}
    else:
        url, headers = SENDGRID_URL, {"Authorization": f"Bearer {key}"}
        # SendGrid wants the sender split out and content as an ordered list,
        # plaintext first — it uses the order to pick a fallback.
        addr = sender.split("<")[-1].strip("<> ")
        body = {
            "personalizations": [{"to": [{"email": r} for r in recipients]}],
            "from": {"email": addr, "name": "BEACON"},
            "subject": subject,
            "content": [{"type": "text/plain", "value": text}, {"type": "text/html", "value": html}],
        }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=headers, json=body)

    if r.status_code >= 300:
        logger.error("escalation email failed: %s %s", r.status_code, r.text[:400])
        return EmailResult(ok=False, provider=provider, to=recipients,
                           detail=f"HTTP {r.status_code}: {r.text[:200]}")

    msg_id = None
    if provider == "resend":
        try:
            msg_id = r.json().get("id")
        except Exception:
            pass
    else:
        msg_id = r.headers.get("X-Message-Id")

    logger.info("escalation email sent to %s via %s", recipients, provider)
    return EmailResult(ok=True, provider=provider, to=recipients, detail="sent", message_id=msg_id)
