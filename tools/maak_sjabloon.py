#!/usr/bin/env python3
"""Maakt het Word-sjabloon uit een van de bestaande .dotx-bestanden.

Het uitgangspunt is dat de huisstijl niet wordt nagebouwd. Een bronbrief bevat
de briefkop, de voettekst, de afbeeldingen, de paginamarges en de stijlen al;
dit script haalt alleen de brieftekst uit de body en zet er de lussen voor in
de plaats die docxtpl invult.

    python3 tools/maak_sjabloon.py
    python3 tools/maak_sjabloon.py --bron "bronbrieven/kanaal enkelvoud.dotx"

Het resultaat is sjablonen/brief.docx. Dat bestand is met opzet niet met de hand
te onderhouden: draai dit script opnieuw als de huisstijl verandert.
"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

# De stijl-id's zoals ze in de bronsjablonen heten. Nederlandstalig, want de
# sjablonen zijn in een Nederlandse Word gemaakt.
STIJL_TEKST = "Standaard"
STIJL_OPSOMMING = "Lijstalinea"

# De lijstdefinitie in numbering.xml die het streepje levert. De bronbrief
# gebruikt er vier (1, 3, 4 en 5) die alleen verschillen in het lettertype van
# het streepje -- onzichtbaar bij een liggend streepje -- dus een volstaat.
LIJST_ID = "3"

# Tekengrootte van de labels "Betreft" en "Meerkerk", in halve punten.
# De brieftekst staat op 18 (9 punt); deze labels op 14 (7 punt).
LABEL_GROOTTE = "14"

CT_SJABLOON = "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
CT_DOCUMENT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def alinea(tekst: str, *, stijl: str | None = None, vet: bool = False,
           onderstreept: bool = False, cursief: str | None = None,
           hangend: int | None = None) -> str:
    """Bouwt één <w:p>. `tekst` mag docxtpl-tags bevatten."""
    eigenschappen = ""
    if stijl or hangend is not None:
        eigenschappen = "<w:pPr>"
        if stijl:
            eigenschappen += f'<w:pStyle w:val="{stijl}"/>'
        if hangend is not None:
            eigenschappen += f'<w:ind w:hanging="{hangend}"/>'
        eigenschappen += "</w:pPr>"
    if not tekst:
        # Met een leeg tekstelement erin, zodat de alinea niet als <w:p />
        # wordt weggeschreven; zie de uitleg bij PARAGRAAFTAG in sjabloon.py.
        return f'<w:p>{eigenschappen}<w:r><w:t xml:space="preserve"></w:t></w:r></w:p>'
    kenmerken = ("<w:b/>" if vet else "") + ('<w:u w:val="single"/>' if onderstreept else "")
    opmaak = f"<w:rPr>{kenmerken}</w:rPr>" if kenmerken else ""
    if cursief:
        # De cursieve blokken -- de uitgangspunten, de garantie en de functie
        # onder de ondertekening -- staan zo in de bronbrieven. Het hele rPr
        # staat in de voorwaarde, zodat een gewone alinea er geen leeg
        # tekstopmaakelement aan overhoudt.
        opmaak += "{% if " + cursief + " %}<w:rPr><w:i/></w:rPr>{% endif %}"
    return (f"<w:p>{eigenschappen}<w:r>{opmaak}"
            f'<w:t xml:space="preserve">{escape(tekst)}</w:t></w:r></w:p>')


def leeg(aantal: int = 1) -> str:
    """Lege alinea's. De bronbrieven gebruiken die voor alle witruimte."""
    return alinea("") * aantal


def opsommingsregel() -> str:
    """Een opsommingsregel met streepje.

    De stijl Lijstalinea zorgt alleen voor de inspringing; het streepje komt uit
    een verwijzing naar een lijstdefinitie in numbering.xml. Zonder die
    verwijzing staat de regel ingesprongen maar zonder teken ervoor.
    """
    return (f'<w:p><w:pPr><w:pStyle w:val="{STIJL_OPSOMMING}"/>'
            f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{LIJST_ID}"/></w:numPr>'
            '</w:pPr><w:r>{% if a.cursief %}<w:rPr><w:i/></w:rPr>{% endif %}'
            '<w:t xml:space="preserve">{{ a.tekst }}</w:t></w:r></w:p>')


