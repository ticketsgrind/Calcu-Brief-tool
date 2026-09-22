"""Zet een samengestelde brief om in een Word-bestand.

Het sjabloon in sjablonen/brief.docx is gemaakt uit een van de bestaande
.dotx-bestanden door tools/maak_sjabloon.py: de briefkop, de voettekst, de
afbeeldingen, de marges en de stijlen zijn die van Schilt zelf. In de body staan
alleen Jinja-lussen, zodat de tekstblokken in analyse/teksten.yaml blijven staan
en niet in een Word-bestand onderhouden hoeven te worden.

Een .docx is een zip met XML, dus invullen komt neer op: het document eruit
halen, er Jinja overheen draaien en het weer inpakken. Daar is geen aparte
Word-bibliotheek voor nodig — die bestaat vooral om tags te repareren die Word
over meerdere tekstdelen verspreidt wanneer je ze met de hand intypt, en ons
sjabloon wordt door een script gemaakt. Voor de zekerheid worden die tekstdelen
alsnog samengevoegd voordat er wordt ingevuld.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from .samenstellen import Brief

DOCUMENT = "word/document.xml"

# Deze secties staan los in het sjabloon omdat ze een eigen plaats of
# inspringing hebben; de rest loopt door één lus.
KOPSECTIES = ("geadresseerde", "betreft", "kenmerken", "aanhef")

# Een alinea die alleen een {%p ... %}-tag bevat verdwijnt zelf uit de brief;
# alleen de tag blijft over. Zo levert een lus geen lege regels op.
#
# De (?<!/) sluit een zelfsluitende <w:p /> uit. Die heeft geen </w:p>, dus
# zonder die uitsluiting zoekt het patroon door in de volgende alinea en
# verdwijnt de lege alinea ertussen — de witregel tussen twee secties.
PARAGRAAFTAG = re.compile(
    r"<w:p\b[^>]*(?<!/)>(?:(?!</w:p>).)*?\{%p(.+?)%\}.*?</w:p>", re.S
)

# De tekstinhoud van een <w:t> bevat nooit andere elementen, dus dit is veilig.
TEKSTELEMENT = re.compile(r"<w:t\b[^>]*>(?P<inhoud>[^<]*)</w:t>")


class SjabloonFout(RuntimeError):
    """Het sjabloon ontbreekt of kan niet worden ingevuld."""


def schrijf_docx(brief: Brief, sjabloon: Path | str, doel: Path | str) -> Path:
    """Vult het Word-sjabloon met de samengestelde brief."""
    sjabloon_pad, doel_pad = Path(sjabloon), Path(doel)
    if not sjabloon_pad.is_file():
        raise SjabloonFout(
            f"sjabloon {sjabloon_pad} bestaat niet. "
            f"Maak het met: python3 tools/maak_sjabloon.py"
        )

    with zipfile.ZipFile(sjabloon_pad) as zip_in:
        onderdelen = {naam: zip_in.read(naam) for naam in zip_in.namelist()}
    if DOCUMENT not in onderdelen:
        raise SjabloonFout(f"{sjabloon_pad} is geen Word-bestand")

    onderdelen[DOCUMENT] = vul_document(onderdelen[DOCUMENT], context(brief))

    doel_pad.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(doel_pad, "w", zipfile.ZIP_DEFLATED) as zip_uit:
        for naam, inhoud in onderdelen.items():
            zip_uit.writestr(naam, inhoud)
    return doel_pad


def vul_document(document_xml: bytes, gegevens: dict[str, Any]) -> bytes:
    """Draait Jinja over word/document.xml en repareert de tabs.

    Bewust zonder XML-lezer. Het hoofdelement van een Word-document declareert
    tientallen namespaces en somt er in mc:Ignorable een aantal van op; opnieuw
    wegschrijven hernoemt prefixen en maakt die opsomming ongeldig, waarna Word
    het bestand als beschadigd beschouwt. Zo blijft alles buiten de body -- de
    briefkop met de Schilt-gegevens, de voetteksten en de afbeeldingen -- gelijk
    aan het sjabloon.
    """
    try:
        from jinja2 import Environment, StrictUndefined
    except ImportError as fout:
        raise SjabloonFout(
            "jinja2 is niet geïnstalleerd. Draai eerst: pip install -r requirements.txt"
        ) from fout

    xml = document_xml.decode("utf-8")
    _controleer_tags(xml)
    xml = PARAGRAAFTAG.sub(lambda treffer: "{%" + treffer.group(1) + "%}", xml)

    omgeving = Environment(autoescape=True, undefined=StrictUndefined,
                           keep_trailing_newline=True)
    try:
        ingevuld = omgeving.from_string(xml).render(**gegevens)
    except Exception as fout:
        raise SjabloonFout(f"het sjabloon kon niet worden ingevuld: {fout}") from fout

    return tabs_naar_word(ingevuld).encode("utf-8")


def _controleer_tags(xml: str) -> None:
    """Waarschuwt als Word een sjabloontag over meerdere tekstdelen heeft geknipt.

    Dat gebeurt zodra iemand sjablonen/brief.docx in Word bewerkt en opslaat.
    Jinja herkent de tag dan niet meer en laat hem stilzwijgend staan, waarna
    de tekst in de brief belandt.
    """
    gebroken = re.search(r"\{[{%][^}%]*?<", xml)
    if gebroken:
        raise SjabloonFout(
            "een sjabloontag is door Word opgeknipt en werkt niet meer. "
            "Maak het sjabloon opnieuw met: python3 tools/maak_sjabloon.py"
        )


def context(brief: Brief) -> dict[str, Any]:
    """De gegevens die het sjabloon te zien krijgt.

    `secties` bevat elke sectie op naam, `romp` de secties die door de grote lus
    lopen: alles behalve de briefkop, en zonder de secties die leeg zijn
    gebleven — die zouden anders een lege regel opleveren.
    """
    gegevens: dict[str, Any] = {
        naam: waarde for naam, waarde in brief.context.items() if not callable(waarde)
    }
    gegevens["secties"] = brief.secties
    gegevens["romp"] = [
        alineas for naam, alineas in brief.secties.items()
        if naam not in KOPSECTIES and alineas
    ]
    return gegevens


def tabs_naar_word(xml: str) -> str:
    """Zet tabtekens in de ingevulde tekst om in echte Word-tabs.

    Een tab die uit de gegevens komt belandt als los teken in een <w:t> en wordt
    door Word als spatie weergegeven. De betreft-regel en de uitlijning van de
    factureringstermijnen hangen daarvan af, dus splitsen we die tekst op in
    <w:t>- en <w:tab>-elementen.
    """
    def splits(treffer: re.Match[str]) -> str:
        inhoud = treffer.group("inhoud")
        if "\t" not in inhoud:
            return treffer.group(0)
        delen: list[str] = []
        for nummer, stuk in enumerate(inhoud.split("\t")):
            if nummer:
                delen.append("<w:tab/>")
            if stuk:
                delen.append(f'<w:t xml:space="preserve">{stuk}</w:t>')
        return "".join(delen)

    return TEKSTELEMENT.sub(splits, xml)
