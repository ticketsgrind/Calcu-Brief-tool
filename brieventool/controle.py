"""Kijkt of er nog gaten in de brief vallen voordat er een Word-bestand komt.

De tool vulde een ontbrekend antwoord stilzwijgend in als niets. Dat levert
zinnen op die er af uitzien maar het niet zijn:

    De totaalprijs compleet geleverd en gemonteerd bedraagt netto.
    Ons project no.
    Betreft   Airconditioning t.b.v.

Op het scherm valt dat op; in een verstuurde brief niet meer. Deze module
noemt daarom bij naam wat er nog mist. De voorvertoning blijft gewoon werken --
je moet kunnen meelezen terwijl je invult -- maar het Word-bestand komt er pas
als de brief compleet is.

Elke controle hieronder staat er omdat het gat is nagemeten: het lege veld is
teruggevonden in de samengestelde brief.
"""

from __future__ import annotations

from typing import Any, Mapping

# veld -> hoe het in de melding heet. De volgorde is die van de brief zelf.
VASTE_VELDEN: list[tuple[str, str]] = [
    ("achternaam", "de achternaam"),                    # adresblok en aanhef
    ("straat_huisnummer", "straat en huisnummer"),      # adresblok
    ("postcode", "de postcode"),                        # adresblok
    ("plaats", "de plaats"),                            # adresblok
    ("locatieaanduiding", "de betreft-regel"),          # "Airconditioning t.b.v. ..."
    ("projectnummer", "het projectnummer"),             # "Ons project no."
    ("sa_nummer", "het SA-nummer"),                     # "Ref. NV/LH/SA..."
]

# veld -> hoe het in de melding heet. De ruimte staat er niet bij; die heeft
# een eigen regel, want met een eigen kopregel is hij niet nodig.
#
# systeemsoort staat erbij sinds de calculatie-koppeling: zonder systeemsoort
# matcht geen enkel blok in de sectie "systeemomschrijving" (elk blok daar
# heeft een voorwaarde als "regel.systeemsoort == 'splitsystem'"), en die
# installatieregel krijgt dan stilzwijgend geen omschrijvingsalinea. Dat gat
# viel niet op zolang het formulier nog niet bestond en elke offerte met de
# hand in YAML werd geschreven; met een formulier waar dit veld vergeten kan
# worden moet die controle er staan, net als bij merk en type binnendeel.
INSTALLATIEVELDEN: list[tuple[str, str]] = [
    ("systeemsoort", "de systeemsoort"),
    ("merk", "het merk"),
    ("type_binnendeel", "het type binnendeel"),
]


def ontbrekende_gegevens(offerte: Mapping[str, Any]) -> list[str]:
    """De dingen die nog ingevuld moeten worden, in leesbare bewoording."""
    ontbreekt: list[str] = []

    for veld, omschrijving in VASTE_VELDEN:
        if not _gevuld(offerte.get(veld)):
            ontbreekt.append(omschrijving)

    # Elke aanleidingszin noemt een datum ("d.d. 20 maart jl."), bij een gesprek
    # met een adviseur ook diens naam, en bij een opdrachtbevestiging het
    # opdrachtnummer ("uw schriftelijke opdrachtnr. ...").
    if not _gevuld(offerte.get("datum_aanleiding")):
        ontbreekt.append("de datum van de aanleiding")
    if offerte.get("aanleiding") == "onderhoud" and not _gevuld(offerte.get("adviseur")):
        ontbreekt.append("de naam van de adviseur")
    if offerte.get("aanleiding") == "opdrachtbevestiging" \
            and not _gevuld(offerte.get("opdrachtnummer")):
        ontbreekt.append("het opdrachtnummer")

    # Zonder bedrag blijft er "bedraagt netto." staan.
    prijsregels = offerte.get("prijsregels") or []
    if not any(_gevuld(regel.get("bedrag")) for regel in prijsregels if isinstance(regel, Mapping)):
        ontbreekt.append("het bedrag")

    installaties = offerte.get("installaties") or []
    if not installaties:
        ontbreekt.append("een installatie")
    for nummer, installatie in enumerate(installaties, start=1):
        if not isinstance(installatie, Mapping):
            continue
        erbij = f" van regel {nummer}" if len(installaties) > 1 else ""
        # De ruimte mag leeg blijven: zonder ruimte en zonder eigen kopregel
        # komt er gewoon geen kopregel boven de installatie te staan, en dat is
        # geen gat. Alleen een eigen opstelling per regel noemt de ruimte bij
        # naam ("De buitenunit voor <ruimte> wordt geplaatst ..."); dan wel.
        if _gevuld(installatie.get("opstelling_buitenunit")) \
                and not _gevuld(installatie.get("ruimte")):
            ontbreekt.append("de ruimte" + erbij)
        for veld, omschrijving in INSTALLATIEVELDEN:
            if not _gevuld(installatie.get(veld)):
                ontbreekt.append(omschrijving + erbij)
        # Een multi-split of VRF noemt het buitendeel apart; een splitsysteem
        # heeft er in de brief geen eigen regel voor.
        if installatie.get("systeemsoort") in ("multi-splitsystem", "vrf") \
                and not _gevuld(installatie.get("type_buitendeel")):
            ontbreekt.append("het type buitendeel" + erbij)

    # Staat de inhoud in de brief zelf, dan moet die er ook zijn. Zonder tekst
    # loopt stel_samen vast; zo is de melding gelijk aan de andere.
    if offerte.get("technische_specificaties") == "uitgeschreven" \
            and not _gevuld(offerte.get("technische_specificaties_tekst")) \
            and not _gevuld(offerte.get("technische_specificaties_bestand")):
        ontbreekt.append("de technische specificaties")

    return ontbreekt


def opsomming(ontbreekt: list[str]) -> str:
    """De ontbrekende gegevens als lopende zin: a, b en c."""
    if not ontbreekt:
        return ""
    if len(ontbreekt) == 1:
        return ontbreekt[0]
    return ", ".join(ontbreekt[:-1]) + " en " + ontbreekt[-1]


def melding(ontbreekt: list[str]) -> str:
    """De zin die de gebruiker te zien krijgt als de brief nog niet af is."""
    return (f"De brief is nog niet compleet: {opsomming(ontbreekt)} "
            f"{'ontbreekt' if len(ontbreekt) == 1 else 'ontbreken'} nog. "
            f"Vul dat eerst in; anders staat er straks een gat in de brief.")


def _gevuld(waarde: Any) -> bool:
    return bool(str(waarde).strip()) if waarde is not None else False
