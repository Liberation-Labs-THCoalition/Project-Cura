"""Email intake: one real message in, a verdict out. Nothing stored, nothing sent.

Thomas, 2026-11-17 (his answer on the Cura calls card): "Let's also make sure
email is included and scanned, it's the most common attack surface for
seniors." The plan for that is docs/EMAIL_SCOPE_PLAN.md. This module is its
first, local step (E1 there).

`MessageScanner.scan_email` existed with zero production callers, and it took
the sender, subject and body as strings someone had already pulled apart, so it
never saw a real message: not the Authentication-Results her mail server wrote,
not the Reply-To, not the name shown in front of the address, and not where a
link really goes behind the words it shows. This reads an RFC 822 message (a
saved .eml, or the raw text a mail client shows as "Show original") with the
standard library and hands the scanner all of it.

What it keeps: the scanner's MessageVerdict (the sender's domain, the subject's
first 50 characters, the indicators). The body is read in memory and dropped;
it is not logged, not returned and not written anywhere.

What it does not do: it opens no mailbox, holds no credential, and tells
nobody. A verdict reaches a person only through whoever called it, who must not
say anyone was told (tests/test_email_intake.py checks both surfaces).
"""
from __future__ import annotations

import email
import email.policy
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser

from cura.privacy.message_scanner import MessageScanner, MessageVerdict

#: Headers the scanner reads. Everything else stays in the message object and
#: is dropped with it.
_HEADERS = ("From", "Return-Path", "Reply-To", "Received-SPF", "DKIM-Signature",
            "Authentication-Results")


class _Links(HTMLParser):
    """(visible text, href) for each <a>, and the page's text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.text: list[str] = []
        self._href: str | None = None
        self._label: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._label = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append(("".join(self._label).strip(), self._href))
            self._href = None

    def handle_data(self, data):
        self.text.append(data)
        if self._href is not None:
            self._label.append(data)


def _parts(msg) -> tuple[str, list[tuple[str, str]]]:
    """The readable text of a message and its links (from the HTML part)."""
    plain, html = [], []
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            content = part.get_content()
        except (LookupError, ValueError):
            content = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
        (plain if ctype == "text/plain" else html).append(content)
    links: list[tuple[str, str]] = []
    html_text = []
    for h in html:
        p = _Links()
        p.feed(h)
        links += p.links
        html_text.append(" ".join(p.text))
    body = "\n".join(plain) if plain else "\n".join(html_text)
    # The scanner finds raw URLs in the body; hrefs hidden behind words count too.
    hrefs = " ".join(href for _, href in links if href.startswith(("http://", "https://")))
    return (body + ("\n" + hrefs if hrefs else "")), links


def scan_raw_email(raw: bytes | str, scanner: MessageScanner | None = None) -> MessageVerdict:
    """Scan one RFC 822 message. Returns the verdict only.

    Raises ValueError for input that is not an email at all (no From header),
    rather than returning "safe" for something that was never read.
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    from_header = str(msg.get("From", "") or "")
    if not from_header:
        raise ValueError("this is not an email message: it has no From header")
    name, address = parseaddr(from_header)
    if not address and getaddresses([from_header]):
        name, address = getaddresses([from_header])[0]
    headers = {h: str(msg.get(h, "") or "") for h in _HEADERS if msg.get(h)}
    body, links = _parts(msg)
    scanner = scanner or MessageScanner()
    verdict = scanner.scan_email(
        sender=address, subject=str(msg.get("Subject", "") or ""), body=body,
        headers=headers or None, links=links, display_name=name)
    del body, msg          # read in memory, dropped here
    return verdict


def plain_words(verdict: MessageVerdict) -> str:
    """The verdict as she or a helper would want it read out.

    Says what was found and what to do. Says nothing about anyone being told,
    because scanning tells nobody.
    """
    if verdict.risk_level == "safe" and not verdict.indicators:
        return ("I didn't find anything wrong with this email. If it asks for "
                "money or personal information, check with someone you trust anyway.")
    lead = {"dangerous": "This email looks like a scam.",
            "suspicious": "Be careful with this email.",
            "safe": "This email is probably fine, but one thing stood out."}[verdict.risk_level]
    # The reasons a person can check with her own eyes first (where a link
    # goes, whose name is on it), the mail-server details last.
    order = ("A link shows", "Name says", "Claims to be", "Replies go to",
             "Money transfer", "SPF check", "DMARC check", "DKIM check")
    ranked = sorted(verdict.indicators, key=lambda i: next(
        (n for n, p in enumerate(order) if i.startswith(p)), len(order)))
    reasons = "; ".join(ranked[:3])
    more = (f" (and {len(ranked) - 3} more)" if len(ranked) > 3 else "")
    action = verdict.recommended_action or (
        "If it asks for money or personal information, check with someone you trust.")
    return f"{lead} What I noticed: {reasons}{more}. {action}"
