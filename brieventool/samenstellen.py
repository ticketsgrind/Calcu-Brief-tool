"""Zet een ingevuld offerteformulier om in de tekst van een brief.

Per sectie wordt bepaald welke tekstblokken meegaan (op basis van hun
voorwaarde) en worden de {{ }}-plaatshouders ingevuld. Het resultaat is een
woordenboek van sectienaam naar een lijst alinea's, dat het Word-sjabloon
alleen nog hoeft af te lopen. De sectievolgorde volgt analyse/skelet.md.

Blokken die naar `regel` verwijzen worden herhaald: eenmaal per installatie of
per prijsregel. De rest wordt eenmalig beoordeeld.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .bibliotheek import Bibliotheek, Tekstblok
from .bijlage import BijlageFout, tekst_uit_bestand
from .expressies import ExpressieFout, evalueer, is_waar
from .opmaak import FUNCTIES, bedrag, briefdatum, postcode, telwoord

# Welke lijst uit de offerte hoort bij welke herhalende sectie.
LOOPSECTIES = {
    "specificatie": "installaties",
    "buitenunit": "installaties",
    "prijs": "prijsregels",
}

PLAATSHOUDER = re.compile(r"\{\{(.+?)\}\}")


class SamenstelFout(ValueError):
    """De offerte kan niet worden samengesteld."""


@dataclass(frozen=True)
class Alinea:
    """Eén alinea in de brief.

    Word kent geen regelovergang binnen een alinea zoals YAML die schrijft, dus
    een blok van meerdere regels wordt hier opgesplitst. De stijl bepaalt met
    welke Word-opmaak de alinea wordt weggeschreven.
    """
    tekst: str
    # "tekst", "kop" (onderstreept), "kopvet", "opsomming", "prijs" of "label"
    stijl: str = "tekst"
    nadruk: str = ""          # bij "prijs" het bedrag, bij "label" de inhoud
    blok_id: str = ""
    uitgelijnd: bool = False   # vervolgregel die met tabs is uitgelijnd
    cursief: bool = False      # schuingedrukt, zoals de uitgangspunten en de garantie
    los: bool = False          # ook als opsommingsregel een lege regel erna
    letterlijk: bool = False   # regel uit aangeleverde tekst; niets aan wijzigen
    witregel_erna: bool = True

    @property
    def volledig(self) -> str:
        """De hele regel, inclusief het vette staartstuk van een prijsregel.

        `tekst` en `nadruk` staan apart omdat ze in Word twee tekstdelen met
        eigen opmaak worden. Voor alles wat de brief als tekst leest -- de
        controleweergave, de tests -- hoort de regel weer heel te zijn.
        """
        if self.stijl == "label" and self.nadruk:
            return f"{self.tekst}\t{self.nadruk}"
        return self.tekst + self.nadruk

    def __str__(self) -> str:
        return self.volledig


@dataclass
class Brief:
    """Het samengestelde resultaat, klaar voor het Word-sjabloon."""
    secties: dict[str, list[Alinea]] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    gebruikte_blokken: list[str] = field(default_factory=list)
    waarschuwingen: list[str] = field(default_factory=list)

    def tekst(self) -> str:
        """Platte tekst van de hele brief. Handig om snel te controleren."""
        regels: list[str] = []
        for sectie, alineas in self.secties.items():
            if alineas:
                regels.append(f"[{sectie}]")
                regels.extend(a.volledig for a in alineas)
                regels.append("")
        return "\n".join(regels)

    def regels(self, sectie: str) -> list[str]:
        """De tekst van één sectie, als losse regels."""
        return [a.volledig for a in self.secties.get(sectie, [])]

    @property
    def alle_alineas(self) -> list[Alinea]:
        return [a for alineas in self.secties.values() for a in alineas]


def stel_samen(offerte: Mapping[str, Any], bib: Bibliotheek) -> Brief:
    context = _bouw_context(offerte, bib)
    brief = Brief(context=context)

    # Binnen een keuzegroep gaat hoogstens één blok mee: de eerste die past.
    # De volgorde in teksten.yaml is dus de voorrangsvolgorde, met de meest
    # algemene variant onderaan als terugval.
    vergeven_groepen: set[str] = set()

    for sectie in bib.secties:
        alineas: list[Alinea] = []
        lijstnaam = LOOPSECTIES.get(sectie)
        # Prijsregels zijn al opgemaakt in de context; installaties niet.
        regels = list(context.get(lijstnaam) or []) if lijstnaam else []

        for groep, is_herhalend in _groepeer(bib.per_sectie(sectie), bool(lijstnaam)):
            if is_herhalend:
                for nummer, regel in enumerate(regels, start=1):
                    lokaal = dict(context, regel=regel, regelnummer=nummer)
                    for blok in groep:
                        if _meegaan(blok, lokaal, brief):
                            alineas.extend(_naar_alineas(blok, lokaal))
                            _onthoud(brief, blok.id)
            else:
                for blok in groep:
                    if blok.keuzegroep and blok.keuzegroep in vergeven_groepen:
                        continue
                    if _meegaan(blok, context, brief):
                        alineas.extend(_naar_alineas(blok, context))
                        _onthoud(brief, blok.id)
                        if blok.keuzegroep:
                            vergeven_groepen.add(blok.keuzegroep)

        brief.secties[sectie] = _zet_witregels(alineas, sectie)

    return brief


# In de briefkop staat de witruimte vast in het sjabloon (zie sjabloonbody in
# tools/maak_sjabloon.py), nagemeten aan de bronbrieven: het adresblok staat
# aaneengesloten, en onder "Meerkerk <datum>" komt een lege regel waarna project
# no. en Ref. weer tegen elkaar aan staan.
KOPSECTIES_AANEEN = ("geadresseerde", "betreft", "aanhef")

# De werkzaamhedenlijst: de opsommingsregels staan tegen elkaar aan, zonder
# lege regel na de kop erboven -- behalve de kop zelf, die krijgt er wél een.
# Ook tussen de twee koppen ("... inclusief:" -> "Niet tot onze ... behoren:")
# komt geen lege regel, en pas na de allerlaatste opsommingsregel weer wel.
# Op verzoek van Lars (17 september 2026); wijkt af van de bronbrieven, die
# nergens in dit stuk een lege regel zetten.
AANEENGESLOTEN_SECTIES = ("werkzaamheden_inclusief", "werkzaamheden_exclusief")
LAATSTE_AANEENGESLOTEN = "werkzaamheden_exclusief"


def _zet_witregels(alineas: list[Alinea], sectie: str = "") -> list[Alinea]:
    """Bepaalt na welke alinea's een lege regel hoort.

    De bronbrieven zetten een lege alinea na elke gewone alinea, maar niet
    tussen de regels van een opsomming; die staan tegen elkaar aan, met alleen
    een lege regel na de laatste. Zonder dat onderscheid staat de hele brief op
    elkaar gepropt. Hetzelfde geldt voor een uitgelijnde vervolgregel: die hoort
    direct onder de regel waar hij bij hoort.

    De secties van de briefkop volgen het sjabloon: daar zit de witruimte tussen
    de secties en niet tussen de regels.
    """
    if sectie in KOPSECTIES_AANEEN:
        return [replace(alinea, witregel_erna=False) for alinea in alineas]
    if sectie == "kenmerken":
        return [replace(alinea, witregel_erna=(nummer == 0))
                for nummer, alinea in enumerate(alineas)]
    if sectie in AANEENGESLOTEN_SECTIES:
        laatste = len(alineas) - 1
        return [replace(alinea, witregel_erna=(
                    nummer == 0                                     # na de kop
                    or (nummer == laatste and sectie == LAATSTE_AANEENGESLOTEN)))
                for nummer, alinea in enumerate(alineas)]

    uit: list[Alinea] = []
    for nummer, alinea in enumerate(alineas):
        volgende = alineas[nummer + 1] if nummer + 1 < len(alineas) else None
        aaneengesloten = volgende is not None and (
            # Opsommingsregels staan tegen elkaar aan, behalve in een blok dat
            # er zelf een lege regel tussen wil -- zoals de aansprakelijkheid.
            (alinea.stijl == "opsomming" and volgende.stijl == "opsomming"
             and not alinea.los)
            or volgende.uitgelijnd
            or alinea.letterlijk          # de aangeleverde tekst bepaalt zelf zijn witregels
        )
        uit.append(replace(alinea, witregel_erna=not aaneengesloten))
    return uit


def _groepeer(blokken: list[Tekstblok], sectie_herhaalt: bool):
    """Splitst een sectie in aaneengesloten reeksen herhalende en vaste blokken.

    In de specificatie staan kopregel en installatieregel na elkaar; die horen
    samen per installatie herhaald te worden, niet ieder apart over alle
    installaties. In de prijssectie staan de vaste kop en btw-regel eromheen.
    """
    groep: list[Tekstblok] = []
    huidige: bool | None = None
    for blok in blokken:
        herhaalt = sectie_herhaalt and _verwijst_naar_regel(blok)
        if huidige is None or herhaalt == huidige:
            groep.append(blok)
        else:
            yield groep, huidige
            groep = [blok]
        huidige = herhaalt
    if groep:
        yield groep, bool(huidige)


def _onthoud(brief: Brief, blok_id: str) -> None:
    """Houdt bij welke blokken zijn gebruikt, elk hoogstens één keer."""
    if blok_id not in brief.gebruikte_blokken:
        brief.gebruikte_blokken.append(blok_id)


def _meegaan(blok: Tekstblok, context: Mapping[str, Any], brief: Brief | None = None) -> bool:
    """Bepaalt of dit blok in de brief komt.

    Een blok met een omschrijving is een keuze uit een menu. Daar is de keuze
    van de opsteller leidend: staat het blok in `gekozen_blokken`, dan gaat het
    mee. Klopt de voorwaarde daar niet bij -- bijvoorbeeld de particuliere
    factureringsregel op een zakelijke offerte -- dan gaat het blok wél mee maar
    komt er een waarschuwing bij, zodat de fout opvalt vóór de brief de deur uit
    gaat in plaats van erna.
    """
    try:
        voorwaarde_klopt = is_waar(blok.voorwaarde, context, FUNCTIES)
    except ExpressieFout as fout:
        raise SamenstelFout(f"blok {blok.id!r}: {fout}") from fout

    if not blok.is_keuze:
        return voorwaarde_klopt

    gekozen = context.get("gekozen_blokken")
    if gekozen is None:
        return voorwaarde_klopt          # geen keuzelijst: voorwaarde beslist
    if blok.id not in gekozen:
        return False
    if not voorwaarde_klopt and brief is not None:
        _waarschuw(brief, f"blok {blok.id!r} is gekozen maar de voorwaarde "
                          f"{blok.voorwaarde!r} klopt niet voor deze offerte")
    return True


def _waarschuw(brief: Brief, tekst: str) -> None:
    if tekst not in brief.waarschuwingen:
        brief.waarschuwingen.append(tekst)


def _verwijst_naar_regel(blok: Tekstblok) -> bool:
    return "regel." in blok.voorwaarde or "regel." in blok.tekst


# Kopjes die in de bronbrieven vet staan in plaats van onderstreept.
KOPPEN_VET = {"Aanbieding", "Opdracht", "Tot slot", "TECHNISCHE SPECIFICATIES",
              "Technische specificaties", "Uitgangspunten:", "Elektra:"}


def _naar_alineas(blok: Tekstblok, context: Mapping[str, Any]) -> list[Alinea]:
    """Splitst een ingevuld blok in losse alinea's met elk een stijl.

    Word kent geen regelovergang binnen een alinea, dus een blok als
    "Garantietermijn:\n<tekst>" wordt twee alinea's: een kop en een gewone.
    """
    ingevuld = _vul_in(blok, context)
    if not ingevuld:
        return []

    # Aangeleverde tekst -- de technische specificaties -- wordt regel voor
    # regel overgenomen, inclusief de lege regels die er de units mee scheiden.
    if blok.stijl == "letterlijk":
        return [Alinea(tekst=regel.rstrip(), stijl="tekst", blok_id=blok.id,
                       letterlijk=True)
                for regel in ingevuld.split("\n")]

    uit: list[Alinea] = []
    for regel in ingevuld.split("\n"):
        kaal = regel.strip()
        if not kaal:
            continue
        # Een regel die met een tab of een vaste spatie begint is een
        # uitgelijnde vervolgregel van de regel erboven -- zo staan de
        # factureringstermijnen in de brieven. Die uitlijning blijft staan, en
        # een streepje erin is onderdeel van de tekst en geen opsommingsteken.
        uitgelijnd = regel.startswith(("\t", "\u00a0"))
        if uitgelijnd:
            stijl, tekst = "tekst", regel.rstrip()
        elif blok.stijl:
            stijl, tekst = blok.stijl, kaal
        elif kaal.startswith("- "):
            stijl, tekst = "opsomming", kaal[2:].strip()
        elif kaal in KOPPEN_VET:
            stijl, tekst = "kopvet", kaal
        elif _is_kopregel(kaal):
            stijl, tekst = "kop", kaal
        else:
            stijl, tekst = "tekst", kaal
        nadruk = ""
        if stijl == "prijs":
            tekst, nadruk = _splits_bedrag(tekst)
        elif stijl == "label" and "\t" in tekst:
            # "Betreft\tAirconditioning ..." wordt een klein label plus de
            # inhoud erachter; die twee hebben in de brieven eigen opmaak.
            tekst, _, nadruk = tekst.partition("\t")
        # Een blok dat schuingedrukt hoort te staan geeft dat door aan zijn
        # regels, behalve aan de kopregel: in de bronbrieven is geen enkele kop
        # cursief -- die zijn onderstreept of vet.
        uit.append(Alinea(tekst=tekst, stijl=stijl, nadruk=nadruk,
                          blok_id=blok.id, uitgelijnd=uitgelijnd,
                          cursief=blok.cursief and stijl not in ("kop", "kopvet"),
                          los=blok.witregel_tussen))
    return uit


def _splits_bedrag(regel: str) -> tuple[str, str]:
    """Splitst een prijsregel bij het eurobedrag.

    In de bronbrieven staat het bedrag tot en met "netto." vet en de aanloopzin
    niet -- dat is zo in alle acht nagekeken brieven, sjablonen en verstuurde.
    Staat er geen bedrag in, dan blijft de regel in zijn geheel gewoon.
    """
    plek = regel.find("€")
    if plek == -1:
        return regel, ""
    return regel[:plek], regel[plek:]


def _is_kopregel(regel: str) -> bool:
    """Een korte regel die op een dubbele punt eindigt is een sectiekop.

    De grens ligt op 45 tekens omdat de bronbrieven daar de scheiding leggen:
    "Wij specificeren onze aanbieding als volgt:" (42) is een onderstreept
    kopje, "Voor de prijsvorming zijn wij er van uitgegaan dat:" (51) is een
    gewone aanloopzin.
    """
    return regel.endswith(":") and len(regel) <= 45 and ". " not in regel


def _vul_in(blok: Tekstblok, context: Mapping[str, Any]) -> str:
    def vervang(treffer: re.Match[str]) -> str:
        expressie = treffer.group(1).strip()
        try:
            waarde = evalueer(expressie, context, FUNCTIES)
        except ExpressieFout as fout:
            raise SamenstelFout(f"blok {blok.id!r}: {fout}") from fout
        return "" if waarde is None else str(waarde)

    ingevuld = PLAATSHOUDER.sub(vervang, blok.tekst)
    # Waar een plaatshouder leeg blijft ontstaan dubbele spaties. Tabs blijven
    # staan: die lijnen de betreft-regel en de factureringstermijnen uit.
    ingevuld = re.sub(r" {2,}", " ", ingevuld)
    return "\n".join(regel.rstrip() for regel in ingevuld.split("\n")).strip()


# ---------------------------------------------------------------------------
# Afgeleide waarden: alles wat de tool zelf uitrekent en niet gevraagd wordt.
# ---------------------------------------------------------------------------

INSTALLATIE_OMSCHRIJVING = {
    "airconditioning": ("een airconditioninginstallatie", "airconditioninginstallaties"),
    "koelmachine": ("een koelmachine", "koelmachines"),
    "mechanische ventilatie": ("een mechanisch ventilatiesysteem", "mechanische ventilatiesystemen"),
    "warmtepomp": ("een warmtepompinstallatie", "warmtepompinstallaties"),
    "luchtslangsysteem": ("een luchtslangsysteem", "luchtslangsystemen"),
}

BETREFT_ONDERWERP = {
    "airconditioning": "Airconditioning",
    "koelmachine": "Koelmachine",
    "mechanische ventilatie": "Mechanische ventilatie",
    "warmtepomp": "Warmtepomp",
    "luchtslangsysteem": "Luchtslangsysteem",
}

AANHEFVORM = {
    "de heer": "heer",
    "mevrouw": "mevrouw",
    "de heer en mevrouw": "heer en mevrouw",
    "Fam.": "heer en mevrouw",
}


def _bouw_context(offerte: Mapping[str, Any], bib: Bibliotheek) -> dict[str, Any]:
    ctx: dict[str, Any] = dict(offerte)

    installaties = list(offerte.get("installaties") or [])
    prijsregels = list(offerte.get("prijsregels") or [])

    binnen = offerte.get("aantal_binnenunits")
    if binnen is None:
        binnen = sum(_aantallen(i)[0] for i in installaties) or 1
    buiten = offerte.get("aantal_buitenunits")
    if buiten is None:
        buiten = sum(_aantallen(i)[1] for i in installaties) or 1

    ctx["aantal_binnenunits"] = int(binnen)
    ctx["aantal_buitenunits"] = int(buiten)
    ctx["aantal_installaties"] = len(installaties) or 1
    # Staat er bij een installatieregel een eigen opstelling, dan krijgt elke
    # regel zijn eigen zin met de ruimte erbij en vervalt de keuze voor de hele
    # brief. Zo staat het in uitgewerkt-3: de keuken tegen de gevel, de
    # slaapkamer op de grond.
    ctx["opstelling_per_installatie"] = any(
        i.get("opstelling_buitenunit") for i in installaties
    )

    ctx["is_meervoud_binnen"] = ctx["aantal_binnenunits"] > 1
    ctx["is_meervoud_buiten"] = ctx["aantal_buitenunits"] > 1
    ctx["is_meervoud_installatie"] = len(prijsregels) > 1 or len(installaties) > 1

    soort = str(offerte.get("installatietype") or "airconditioning")
    enkel, meer = INSTALLATIE_OMSCHRIJVING.get(soort, (f"een {soort}", f"{soort}en"))
    ctx["installatie_omschrijving"] = meer if ctx["is_meervoud_installatie"] else enkel

    if not offerte.get("betreft_onderwerp"):
        ctx["betreft_onderwerp"] = BETREFT_ONDERWERP.get(soort, soort.capitalize())

    aanspreek = str(offerte.get("aanspreekvorm") or "de heer")
    ctx["aanspreekvorm_aanhef"] = AANHEFVORM.get(aanspreek, aanspreek)
    # Zonder organisatie begint de adresregel met een hoofdletter:
    # "De heer K. ten Broek" in plaats van "T.a.v. de heer ...".
    ctx["aanspreekvorm_hoofdletter"] = aanspreek[:1].upper() + aanspreek[1:]
    # Een tussenvoegsel krijgt een hoofdletter zodra er geen voorletter
    # voor staat: "De heer K. ten Broek" maar "Geachte heer Ten Broek,".
    achternaam = str(offerte.get("achternaam") or "")
    ctx["achternaam_aanhef"] = achternaam[:1].upper() + achternaam[1:]

    ctx["btw_weergave"] = "inclusief" if offerte.get("klanttype") == "particulier" else "exclusief"

    ctx["technische_specificaties_tekst"] = _specificatietekst(offerte)

    ctx["briefdatum"] = briefdatum(offerte.get("briefdatum"))
    if offerte.get("postcode"):
        ctx["postcode"] = postcode(str(offerte["postcode"]))

    ctx["prijsregels"] = [_verrijk_prijsregel(r) for r in prijsregels]
    ctx["installaties"] = installaties

    for veld in ("meerprijs_coating", "meerprijs_ral", "meerprijs_advies", "totaalprijs"):
        if offerte.get(veld) is not None:
            ctx[veld] = bedrag(offerte[veld])

    ondertekenaar_sleutel = offerte.get("ondertekenaar")
    ondertekenaar = bib.ondertekenaars.get(ondertekenaar_sleutel or "", {})
    if ondertekenaar_sleutel and not ondertekenaar:
        raise SamenstelFout(
            f"ondertekenaar {ondertekenaar_sleutel!r} staat niet in config/ondertekenaars.yaml "
            f"(bekend: {', '.join(sorted(bib.ondertekenaars)) or 'geen'})"
        )
    ctx["ondertekenaar"] = ondertekenaar
    ctx["bedrijf"] = bib.bedrijf

    if not offerte.get("referentie") and ondertekenaar.get("initialen"):
        ctx["referentie"] = _stel_referentie_voor(
            ondertekenaar["initialen"], offerte.get("opsteller_initialen"), offerte.get("sa_nummer")
        )

    ctx["telwoord"] = telwoord
    return ctx


def _specificatietekst(offerte: Mapping[str, Any]) -> str:
    """De technische specificaties: zelf ingetypt, of uit een aangeleverd bestand.

    Welke van de twee het is maakt voor de brief niet uit; het gaat om de tekst
    die erin komt. Is er allebei, dan wint de ingetypte tekst -- die heeft de
    opsteller bewust neergezet.
    """
    ingetypt = str(offerte.get("technische_specificaties_tekst") or "").strip()
    if ingetypt:
        return ingetypt

    bestand = offerte.get("technische_specificaties_bestand")
    if not bestand:
        if offerte.get("technische_specificaties") == "uitgeschreven":
            raise SamenstelFout(
                "technische_specificaties staat op 'uitgeschreven', maar er is geen tekst. "
                "Vul technische_specificaties_tekst in of wijs met "
                "technische_specificaties_bestand een bestand aan."
            )
        return ""

    try:
        return tekst_uit_bestand(bestand)
    except BijlageFout as fout:
        raise SamenstelFout(f"technische specificaties: {fout}") from fout


def _aantallen(regel: Mapping[str, Any]) -> tuple[int, int]:
    """Hoeveel binnen- en buitendelen een installatieregel aanbiedt.

    Hier hangt het enkelvoud/meervoud van de hele brief aan: "De binnenunit is"
    tegenover "De binnenunits zijn", en hetzelfde voor de buitenunit.

    Een splitsysteem is per definitie een binnendeel op een buitendeel, dus
    telt daar het aantal systemen. Een multi-split of VRF heeft meerdere
    binnendelen op meestal een buitendeel; staat er een eigen aantal, dan geldt
    dat. Een blijven staan `aantal_binnendelen` van een eerder gekozen
    multi-split telt bij een splitsysteem dus niet mee -- dat gaf eerder "De
    binnenunits zijn" bij een enkele unit.
    """
    systemen = _geheel(regel.get("aantal_systemen"), 1)
    if regel.get("systeemsoort") == "splitsystem":
        return systemen, systemen
    return (_geheel(regel.get("aantal_binnendelen"), systemen),
            _geheel(regel.get("aantal_buitendelen"), systemen))


def _geheel(waarde: Any, terugval: int) -> int:
    try:
        getal = int(str(waarde).strip())
    except (TypeError, ValueError):
        return terugval
    return getal if getal > 0 else terugval


def _verrijk_prijsregel(regel: Mapping[str, Any]) -> dict[str, Any]:
    verrijkt = dict(regel)
    if "bedrag" in verrijkt:
        verrijkt["bedrag"] = bedrag(verrijkt["bedrag"])
    return verrijkt


def _stel_referentie_voor(initialen: str, opsteller: str | None, sa_nummer: Any) -> str:
    """Bouwt Ref. volgens het patroon uit de uitgewerkte brieven.

    <initialen ondertekenaar>/[<initialen opsteller>/]SA<volgnummer>
    Zonder SA-nummer valt dat hele onderdeel weg -- niet "SA" zonder cijfers.
    De teller zelf kennen we niet, dus dat vult de opsteller met de hand in;
    zie analyse/vragen.md vraag 1f. Tot 17 september 2026 stond hier ongeacht
    het veld altijd een "SA" klaar, ook als er nog niets was ingevuld.
    """
    delen = [initialen]
    if opsteller:
        delen.append(str(opsteller))
    if sa_nummer:
        delen.append(f"SA{sa_nummer}")
    return "/".join(delen)
