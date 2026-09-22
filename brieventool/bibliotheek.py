"""Laadt de tekstblokkenbibliotheek en de ondertekenaars.

De bibliotheek staat bewust niet in de code maar in analyse/teksten.yaml, zodat
een gewijzigde garantietekst geen nieuwe versie van de tool vergt.

Op een werkplek wijst BRIEVENTOOL_BIBLIOTHEEK naar een gedeelde map, bijvoorbeeld
een gesynchroniseerde OneDrive-map. Zo hebben alle collega's dezelfde teksten,
ook al draait de tool lokaal.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

OMGEVINGSVARIABELE = "BRIEVENTOOL_BIBLIOTHEEK"


class BibliotheekFout(ValueError):
    """De bibliotheek ontbreekt of klopt niet."""


@dataclass(frozen=True)
class Tekstblok:
    id: str
    sectie: str
    tekst: str
    voorwaarde: str = ""
    omschrijving: str = ""
    keuzegroep: str = ""   # binnen één groep gaat hoogstens één blok mee
    stijl: str = ""        # "opsomming" of "kop"; leeg = gewone alinea
    cursief: bool = False  # schuingedrukt in de brief; koppen blijven recht
    witregel_tussen: bool = False   # ook tussen opsommingsregels een lege regel
    bron: str = ""
    notitie: str = ""      # interne aantekening; komt nooit in de brief

    @property
    def is_keuze(self) -> bool:
        """Blokken met een omschrijving verschijnen als keuze in het formulier."""
        return bool(self.omschrijving)


@dataclass
class Bibliotheek:
    blokken: list[Tekstblok]
    ondertekenaars: dict[str, dict[str, Any]] = field(default_factory=dict)
    opstellers: dict[str, Any] = field(default_factory=dict)
    bedrijf: dict[str, Any] = field(default_factory=dict)

    def per_sectie(self, sectie: str) -> list[Tekstblok]:
        return [b for b in self.blokken if b.sectie == sectie]

    def zoek(self, blok_id: str) -> Tekstblok:
        for blok in self.blokken:
            if blok.id == blok_id:
                return blok
        raise BibliotheekFout(f"tekstblok {blok_id!r} bestaat niet")

    @property
    def secties(self) -> list[str]:
        gezien: list[str] = []
        for blok in self.blokken:
            if blok.sectie not in gezien:
                gezien.append(blok.sectie)
        return gezien

    def keuzes(self, sectie: str) -> list[tuple[str, str]]:
        """(id, label) voor het keuzemenu van één sectie."""
        return [(b.id, b.omschrijving) for b in self.per_sectie(sectie) if b.is_keuze]

    def velden(self) -> "VeldOpties":
        """Leidt uit de voorwaarden van alle keuzeblokken af welke gewone
        antwoordvelden er bestaan, met welke waarden en welk label erbij hoort.

        Dit voorkomt dat het formulier de mogelijke waarden van bijvoorbeeld
        `facturering` of `condensafvoer` hardcodeert: die vocabulaire staat al
        in analyse/teksten.yaml (elk blok is precies één antwoordwaarde) en
        moet daar de enige plek blijven waar hij verandert. Zie ook de regel
        in CLAUDE.md dat de inhoud niet in de code hoort te zitten."""
        return _velden_uit_blokken(self.blokken)


@dataclass
class VeldOpties:
    """Resultaat van Bibliotheek.velden(): drie soorten gewone (niet-installatie-,
    niet-blok-id-gebonden) antwoordvelden, afgeleid uit de voorwaarden zelf."""
    enkele_keuze: dict[str, list[tuple[str, str]]] = field(default_factory=dict)   # veld -> [(waarde, label)]
    meervoudige_keuze: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # veld -> [(waarde, label)]
    vinkjes: dict[str, str] = field(default_factory=dict)                          # veld -> label


# Velden die wel in een voorwaarde voorkomen maar geen zelfstandig antwoord zijn:
# afgeleide/interne vlaggen (opstelling_per_installatie, aantal_*) of velden die
# het formulier al met een eigen, specifiek invulveld behandelt (klanttype,
# installatietype -- die sturen te veel andere velden om generiek te doen).
_GEEN_ANTWOORDVELD = {"opstelling_per_installatie", "aantal_binnenunits",
                      "aantal_buitenunits", "klanttype", "installatietype"}

_GELIJKHEID = re.compile(r"^(\w+)\s*==\s*'([^']*)'$")
_LIDMAATSCHAP = re.compile(r"^'([^']*)'\s+in\s+(\w+)$")
_VLAG = re.compile(r"^(\w+)$")


def _velden_uit_blokken(blokken: list["Tekstblok"]) -> VeldOpties:
    enkele: dict[str, dict[str, str]] = {}
    meervoudig: dict[str, dict[str, str]] = {}
    vinkjes: dict[str, str] = {}

    for blok in blokken:
        if not blok.omschrijving:
            continue
        for deel in blok.voorwaarde.split(" and "):
            deel = deel.strip()
            if deel.startswith("not ") or deel.startswith("regel."):
                continue  # een negatie van een interne vlag, of een installatieveld

            treffer = _GELIJKHEID.match(deel)
            if treffer and treffer.group(1) not in _GEEN_ANTWOORDVELD:
                enkele.setdefault(treffer.group(1), {}).setdefault(treffer.group(2), blok.omschrijving)
                continue

            treffer = _LIDMAATSCHAP.match(deel)
            if treffer and treffer.group(2) not in _GEEN_ANTWOORDVELD:
                meervoudig.setdefault(treffer.group(2), {}).setdefault(treffer.group(1), blok.omschrijving)
                continue

            treffer = _VLAG.match(deel)
            if treffer and treffer.group(1) not in _GEEN_ANTWOORDVELD:
                vinkjes.setdefault(treffer.group(1), blok.omschrijving)

    return VeldOpties(
        enkele_keuze={veld: list(opties.items()) for veld, opties in enkele.items()},
        meervoudige_keuze={veld: list(opties.items()) for veld, opties in meervoudig.items()},
        vinkjes=vinkjes,
    )


def standaardmap() -> Path:
    """De map met teksten.yaml: uit de omgevingsvariabele, anders naast de code."""
    vanuit_omgeving = os.environ.get(OMGEVINGSVARIABELE)
    if vanuit_omgeving:
        return Path(vanuit_omgeving).expanduser()
    return Path(__file__).resolve().parent.parent


def laad(map_pad: Path | str | None = None) -> Bibliotheek:
    wortel = Path(map_pad) if map_pad else standaardmap()

    teksten_pad = _eerste_bestaande(wortel, "analyse/teksten.yaml", "teksten.yaml")
    if teksten_pad is None:
        raise BibliotheekFout(
            f"teksten.yaml niet gevonden onder {wortel}. "
            f"Zet {OMGEVINGSVARIABELE} op de map waar de bibliotheek staat."
        )

    rauw = yaml.safe_load(teksten_pad.read_text(encoding="utf-8")) or {}
    blokken = [_naar_blok(item, teksten_pad) for item in (rauw.get("blokken") or [])]
    _controleer_unieke_ids(blokken, teksten_pad)

    bib = Bibliotheek(blokken=blokken)

    onder_pad = _eerste_bestaande(wortel, "config/ondertekenaars.yaml", "ondertekenaars.yaml")
    if onder_pad is not None:
        onder = yaml.safe_load(onder_pad.read_text(encoding="utf-8")) or {}
        bib.ondertekenaars = onder.get("ondertekenaars") or {}
        bib.opstellers = onder.get("opstellers") or {}
        bib.bedrijf = onder.get("bedrijf") or {}

    return bib


def _eerste_bestaande(wortel: Path, *relatieve_paden: str) -> Path | None:
    for pad in relatieve_paden:
        kandidaat = wortel / pad
        if kandidaat.is_file():
            return kandidaat
    return None


def _naar_blok(item: dict, herkomst: Path) -> Tekstblok:
    ontbreekt = [v for v in ("id", "sectie", "tekst") if not item.get(v)]
    if ontbreekt:
        raise BibliotheekFout(
            f"blok in {herkomst.name} mist {', '.join(ontbreekt)}: {item.get('id', item)!r}"
        )
    return Tekstblok(
        id=item["id"],
        sectie=item["sectie"],
        tekst=str(item["tekst"]).rstrip("\n"),
        voorwaarde=item.get("voorwaarde") or "",
        omschrijving=item.get("omschrijving") or "",
        keuzegroep=item.get("keuzegroep") or "",
        stijl=item.get("stijl") or "",
        cursief=bool(item.get("cursief")),
        witregel_tussen=bool(item.get("witregel_tussen")),
        bron=item.get("bron") or "",
        notitie=item.get("notitie") or "",
    )


def _controleer_unieke_ids(blokken: list[Tekstblok], herkomst: Path) -> None:
    gezien: set[str] = set()
    dubbel = sorted({b.id for b in blokken if b.id in gezien or gezien.add(b.id)})
    if dubbel:
        raise BibliotheekFout(f"dubbele blok-id's in {herkomst.name}: {', '.join(dubbel)}")