def prijsregel() -> str:
    """Een prijsregel: aanloopzin gewoon, bedrag tot en met "netto." vet.

    Twee tekstdelen binnen een alinea, want in de bronbrieven staat alleen het
    bedrag vet en niet de hele zin.
    """
    return (f'<w:p><w:pPr><w:pStyle w:val="{STIJL_TEKST}"/></w:pPr>'
            '<w:r><w:t xml:space="preserve">{{ a.tekst }}</w:t></w:r>'
            '<w:r><w:rPr><w:b/></w:rPr>'
            '<w:t xml:space="preserve">{{ a.nadruk }}</w:t></w:r></w:p>')


def labelregel(hangend: int, inhoud_vet: bool) -> str:
    """Een regel met een klein label, een tab en de inhoud erachter.

    Zo staan de betreft-regel en de regel met plaats en datum in de brieven:
    het label ("Betreft", "Meerkerk") staat op 7 punten en hangt in de marge,
    de inhoud staat op de gewone grootte achter een tab. Zonder dat verschil in
    tekengrootte landt de tab anders en loopt de regel scheef.
    """
    inhoud_opmaak = "<w:rPr><w:b/></w:rPr>" if inhoud_vet else ""
    return (
        f'<w:p><w:pPr><w:ind w:hanging="{hangend}"/></w:pPr>'
        f'<w:r><w:rPr><w:sz w:val="{LABEL_GROOTTE}"/></w:rPr>'
        '<w:t xml:space="preserve">{{ a.tekst }}</w:t></w:r>'
        "{% if a.nadruk %}"
        f'<w:r><w:rPr><w:sz w:val="{LABEL_GROOTTE}"/></w:rPr><w:tab/></w:r>'
        f'<w:r>{inhoud_opmaak}<w:t xml:space="preserve">{{{{ a.nadruk }}}}</w:t></w:r>'
        "{% endif %}"
        "</w:p>"
    )


def sjabloonbody() -> str:
    """De lussen die het sjabloon invullen.

    De kop van de brief is nagemeten aan de bronbrief: het aantal lege alinea's
    boven het adresblok, de inspringing van de betreft-regel en van de regel met
    plaats en datum staan daar zo. De rest loopt door een lus, zodat een nieuwe
    sectie in teksten.yaml geen wijziging in dit sjabloon vergt.
    """
    delen = [
        leeg(4),                                   # ruimte voor de briefkop
        "{%p for a in secties.geadresseerde %}",
        alinea("{{ a.tekst }}"),
        "{%p endfor %}",
        leeg(6),
        "{%p for a in secties.betreft %}",
        labelregel(709, inhoud_vet=True),
        "{%p endfor %}",
        leeg(1),
        "{%p for a in secties.kenmerken %}",
        "{%p if loop.first %}",
        labelregel(851, inhoud_vet=False),
        "{%p else %}",
        alinea("{{ a.tekst }}"),
        "{%p endif %}",
        "{%p if loop.first %}", leeg(1), "{%p endif %}",
        "{%p endfor %}",
        leeg(3),
        "{%p for a in secties.aanhef %}",
        alinea("{{ a.tekst }}"),
        "{%p endfor %}",
        leeg(1),
        # Vanaf hier alle overige secties in volgorde. Drie vormen: een kop, een
        # opsommingsregel en een gewone alinea; de witregel erna bepaalt de motor.
        "{%p for sectie in romp %}",
        "{%p for a in sectie %}",
        "{%p if a.stijl == 'kop' %}",
        alinea("{{ a.tekst }}", onderstreept=True),
        "{%p elif a.stijl == 'kopvet' %}",
        alinea("{{ a.tekst }}", vet=True),
        "{%p elif a.stijl == 'opsomming' %}",
        opsommingsregel(),
        "{%p elif a.stijl == 'prijs' %}",
        prijsregel(),
        "{%p else %}",
        alinea("{{ a.tekst }}", stijl=STIJL_TEKST, cursief="a.cursief"),
        "{%p endif %}",
        "{%p if a.witregel_erna %}", leeg(1), "{%p endif %}",
        "{%p endfor %}",
        "{%p endfor %}",
    ]
    # Een losse {%p ... %} krijgt zijn eigen alinea, zodat hij zelf verdwijnt.
    return "".join(alinea(d) if d.startswith("{%p") else d for d in delen)


