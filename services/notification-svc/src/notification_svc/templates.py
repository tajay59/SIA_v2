"""Email templates (Design Brief §13, APD §7 deep links).

One layout: single column, 600 px, white card, CIMH header in the logo blue, ink text, one primary button
(#006FA8, white text) and the same link as text, request id in mono, key facts, a footer saying why the person
gets it. Every value is HTML-escaped; a plain-text part is always sent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

LOGO_BLUE = "#0084C8"
PRIMARY = "#006FA8"
INK = "#0F1A24"
MUTED = "#53606C"
BG = "#F5F7FA"
BORDER = "#C7D0DA"
BODY_STYLE = (
    f"margin:0;padding:24px 12px;background:{BG};font-family:Inter,'Segoe UI',Roboto,Arial,sans-serif;"
    f"font-size:15px;line-height:22px;color:{INK}"
)
HEADER_STYLE = (
    f"background:{LOGO_BLUE};color:#FFFFFF;padding:16px 24px;border-radius:12px 12px 0 0;font-weight:700;font-size:17px"
)
ADDRESS = "Caribbean Institute for Meteorology and Hydrology · Husbands, St. James, Barbados"


@dataclass(frozen=True)
class Message:
    """What a handler wants sent; rendered by `render`."""

    to: str
    subject: str
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    button: str | None = None
    link: str | None = None
    facts: list[tuple[str, str]] = field(default_factory=list)
    request_id: str | None = None
    status: tuple[str, str] | None = None  # (label, colour) shown as a coloured text label
    code: str | None = None  # one-time code, shown large
    why: str = "you have an account with CIMH Stores"


@dataclass(frozen=True)
class Rendered:
    to: str
    subject: str
    html: str
    text: str


def render(m: Message) -> Rendered:
    e = escape
    parts: list[str] = []
    if m.status:
        label, colour = m.status
        parts.append(f'<p style="margin:0 0 12px;font-weight:600;color:{e(colour)}">{e(label)}</p>')
    parts.append(f'<h1 style="margin:0 0 16px;font-size:22px;line-height:28px;color:{INK}">{e(m.heading)}</h1>')
    if m.request_id:
        parts.append(
            f'<p style="margin:0 0 16px;color:{MUTED}">Request '
            f"<span style=\"font-family:'JetBrains Mono',Consolas,monospace;color:{INK}\">{e(m.request_id)}</span></p>"
        )
    parts += [f'<p style="margin:0 0 16px">{e(p)}</p>' for p in m.paragraphs]
    if m.code:
        parts.append(
            f"<p style=\"margin:0 0 16px;font-family:'JetBrains Mono',Consolas,monospace;font-size:28px;"
            f'letter-spacing:6px;font-weight:700;color:{INK}">{e(m.code)}</p>'
        )
    if m.facts:
        rows = "".join(
            f'<tr><td style="padding:4px 16px 4px 0;color:{MUTED}">{e(k)}</td>'
            f'<td style="padding:4px 0;color:{INK};font-weight:600">{e(v)}</td></tr>'
            for k, v in m.facts
        )
        parts.append(f'<table role="presentation" style="margin:0 0 16px;border-collapse:collapse">{rows}</table>')
    if m.button and m.link:
        parts.append(
            f'<p style="margin:24px 0 8px"><a href="{e(m.link)}" style="display:inline-block;background:{PRIMARY};'
            f'color:#FFFFFF;text-decoration:none;font-weight:600;padding:12px 20px;border-radius:8px">'
            f"{e(m.button)}</a></p>"
            f'<p style="margin:0 0 16px;font-size:13px;color:{MUTED}">Or open this link: '
            f'<a href="{e(m.link)}" style="color:{PRIMARY}">{e(m.link)}</a></p>'
        )
    body = "\n".join(parts)
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{e(m.subject)}</title></head>
<body style="{BODY_STYLE}">
<table role="presentation" width="100%" style="max-width:600px;margin:0 auto;border-collapse:collapse">
<tr><td style="{HEADER_STYLE}">CIMH Stores</td></tr>
<tr><td style="background:#FFFFFF;padding:24px;border:1px solid {BORDER};border-top:0;border-radius:0 0 12px 12px">
{body}
</td></tr>
<tr><td style="padding:16px 8px;font-size:12px;line-height:18px;color:{MUTED}">CIMH Stores · {e(ADDRESS)}<br>
You're receiving this because {e(m.why)}.</td></tr>
</table></body></html>
"""
    text = [m.heading, ""]
    if m.status:
        text += [m.status[0], ""]
    if m.request_id:
        text += [f"Request {m.request_id}", ""]
    for p in m.paragraphs:
        text += [p, ""]
    if m.code:
        text += [m.code, ""]
    text += [f"{k}: {v}" for k, v in m.facts]
    if m.facts:
        text.append("")
    if m.button and m.link:
        text += [f"{m.button}: {m.link}", ""]
    text += ["--", f"CIMH Stores · {ADDRESS}", f"You're receiving this because {m.why}."]
    return Rendered(m.to, m.subject, html, "\n".join(text) + "\n")
