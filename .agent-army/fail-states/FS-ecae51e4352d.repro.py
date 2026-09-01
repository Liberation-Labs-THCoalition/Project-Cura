"""FS-ecae51e4352d — REJECTED. An apostrophe in a spoken name does not break TwiML.

Investigated alongside FS-2b702d758df4 (unescaped ampersands, which is a real
defect). An apostrophe is legal character data inside an XML element, so
"Margaret O'Brien" produces a well-formed document. Only &, < and > break it.
Kept so the next audit does not re-run the apostrophe case.
"""
import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_apostrophe_in_a_name_is_well_formed():
    from cura.comms.voice import CuraVoice
    twiml = CuraVoice()._build_twiml(
        ["Good morning, Margaret O'Brien.", "I didn't hear you."], gather=True)
    ET.fromstring(twiml)
