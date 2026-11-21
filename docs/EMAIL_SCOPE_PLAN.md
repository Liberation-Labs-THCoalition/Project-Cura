# Email in Cura's scope: the plan

**Direction (Thomas, 2026-11-17 10:09, his answer on the Cura calls card, relayed word for word by Nexus):**

> "Let's also make sure email is included and scanned, it's the most common attack surface for seniors."

**Author:** CC (Coalition Code), 2026-11-21. Design calls on this build are CC's (Thomas, 2026-10-01). The consent
and family-visibility steps below are not CC's alone to settle: they rest on Cura's ethics rules ("Ongoing consent,
revocable at any moment"; "Family sees only what elder explicitly authorizes") and need Thomas's and Vera's review
before anything reads a real inbox.

## The goal

Cura watches the place most scams reach her (her email), catches the ones that are lying about who they are, and
tells her in plain words before she clicks, replies or pays. It does that with her consent and keeps only the
verdict, never the mail. Scanning one message someone pastes in is the first step, not the goal.

## Where Cura stood (checked against the code, 2026-11-21)

- `cura/privacy/message_scanner.py` had email and SMS checks (sender patterns, SPF from `Received-SPF`, DKIM
  presence, Return-Path, urgency and money language, URL patterns, brand impersonation). It had **no production
  caller**. Its dangerous verdict said "Cura will alert your caregiver", and its daily summary said messages were
  "blocked" with "Details in the caregiver dashboard". Nothing alerted anyone, nothing blocked mail, and
  `cura/dashboard/` is empty.
- It took the sender, subject and body as separate strings, so it never saw a real message: not the
  `Authentication-Results` her mail server writes, not `Reply-To`, not the display name, not where a link goes
  behind the words it shows.
- `CLAUDE.md` listed "email provenance scanning" under Phase 1 as if it were running.
- On a call, "strange email" is one of the responder's scam phrases, so she can tell Cura about an email out loud.
  Nothing reads the email itself.

## The steps

### E1. One message, read for real (built 2026-11-21, branch `fix/false-alert-sentences`)

- `cura/privacy/email_intake.py::scan_raw_email` reads one RFC 822 message (a saved `.eml`, or a mail program's
  "Show original") with the standard library and hands the scanner all of it: `Authentication-Results`
  (spf, dkim, dmarc), `Reply-To`, the display name, and each link's visible text against its real address.
- New checks in `MessageScanner.scan_email`: her mail server's SPF/DKIM/DMARC failures; replies redirected to
  another domain; a trusted name (Medicare, Social Security, IRS, Amazon, Apple, PayPal) on someone else's address;
  a link that shows one domain and goes to another (scored dangerous on its own).
- Two ways in: `cura scan-email FILE` (prints the verdict in plain words), and the MCP `cura_scam_check` tool's
  new `email` argument. Both read the message in memory, keep only the verdict, write nothing and send nothing.
  Both say nobody was told.
- The scanner's false promises are gone: "Don't click any links or reply. This is likely a scam. Please show it to
  someone you trust before you do anything." The summary says "flagged", never "blocked".
- Tests: `tests/test_email_intake.py` drives `cura scan-email` through `cura.__main__` and `cura_scam_check`
  through the MCP handler with real messages built by the standard library. A sentinel planted in each body must
  appear in no output, nothing may be written to `~/.cura`, and nothing may claim anyone was told.

### E2. Forward-to-Cura (next; no access to her inbox)

She, or someone helping her, forwards a message she is unsure of to Cura's own address, and Cura answers: by reply
email, and on her next call ("The email you sent me that says it's from Medicare isn't from Medicare. Please don't
click anything in it.").

- Needs a mailbox for Cura (an infrastructure call: where it lives, who runs it) and Cura's own credential for it,
  kept out of the config file `cura webhook` reads.
- **Forward as attachment.** An inline forward rewrites the headers, so the provenance checks (SPF, DKIM, DMARC,
  Reply-To) have nothing to read and the scan falls back to content only. The verdict must say which it was.
- Consent is per message: she chooses what to show. This is why E2 comes before E3, not instead of it.

### E3. Watching her inbox (the scan Thomas asked for)

Read-only access to her inbox (the Gmail API's `gmail.readonly` scope, or IMAP opened read-only with `EXAMINE`),
each new message scanned as it arrives, only the verdict kept.

Before it runs on anyone's real mail:

1. **Her consent, recorded and revocable.** Asked during setup in plain words, stored with a date, and revocable
   by voice ("Cura, stop checking my email") as the scanner's own docstring already promises. Nothing implements
   that promise yet.
2. **The credential.** OAuth with a read-only scope where the provider offers one; otherwise an app password. Kept
   outside the config file `cura webhook` reads, never in a log, never sent to anything but the provider.
3. **What is kept.** The verdict only: the sender's domain (the address redacted), the first 50 characters of the
   subject, the indicators. No body, no attachments, no addresses of the people she writes to.
4. **Who is told.** Her first, on her next call, in Cura's voice. The family only for what she has authorized
   (ethics rule: "Family sees only what elder explicitly authorizes"), and only by a path that really reaches them,
   so the false-alert rule holds: Cura says "I told your family" only when it did.
5. **A measured false-alarm rate.** No data yet on how often these checks flag real mail from her bank, her
   pharmacy or Medicare.gov. A warning on a real notice teaches her to ignore warnings. Before E3 runs live: a
   labelled set (public phishing corpora plus real, consented mail) and a stated budget for false alarms.

### E4. Telling her, and acting on it

- A check-in line built from the day's dangerous verdicts (the composer takes enrichments; this is one more).
- A pending question after it ("Did you click anything in it, or give them any information?") through the existing
  `cura/comms/pending.py`, so her answer has somewhere to go.
- If she clicked or paid: the help ladder, through `_promise_help`, so what she hears matches what was done.
- The caregiver summary lists verdicts she authorized, in the summary's honest wording ("flagged", never
  "handled" or "blocked").

### Texts, the same way

Twilio cannot see the texts on her own phone. Texts she forwards to Cura's number can arrive at an inbound-SMS
webhook and go through `MessageScanner.scan_sms`, with the same rules as E2.

## Deferred this round, and why

| Step | Why not this round | Way forward |
| --- | --- | --- |
| E2, Cura's own mailbox | Needs an infrastructure decision and a credential; this round runs locally, with no credentials and no messages. | Infra call (where the mailbox lives), then build the fetch on E1's intake. |
| E3, her inbox | Reads a person's private mail. Needs her consent design and Thomas's and Vera's review first (ethics rules above), plus a real test account. | Consent flow and credential storage spec, reviewed, then a read-only poller on E1's intake. |
| E3's false-alarm measurement | No labelled set exists yet. | Build the set before E3 runs live. |
| E4, telling her on the call | Nothing produces verdicts between calls until E2 or E3 exists. | Composer hook and pending question, once E2 lands. |

None of this narrows the goal. E1 is the part that is safe to build without anyone's mail and without a decision
that is not CC's to make. The goal stays Thomas's: email included and scanned.
