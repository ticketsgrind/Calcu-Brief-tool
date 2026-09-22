"""Haalt het briefpapier uit het sjabloon, zodat het scherm het kan tonen.

De voorvertoning liet eerst een zelfbedachte kop zien. Dat wekt de indruk dat de
brief er zo uit gaat zien, terwijl het Word-bestand de echte briefkop van Schilt
gebruikt. Deze module leest dus uit het sjabloon wat er werkelijk op papier komt:
het paginaformaat, de marges, de gegevens rechtsboven, de voettekst en de
afbeeldingen.

Wat een browser niet kan tonen is een EMF-afbeelding; die komt wel in het
Word-bestand maar niet in de voorvertoning. Dat staat als `onbekende_beelden` in
het resultaat, zodat het scherm het kan melden in plaats van het stil weg te
laten.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TWIPS_PER_MM = 1440 / 25.4
EMU_PER_MM = 36000

# Beeldsoorten die een browser rechtstreeks kan tonen.
TOONBAAR = {".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".svg": "image/svg+xml"}


class BriefpapierFout(RuntimeError):
    """Het sjabloon ontbreekt of bevat geen briefkop."""


def lees(sjabloon: Path | str) -> dict:
    """Alles wat het scherm nodig heeft om de eerste pagina na te bootsen."""
    pad = Path(sjabloon)
    if not pad.is_file():
        raise BriefpapierFout(f"sjabloon {pad} bestaat niet")

    with zipfile.ZipFile(pad) as bestand:
        onderdelen = {naam: bestand.read(naam) for naam in bestand.namelist()}

    document = onderdelen["word/document.xml"].decode("utf-8")
    kopnaam = _onderdeel_voor(document, onderdelen, "headerReference", "first")
    voetnaam = _onderdeel_voor(document, onderdelen, "footerReference", "first")

    onbekend: list[str] = []
    return {
        "pagina": _pagina(document),
        "kop": _deel(onderdelen, kopnaam, onbekend),
        "voet": _deel(onderdelen, voetnaam, onbekend),
        "onbekende_beelden": sorted(set(onbekend)),
    }


def beeld(sjabloon: Path | str, naam: str) -> tuple[bytes, str]:
    """De bytes van één afbeelding uit het sjabloon, met het mediatype."""
    veilig = Path(naam).name                      # geen paden naar buiten het sjabloon
    soort = TOONBAAR.get(Path(veilig).suffix.lower())
    if not soort:
        raise BriefpapierFout(f"{veilig} is geen beeldsoort die een browser toont")
    with zipfile.ZipFile(Path(sjabloon)) as bestand:
        try:
            return bestand.read(f"word/media/{veilig}"), soort
        except KeyError as fout:
            raise BriefpapierFout(f"{veilig} zit niet in het sjabloon") from fout


# ---------------------------------------------------------------------------

def _pagina(document: str) -> dict:
    body = ET.fromstring(document).find(W + "body")
    sect = body.find(W + "sectPr") if body is not None else None
    if sect is None:
        raise BriefpapierFout("het sjabloon heeft geen paginainstellingen")

    formaat = sect.find(W + "pgSz")
    marge = sect.find(W + "pgMar")
    mm = lambda waarde: round(int(waarde) / TWIPS_PER_MM, 1)
    return {
        "breedte": mm(formaat.get(W + "w")), "hoogte": mm(formaat.get(W + "h")),
        "boven": mm(marge.get(W + "top")), "onder": mm(marge.get(W + "bottom")),
        "links": mm(marge.get(W + "left")), "rechts": mm(marge.get(W + "right")),
        "kop_vanaf": mm(marge.get(W + "header")), "voet_vanaf": mm(marge.get(W + "footer")),
    }


def _onderdeel_voor(document: str, onderdelen: dict, soort: str, type_: str) -> str | None:
    """Zoekt via de verwijzing in sectPr welk bestand de kop of voet bevat."""
    verwijzing = re.search(rf'<w:{soort}[^>]*w:type="{type_}"[^>]*r:id="(\w+)"', document)
    if not verwijzing:
        return None
    rels = onderdelen.get("word/_rels/document.xml.rels", b"").decode("utf-8")
    doel = re.search(rf'Id="{verwijzing.group(1)}"[^>]*Target="([^"]+)"', rels)
    return f"word/{doel.group(1)}" if doel else None


def _deel(onderdelen: dict, naam: str | None, onbekend: list[str]) -> dict:
    """De tekstregels en afbeeldingen van een kop- of voettekst."""
    if not naam or naam not in onderdelen:
        return {"regels": [], "beelden": []}
    xml = onderdelen[naam].decode("utf-8")
    rels = onderdelen.get(f"word/_rels/{Path(naam).name}.rels", b"").decode("utf-8")
    verwijzingen = dict(re.findall(r'Id="(\w+)"[^>]*Target="([^"]+)"', rels))

    regels = []
    for alinea in ET.fromstring(xml).iter(W + "p"):
        tekst = "".join(t.text or "" for t in alinea.iter(W + "t"))
        # "C2-Vertrouwelijk" is de classificatiemarkering van Word, geen
        # brieftekst; die hoort niet in de voorvertoning. Zie vragen.md vraag 19.
        tekst = tekst.replace("C2-Vertrouwelijk", "").strip()
        if tekst:
            regels.append(tekst)

    beelden = []
    for anker in re.findall(r"<wp:anchor\b.*?</wp:anchor>|<wp:inline\b.*?</wp:inline>", xml, re.S):
        naar = re.search(r'r:embed="(\w+)"', anker)
        omvang = re.search(r'<wp:extent cx="(\d+)" cy="(\d+)"', anker)
        if not (naar and omvang):
            continue
        doel = Path(verwijzingen.get(naar.group(1), "")).name
        if not doel:
            continue
        if Path(doel).suffix.lower() not in TOONBAAR:
            onbekend.append(doel)
            continue
        beeld_gegevens = {
            "naam": doel,
            "breedte": round(int(omvang.group(1)) / EMU_PER_MM, 1),
            "hoogte": round(int(omvang.group(2)) / EMU_PER_MM, 1),
        }
        for as_, patroon in (("links", "positionH"), ("boven", "positionV")):
            plek = re.search(rf'<wp:{patroon} relativeFrom="(\w+)">\s*<wp:posOffset>(-?\d+)',
                             anker, re.S)
            if plek:
                beeld_gegevens[as_] = round(int(plek.group(2)) / EMU_PER_MM, 1)
                beeld_gegevens[as_ + "_vanaf"] = plek.group(1)
        if not any(b["naam"] == doel and b.get("links") == beeld_gegevens.get("links")
                   and b.get("boven") == beeld_gegevens.get("boven") for b in beelden):
            beelden.append(beeld_gegevens)
    return {"regels": regels, "beelden": beelden}
