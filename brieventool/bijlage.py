"""Leest de tekst uit een aangeleverd bestand.

Bedoeld voor de technische specificaties: die komen van de leverancier als
datablad of als een stuk tekst uit een eerdere brief, en horen in de brief zelf
terecht te komen in plaats van als losse bijlage mee te gaan.

Ondersteund: .docx en .dotx (Word), .txt en .md (platte tekst), .pdf.

Dit is met opzet een eenvoudige uitlezer die alleen tekst en tabs oplevert.
tools/extract_docx.py doet hetzelfde uitgebreider -- met stijlen, tabellen en
kop- en voetteksten -- maar dat is voor de analyse van de bronbrieven; hier
gaat het puur om de regels die in de brief moeten komen.
"""

from __future__ import annotations

import re
import zipfile
import zlib
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TEKST_OF_TAB = re.compile(r"<w:t[^>]*>([^<]*)</w:t>|(<w:tab/>)")
# De zelfsluitende <w:p/> staat vooraan: die heeft geen sluittag, dus met de
# andere volgorde loopt het patroon er dwars doorheen en slokt het de lege
# alinea samen met de volgende op.
ALINEA = re.compile(r"<w:p\b[^>]*/>|<w:p\b.*?</w:p>", re.S)

SOORTEN = (".docx", ".dotx", ".txt", ".md", ".pdf")


class BijlageFout(ValueError):
    """Het bestand kan niet worden uitgelezen."""


def tekst_uit_bestand(pad: Path | str) -> str:
    """De tekst uit het bestand, als regels met tabs erin behouden."""
    pad = Path(pad)
    if not pad.is_file():
        raise BijlageFout(f"bestand niet gevonden: {pad}")

    soort = pad.suffix.lower()
    if soort in (".docx", ".dotx"):
        regels = _uit_word(pad)
    elif soort in (".txt", ".md"):
        regels = pad.read_text(encoding="utf-8", errors="replace").splitlines()
    elif soort == ".pdf":
        regels = _uit_pdf(pad)
    else:
        raise BijlageFout(
            f"{pad.name} heeft een soort die ik niet kan lezen ({soort or 'geen extensie'}). "
            f"Ondersteund: {', '.join(SOORTEN)}"
        )

    schoon = [r.rstrip() for r in regels]
    # Lege regels aan het begin en eind weg; ertussen blijven ze staan, want die
    # scheiden in een datablad de binnen- van de buitenunit.
    while schoon and not schoon[0].strip():
        schoon.pop(0)
    while schoon and not schoon[-1].strip():
        schoon.pop()
    if not schoon:
        raise BijlageFout(f"{pad.name} bevat geen tekst")
    return "\n".join(schoon)


def _uit_word(pad: Path) -> list[str]:
    try:
        with zipfile.ZipFile(pad) as bestand:
            xml = bestand.read("word/document.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError) as fout:
        raise BijlageFout(f"{pad.name} is geen leesbaar Word-bestand") from fout

    body = xml[xml.index("<w:body"):] if "<w:body" in xml else xml
    regels = []
    for alinea in ALINEA.findall(body):
        regels.append("".join(t or "\t" for t, _ in TEKST_OF_TAB.findall(alinea)))
    return regels


def _uit_pdf(pad: Path) -> list[str]:
    """Haalt de tekst uit de gecomprimeerde inhoudsstromen van een PDF.

    Geen volwaardige PDF-lezer: goed genoeg voor een datablad met gewone tekst,
    maar bij een gescand blad of een bijzonder lettertype komt er niets bruikbaars
    uit. Dat merkt de gebruiker meteen, want de tekst staat in de brief.
    """
    ruw = pad.read_bytes()
    regels: list[str] = []
    for treffer in re.finditer(rb"stream\r?\n", ruw):
        begin = treffer.end()
        eind = ruw.find(b"endstream", begin)
        if eind < 0:
            continue
        try:
            inhoud = zlib.decompress(ruw[begin:eind])
        except zlib.error:
            continue
        if b"Tj" not in inhoud and b"TJ" not in inhoud:
            continue
        for regel in re.findall(rb"\((?:\\.|[^\\()])*\)", inhoud):
            tekst = regel[1:-1].replace(rb"\(", b"(").replace(rb"\)", b")")
            regels.append(tekst.decode("latin-1"))
    if not regels:
        raise BijlageFout(
            f"uit {pad.name} komt geen tekst. Is het een gescand document? "
            f"Lever het dan als Word-bestand aan, of plak de tekst zelf."
        )
    return regels
