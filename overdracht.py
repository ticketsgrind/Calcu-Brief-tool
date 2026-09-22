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

OVERIG_OPTIES = ["warmtepomp", "vloeistofkoelmachine"]
RAC_PAC_OPTIES = ["splitsystem", "multi-splitsystem"]
ALLE_SYSTEEMSOORTEN = ["splitsystem", "multi-splitsystem", "vrf", "warmtepomp", "vloeistofkoelmachine"]


def zet_over(calc_staat: dict[str, Any], berekening: dict[str, Any]) -> tuple[dict[str, Any], list[VeldOverdracht]]:
    """Bouwt een offerte-dict (brieventool-formaat) uit een calculatie-state
    en het bijbehorende resultaat van calculatie.rekenkern.bereken().

    Geeft (offerte, overdracht) terug: `offerte` is direct bruikbaar voor
    brieventool.samenstellen.stel_samen / brieventool.controle.ontbrekende_gegevens,
    `overdracht` is de lijst VeldOverdracht-items voor de "controleer dit"-
    weergave in het scherm.
    """
    offerte: dict[str, Any] = {}
    overdracht: list[VeldOverdracht] = []

    meta = calc_staat.get("meta") or {}
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

    offerte_installaties: list[dict[str, Any]] = []
    for index, installatie in enumerate(calc_staat.get("installaties") or []):
        regel, regel_overdracht = _zet_installatie_over(index, installatie)
        offerte_installaties.append(regel)
        overdracht.extend(regel_overdracht)
    if offerte_installaties:
        offerte["installaties"] = offerte_installaties

    marge = berekening.get("marge") or {}
    verkoopprijs = marge.get("verkoopprijs")
    if verkoopprijs is not None:
        offerte["prijssoort"] = "totaalprijs"
        offerte["prijsregels"] = [{"bedrag": round(verkoopprijs, 2)}]
        overdracht.append(VeldOverdracht(
            "prijsregels[0].bedrag", "direct",
            "de verkoopprijs zoals berekend in stap 1 (calculatie) -- wordt hier niet herberekend"
        ))

    return offerte, overdracht


def _zet_installatie_over(index: int, installatie: dict[str, Any]) -> tuple[dict[str, Any], list[VeldOverdracht]]:
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

    if installatie.get("typeBinnendeel"):
        regel["type_binnendeel"] = installatie["typeBinnendeel"]
        overdracht.append(VeldOverdracht(f"{voorvoegsel}.type_binnendeel", "direct", "overgenomen"))

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