def bouw(bron: Path, doel: Path) -> Path:
    with zipfile.ZipFile(bron) as zip_in:
        onderdelen = {naam: zip_in.read(naam) for naam in zip_in.namelist()}

    onderdelen["word/document.xml"] = _vervang_body(onderdelen["word/document.xml"])

    # Een .dotx is een sjabloon; het resultaat moet een gewoon document zijn,
    # anders opent Word het als "nieuw document op basis van".
    types = onderdelen["[Content_Types].xml"].decode("utf-8")
    onderdelen["[Content_Types].xml"] = types.replace(CT_SJABLOON, CT_DOCUMENT).encode("utf-8")

    doel.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(doel, "w", zipfile.ZIP_DEFLATED) as zip_uit:
        for naam, inhoud in onderdelen.items():
            zip_uit.writestr(naam, inhoud)
    return doel


def _vervang_body(document_xml: bytes) -> bytes:
    """Zet de lussen in de body en laat de rest van het bestand ongemoeid.

    Dit gebeurt met tekstbewerking en niet door de XML in te lezen en opnieuw
    weg te schrijven. Het hoofdelement van een Word-document declareert 35
    namespaces en somt er in mc:Ignorable een aantal van op; een XML-lezer
    hernoemt de prefixen die hij zelf niet tegenkomt, waarna mc:Ignorable naar
    prefixen wijst die niet meer bestaan en Word het bestand als beschadigd
    beschouwt. Alles buiten de body blijft daarom byte voor byte gelijk --
    inclusief de verwijzingen naar de briefkop, de voetteksten en titlePg, die
    samen de eerste pagina met de Schilt-gegevens rechtsboven opmaken.
    """
    opening = re.search(rb"<w:body[^>]*>", document_xml)
    if not opening:
        raise SystemExit("geen <w:body> gevonden")
    einde = document_xml.rfind(b"</w:body>")
    if einde == -1:
        raise SystemExit("geen </w:body> gevonden")

    # De sectPr onderaan de body bewaart paginaformaat, marges, titlePg en de
    # verwijzingen naar de kop- en voetteksten. Die moet blijven staan.
    sectpr = document_xml.rfind(b"<w:sectPr", opening.end(), einde)
    staart = document_xml[sectpr:einde] if sectpr != -1 else b""

    return (document_xml[:opening.end()]
            + sjabloonbody().encode("utf-8")
            + staart
            + document_xml[einde:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bron", type=Path, default=Path("bronbrieven/wand enkelvoud.dotx"))
    ap.add_argument("--doel", type=Path, default=Path("sjablonen/brief.docx"))
    keuzes = ap.parse_args()

    if not keuzes.bron.is_file():
        print(f"Bronbestand {keuzes.bron} bestaat niet.")
        return 1

    doel = bouw(keuzes.bron, keuzes.doel)
    with zipfile.ZipFile(doel) as z:
        media = [n for n in z.namelist() if n.startswith("word/media/")]
        koppen = [n for n in z.namelist() if "header" in n or "footer" in n]
    print(f"{doel} gemaakt op basis van {keuzes.bron.name}")
    print(f"  {len(media)} afbeelding(en) en {len(koppen)} kop-/voetteksten meegenomen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
