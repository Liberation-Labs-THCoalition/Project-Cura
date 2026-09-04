"""The call that asks after the caregiver.

`CaregiverBurnoutCheck` has existed for weeks: four written messages, a
docstring that says "nobody checks on the checkers", and tests. It is IMPORTED
by checkin_composer.py and never instantiated. The words for "Cura asks after
the father" were written, tested, imported, and never spoken aloud.

It could not be wired before, because Cura had one profile and every call went
to the person being cared for. The caregiver's number existed only to receive
alerts -- he was, structurally, an alarm recipient. The household model is what
makes this callable: he is a member with his own reach, his own cadence, and
his own check-ins.

THE REGISTER IS DIFFERENT and that is the whole point. He is not being cared
for. He is being asked after, by someone who knows what he is carrying. The
elder check-in is a companion; this is a colleague.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CaregiverCheckin:
    lines: list[str] = field(default_factory=list)

    @property
    def all_messages(self) -> list[str]:
        return list(self.lines)


def compose_caregiver_checkin(household, caregiver_id: str, *,
                              rotation: int = 0,
                              medication_questions: list[tuple] | None = None,
                              open_gaps: list[str] | None = None,
                              ) -> CaregiverCheckin:
    """A call TO the caregiver, ABOUT the caregiver.

    Deliberately not a status report with a wellbeing question bolted on. The
    first line asks after him and nothing else; the practical business comes
    after, and only if there is any.

    `medication_questions` comes straight from needs_clarification(), reasons
    and all. `open_gaps` is what Cura is NOT handling -- the household's reportable gaps.
    Telling him is the point: silence is safe for dosing and unsafe for trust,
    and a caregiver who assumes Cura has something covered when it does not is
    worse off than one who was told plainly.
    """
    from cura.pulse.daily_enrichments import CaregiverBurnoutCheck

    m = household.members[caregiver_id]
    cared_for = [household.members[i].display_name
                 for i in m.cares_for if i in household.members]
    subject = cared_for[0] if cared_for else "them"

    burnout = CaregiverBurnoutCheck()
    lines = [burnout.get_checkin_message(m.display_name, subject,
                                         rotation=rotation)]

    # Say the REASON, not a template. needs_clarification already produces a
    # different sentence for each case, and they are genuinely different
    # situations: "I don't know when this is taken" is a gap, whereas "this is
    # as-needed and I wasn't told the interval" means Cura is GUARDING the drug
    # and cannot answer "may I take another". Collapsing them into "I'm not
    # reminding her about these" tells him something false about the first and
    # nothing useful about the second.
    for name, reason in (medication_questions or []):
        lines.append(
            f"One thing when you have a moment — about {subject}'s {name}. "
            f"{reason} Tell me any time and I'll pick it up.")

    for gap in (open_gaps or []):
        lines.append(f"Something you should know: {gap}.")

    lines.append(burnout.spoken_resource())
    return CaregiverCheckin(lines=lines)
