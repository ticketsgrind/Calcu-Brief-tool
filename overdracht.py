"""Zet een calculatie om in een (deels ingevuld) briefconcept.

Dit is de enige plek waar de twee kanten van de tool elkaar raken. Een paar
regels hierover:

- Dit is een VOORINVULLING van een bewerkbaar concept, nooit een afgeronde
  brief. Alles wat hier wordt ingevuld blijft in stap 2 een gewoon,
  aanpasbaar formulierveld.
- Een veld dat niet met zekerheid uit de calculatie is af te leiden wordt
  NOOIT gegokt en stil ingevuld. Er zijn daarom drie statussen per veld:
  "direct" (een simpele overname, bijv. de datum), "afgeleid" (de tool heeft
  een regel toegepast om tot een waarde te komen, bijv. de systeemsoort-
  vertaling hieronder) en "keuze_nodig" (de calculatie bevat de informatie
  niet om te kiezen; het veld blijft leeg). Alleen "afgeleid" velden krijgen
  een zichtbaar "controleer dit"-label in het scherm -- "keuze_nodig" en
  helemaal niet overgenomen velden lopen gewoon door de bestaande
  controle.ontbrekende_gegevens() (zie brieventool/controle.py), die al
  precies doet wat hier nodig is: nooit stilzwijgend een gat laten staan.
- De verkoopprijs komt rechtstreeks uit calculatie.rekenkern.bereken() (dus
  altijd hetzelfde bedrag als in stap 1 te zien was) -- er wordt in de
  brieventool-kant niets herberekend.

Klantnaam (5 oktober 2026, gevonden door 'm echt te draaien): de calculatie
heeft precies één vrij tekstveld voor de klantnaam, de brief onderscheidt een
organisatie (zakelijke klant) van een persoon (aanspreekvorm/voorletters/
achternaam, ook als contactpersoon bij een zakelijke klant) -- en `klanttype`
bestaat uitsluitend in de brief (zie de btw-uitleg hierboven), dus bij de
EERSTE overdracht staat het nog op zijn standaardwaarde "particulier". Zonder
verdere actie bleef `achternaam` dan op het voorbeeld uit BEGINSTAND staan
("ten Broek") terwijl de echte klantnaam alleen in `organisatie` kwam -- een
veld dat bij klanttype "particulier" nergens in de brief wordt getoond. Live
getest: een calculatie voor "Jansen Vastgoed BV" leverde een brief op die
"De heer K. ten Broek" aanschreef, zonder enige waarschuwing (`achternaam`
was voor `controle.ontbrekende_gegevens()` immers al "gevuld"). Omdat hier
niet te gokken valt of de klant een bedrijf of een privépersoon is, wordt
`achternaam` nu bewust LEEGGEMAAKT zodra er een klantnaam is (status
"keuze_nodig") -- dat maakt dit gat zichtbaar via diezelfde bestaande
ontbrekende-gegevens-controle (achternaam staat al in
`controle.VASTE_VELDEN`) in plaats van een plausibele maar verzonnen naam
onopgemerkt te laten staan.

Systeemsoort-vertaling (afgesproken met Schilt): de calculatietool kent maar
vier grove categorieën (VRF/RAC/PAC/Overig, gebruikt voor de urenformules),
de brief onderscheidt fijner (splitsystem/multi-splitsystem/vrf/warmtepomp/
vloeistofkoelmachine). RAC/PAC met precies 1 binnendeel wordt een
splitsystem, met meer dan 1 een multi-splitsystem -- ook als het in
werkelijkheid meerdere losse splitsystemen in één ruimte zijn in plaats van
één echt multi-systeem; vandaar dat dit altijd als "afgeleid" wordt
gemarkeerd, nooit stilzwijgend overgenomen. VRF wordt vrf. "Overig" kan
zowel warmtepomp als vloeistofkoelmachine zijn en is met de calculatiedata
niet te onderscheiden; dat wordt altijd "keuze_nodig" met beide opties, nooit
een gok tussen de twee.

Model-binnenunit-vertaling (sinds de brieventool-wijziging van 30 september
2026: de systeemomschrijving in de brief kiest voortaan per installatieregel
in plaats van voor de hele brief, zie brieventool/samenstellen.py en
analyse/teksten.yaml). Calculatie se "typeBinnendeel" (Kanaalunit/Casetteunit/
Plafondonderbouw/Wandunit/Vloerunit/Overig, data/systemen.json) is precies
dezelfde montage-categorie als de brief se "model_binnenunit"
(kanaal/cassette/plafondonderbouw/wand/vloer/vrf) -- alleen de spelling en de
taal verschillen, er wordt niets geïnterpreteerd. Daarom "direct", net als
montagewijze hieronder. "Overig" heeft geen eenduidig equivalent in de brief
(geen van de zes brief-modellen dekt het) en blijft daarom "keuze_nodig" met
alle zes opties, nooit een gok.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VeldOverdracht:
    """Beschrijft waar één overgenomen (of juist niet overgenomen) waarde
    vandaan komt, voor de "afgeleid - controleer"-markering in het scherm."""

    pad: str
    status: str  # "direct" | "afgeleid" | "keuze_nodig"
    reden: str
    opties: list[str] | None = None


MONTAGEWIJZE_VERTALING = {
    "Wandmontage": "wandmontage",
    "Plafondinbouwmontage": "plafondinbouwmontage",
    "Vloermontage": "vloermontage",
}

MODEL_BINNENUNIT_VERTALING = {
    "Kanaalunit": "kanaal",
    "Casetteunit": "cassette",
    "Plafondonderbouw": "plafondonderbouw",
    "Wandunit": "wand",
    "Vloerunit": "vloer",
}

OVERIG_OPTIES = ["warmtepomp", "vloeistofkoelmachine"]
RAC_PAC_OPTIES = ["splitsystem", "multi-splitsystem"]
ALLE_SYSTEEMSOORTEN = ["splitsystem", "multi-splitsystem", "vrf", "warmtepomp", "vloeistofkoelmachine"]
ALLE_MODELLEN_BINNENUNIT = ["wand", "cassette", "kanaal", "vloer", "plafondonderbouw", "vrf"]


BTW_PERCENTAGE_PARTICULIER = 0.21


def zet_over(calc_staat: dict[str, Any], berekening: dict[str, Any],
             klanttype: str | None = None) -> tuple[dict[str, Any], list[VeldOverdracht]]:
    """Bouwt een offerte-dict (brieventool-formaat) uit een calculatie-state
    en het bijbehorende resultaat van calculatie.rekenkern.bereken().

    De calculatie rekent altijd exclusief btw (er is geen klanttype-begrip in
    de calculatiestap); `klanttype` komt daarom apart van de briefkant mee,
    zodat bij een particuliere klant de 21% btw bij de verkoopprijs wordt
    opgeteld voordat die in de brief komt -- exact zoals de brief het bedrag
    voor een particulier ook laat zien (btw_inclusief-tekst in teksten.yaml).
    Onbekend/ontbrekend klanttype (bijv. nog niet gekozen) betekent: exclusief
    laten, net als bij een zakelijke klant -- nooit een gok wélke kant op.

    Geeft (offerte, overdracht) terug: `offerte` is direct bruikbaar voor
    brieventool.samenstellen.stel_samen / brieventool.controle.ontbrekende_gegevens,
    `overdracht` is de lijst VeldOverdracht-items voor de "controleer dit"-
    weergave in het scherm.

    Dunne ingang van `zet_meerdere_over()` hieronder, voor het gewone geval van
    precies één calculatie. Zie daar voor de meerdere-opties-variant (twee of
    meer losse calculaties die samen één brief met "pos. A"/"pos. B" moeten
    worden).
    """
    return zet_meerdere_over([(calc_staat, berekening)], klanttype)


def zet_meerdere_over(
    paren: list[tuple[dict[str, Any], dict[str, Any]]],
    klanttype: str | None = None,
) -> tuple[dict[str, Any], list[VeldOverdracht]]:
    """Zoals `zet_over()`, maar voor één of meerdere calculaties tegelijk.

    Elke calculatie in `paren` is een (calc_staat, berekening)-paar, in de
    volgorde waarin ze in de brief moeten komen. Bij precies één paar is de
    uitkomst identiek aan `zet_over()` op dat paar (geen "positie" op de
    prijsregel). Bij meerdere paren wordt elke installatielijst na elkaar
    geplakt (op verzoek van Lars, 29 september 2026: "2 losse calculaties" die
    samen in één brief komen), en krijgt elke prijsregel een positie ("pos.
    A", "pos. B", ...) volgens de volgorde in `paren` -- dat is een al
    bestaand, al werkend mechanisme in de brieftool (zie de
    "+ Prijspositie toevoegen"-knop in scherm/brief.html en het
    prijs_regel_positie-blok in analyse/teksten.yaml), hier alleen automatisch
    ingevuld in plaats van met de hand. Aan het Word-sjabloon of de tekstblokken
    hoeft dus niets te veranderen.

    Projectbrede velden (datum, Q-nummer, klantnaam) komen uitsluitend uit de
    EERSTE calculatie: die velden horen bij het project als geheel, niet bij
    een individuele optie, en in de praktijk deelt een nieuw toegevoegde optie
    die gegevens toch al met de eerste (scherm/calculatie.js vult ze bij het
    aanmaken van een nieuwe optie alvast voor).
    """
    offerte: dict[str, Any] = {}
    overdracht: list[VeldOverdracht] = []
    meerdere_opties = len(paren) > 1

    if paren:
        meta = paren[0][0].get("meta") or {}
        if meta.get("datum"):
            offerte["briefdatum"] = meta["datum"]
            overdracht.append(VeldOverdracht("briefdatum", "direct", "overgenomen uit de projectdatum"))
        if meta.get("qnummer"):
            offerte["projectnummer"] = meta["qnummer"]
            overdracht.append(VeldOverdracht("projectnummer", "direct", "overgenomen uit het Q-nummer"))
        if meta.get("klantnaam"):
            offerte["organisatie"] = meta["klantnaam"]
            overdracht.append(VeldOverdracht(
                "organisatie", "afgeleid",
                "overgenomen uit de klantnaam van de calculatie -- controleer of dit de "
                "bedrijfsnaam is (bij een particuliere klant hoort deze juist leeg te blijven "
                "en de naam bij achternaam/aanspreekvorm)."
            ))
            # A.klanttype staat bij de eerste overdracht nog op zijn standaard
            # "particulier" (de calculatie kent geen klanttype-begrip, zie de
            # btw-uitleg in de moduledocstring) -- zonder onderstaande regel
            # bleef "achternaam" dan gewoon op het voorbeeld uit BEGINSTAND
            # staan ("ten Broek"), want dat veld is al "gevuld" en
            # controle.ontbrekende_gegevens() ziet dus niets mis. Een live
            # test (5 oktober 2026) liet de brief daardoor voor een echte
            # klant "Jansen Vastgoed BV" gewoon "De heer K. ten Broek"
            # aanschrijven -- de echte naam stond wel in organisatie, maar dat
            # blok rendert alleen bij klanttype=='zakelijk'. We kunnen hier
            # niet gokken of dit een bedrijf of een privépersoon is (dat
            # onderscheid bestaat alleen in de brief, niet in de calculatie),
            # dus leeghalen in plaats van zelf raden in welk veld de naam
            # hoort: dat maakt het gat zichtbaar via de bestaande "nog
            # ontbrekende gegevens"-controle (achternaam staat al in
            # controle.VASTE_VELDEN) in plaats van een foute naam onopgemerkt
            # te laten staan.
            offerte["achternaam"] = ""
            overdracht.append(VeldOverdracht(
                "achternaam", "keuze_nodig",
                "de calculatie kent geen onderscheid tussen een zakelijke en een particuliere "
                "klant -- de klantnaam is daarom (nog even) alleen bij 'Organisatie' gezet. Is dit "
                "een particuliere klant: vul hier zelf de achternaam in (en aanspreekvorm/"
                "voorletters). Is het een bedrijf: laat dit leeg of vul de contactpersoon in."
            ))

    offerte_installaties: list[dict[str, Any]] = []
    for calc_staat, _ in paren:
        materiaal_op_id = {m.get("id"): m for m in calc_staat.get("materiaal") or []}
        for installatie in calc_staat.get("installaties") or []:
            index = len(offerte_installaties)
            regel, regel_overdracht = _zet_installatie_over(index, installatie, materiaal_op_id)
            offerte_installaties.append(regel)
            overdracht.extend(regel_overdracht)
    if offerte_installaties:
        offerte["installaties"] = offerte_installaties

    prijsregels: list[dict[str, Any]] = []
    for volgnummer, (_, berekening) in enumerate(paren):
        marge = berekening.get("marge") or {}
        verkoopprijs = marge.get("verkoopprijs")
        if verkoopprijs is None:
            continue
        particulier = klanttype == "particulier"
        bedrag = verkoopprijs * (1 + BTW_PERCENTAGE_PARTICULIER) if particulier else verkoopprijs
        prijsregel: dict[str, Any] = {"bedrag": round(bedrag, 2)}
        if meerdere_opties:
            # A, B, C, ... naar volgorde in `paren` -- niet naar hoeveel
            # prijsregels er uiteindelijk zijn, anders zou een nog niet
            # doorgerekende eerste optie de tweede optie foutief "pos. A" laten
            # heten in plaats van "pos. B".
            prijsregel["positie"] = f"pos. {chr(65 + volgnummer)}"
        prijsregels.append(prijsregel)
        reden = (
            "de verkoopprijs zoals berekend in stap 1 (calculatie), plus 21% btw voor "
            "de particuliere klant -- wordt hier niet herberekend, alleen de btw is erbij opgeteld"
            if particulier else
            "de verkoopprijs zoals berekend in stap 1 (calculatie) -- wordt hier niet herberekend"
        )
        overdracht.append(VeldOverdracht(f"prijsregels[{len(prijsregels) - 1}].bedrag", "direct", reden))

    if prijsregels:
        offerte["prijssoort"] = "totaalprijs"
        offerte["prijsregels"] = prijsregels

    return offerte, overdracht


def _zet_installatie_over(
    index: int, installatie: dict[str, Any], materiaal_op_id: dict[Any, dict[str, Any]]
) -> tuple[dict[str, Any], list[VeldOverdracht]]:
    regel: dict[str, Any] = {}
    overdracht: list[VeldOverdracht] = []
    voorvoegsel = f"installaties[{index}]"

    if installatie.get("merk"):
        regel["merk"] = installatie["merk"]
        overdracht.append(VeldOverdracht(f"{voorvoegsel}.merk", "direct", "overgenomen"))

    montagewijze = MONTAGEWIJZE_VERTALING.get(installatie.get("montagewijze"))
    if montagewijze:
        regel["montagewijze"] = montagewijze
        overdracht.append(VeldOverdracht(f"{voorvoegsel}.montagewijze", "direct", "overgenomen"))

    # Welke systeemomschrijving deze installatieregel in de brief krijgt (zie
    # brieventool/samenstellen.py, _verrijk_installatie, sinds 30 september
    # 2026) -- calculatie se typeBinnendeel is dezelfde montage-categorie,
    # alleen anders gespeld, dus een directe vertaling, geen aanname.
    model_binnenunit = MODEL_BINNENUNIT_VERTALING.get(installatie.get("typeBinnendeel"))
    if model_binnenunit:
        regel["model_binnenunit"] = model_binnenunit
        overdracht.append(VeldOverdracht(f"{voorvoegsel}.model_binnenunit", "direct", "overgenomen"))
    else:
        overdracht.append(VeldOverdracht(
            f"{voorvoegsel}.model_binnenunit", "keuze_nodig",
            f"calculatie-type binnendeel {installatie.get('typeBinnendeel')!r} heeft geen "
            f"eenduidig model binnenunit in de brief -- kies er zelf een",
            opties=ALLE_MODELLEN_BINNENUNIT,
        ))

    # "Type binnendeel" in de brief is een productmodel (bijv. "TZ50"), geen
    # montage-categorie -- calculatie se eigen "typeBinnendeel"-veld
    # (Kanaalunit/Cassetteunit/...) is dat laatste en hoort hier dus NIET meer
    # in te vloeien (deed het eerder wel, zie git-historie/CLAUDE.md: dat gaf
    # een brief met "type Kanaalunit" in plaats van een echt modelnummer). Het
    # echte model staat in de materiaallijst (materiaal_catalogus/Panasonic/
    # Daikin) zodra dat via de zoekbalk is toegevoegd; `installatie.materiaalId`
    # (scherm/calculatie.js, het nieuwe "Model (uit materiaallijst)"-veld) is
    # de expliciete koppeling die de gebruiker daar zelf legt -- geen gok,
    # gewoon een keuze die is doorgegeven.
    materiaal_item = materiaal_op_id.get(installatie.get("materiaalId"))
    model = (materiaal_item or {}).get("artikelcode") or (materiaal_item or {}).get("omschrijving")
    if model:
        regel["type_binnendeel"] = model
        overdracht.append(VeldOverdracht(
            f"{voorvoegsel}.type_binnendeel", "direct",
            "overgenomen van het gekoppelde artikel in de materiaallijst"
        ))
    else:
        overdracht.append(VeldOverdracht(
            f"{voorvoegsel}.type_binnendeel", "keuze_nodig",
            "geen materiaalregel gekoppeld in de calculatie (of de koppeling wijst nergens meer "
            "naartoe) -- vul het modelnummer hier zelf in, of koppel bij Installaties in de "
            "calculatie een artikel uit de materiaallijst"
        ))

    aantal_buiten = installatie.get("aantalBuitendelen")
    aantal_binnen = installatie.get("aantalBinnendelen")
    if aantal_buiten:
        regel["aantal_buitendelen"] = aantal_buiten
    if aantal_binnen:
        regel["aantal_binnendelen"] = aantal_binnen

    status, waarde, opties = _systeemsoort_voor(installatie)
    if status == "afgeleid":
        regel["systeemsoort"] = waarde
        if waarde == "splitsystem":
            # _aantallen() in samenstellen.py telt bij een splitsystem-regel
            # alleen aantal_systemen, niet aantal_binnendelen/aantal_buitendelen
            # -- dus die moet hier expliciet mee, anders valt de regel terug op
            # de standaardwaarde 1 los van wat er in de calculatie stond.
            regel["aantal_systemen"] = 1
        overdracht.append(VeldOverdracht(
            f"{voorvoegsel}.systeemsoort", "afgeleid",
            f"afgeleid van calculatie-systeemsoort {installatie.get('systeemsoort')!r} "
            f"en het aantal binnendelen -- controleer of dit klopt"
        ))
    else:
        overdracht.append(VeldOverdracht(
            f"{voorvoegsel}.systeemsoort", "keuze_nodig",
            f"calculatie-systeemsoort {installatie.get('systeemsoort')!r} kan meerdere dingen "
            f"betekenen in de brief -- kies er zelf een",
            opties=opties,
        ))

    return regel, overdracht


def _systeemsoort_voor(installatie: dict[str, Any]) -> tuple[str, str | None, list[str] | None]:
    """(status, waarde, opties) -- zie de moduledocstring voor de regels."""
    soort = installatie.get("systeemsoort")

    if soort == "VRF":
        return "afgeleid", "vrf", None

    if soort in ("RAC", "PAC"):
        aantal = _geheel_of_niets(installatie.get("aantalBinnendelen"))
        if aantal is None or aantal < 1:
            return "keuze_nodig", None, RAC_PAC_OPTIES
        return "afgeleid", ("splitsystem" if aantal == 1 else "multi-splitsystem"), None

    if soort == "Overig":
        return "keuze_nodig", None, OVERIG_OPTIES

    return "keuze_nodig", None, ALLE_SYSTEEMSOORTEN


def _geheel_of_niets(waarde: Any) -> int | None:
    try:
        return int(waarde)
    except (TypeError, ValueError):
        return None
