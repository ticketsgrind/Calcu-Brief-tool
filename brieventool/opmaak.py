"""Opmaak van bedragen, getallen en datums in de vorm die Schilt gebruikt.

De vormen zijn overgenomen uit de uitgewerkte brieven, niet zelf bedacht.
Bedragen worden geschreven als "€ 7.595,-" en niet als "€ 7.595,00" -- dat is
wat er in alle zeven uitgewerkte brieven staat. Zie analyse/vragen.md vraag 13;
wil je alsnog centen tonen, zet dan `centen=True`.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

MAANDEN = (
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
)

TELWOORDEN = (
    "nul", "één", "twee", "drie", "vier", "vijf", "zes",
    "zeven", "acht", "negen", "tien", "elf", "twaalf",
)


_DUIZENDTAL = re.compile(r"\.\d{3}(?=\D|$)")


def _lees_bedrag(tekst: str) -> Decimal:
    """Leest een bedrag uit tekst, met Nederlandse en machineschrijfwijze.

    "€ 7.595,-" en "3.900,50" volgen de Nederlandse notatie: punt is
    duizendtalscheiding, komma is decimaalteken. Staat er geen komma, dan is een
    punt gevolgd door precies drie cijfers ook een duizendtalscheiding
    ("1.265.000"), en anders een decimaalteken ("3900.50" uit een systeem).
    Zonder dit onderscheid zou "3900.50" stilzwijgend € 390.050,- worden.
    """
    kaal = tekst.replace("€", "").replace(" ", "").replace("\u00a0", "").strip()
    kaal = kaal.rstrip("-").rstrip(",") if kaal.endswith(",-") else kaal
    if "," in kaal:
        kaal = kaal.replace(".", "").replace(",", ".")
    else:
        kaal = _DUIZENDTAL.sub(lambda m: m.group(0)[1:], kaal)
    return Decimal(kaal)


def bedrag(waarde, centen: bool = False) -> str:
    """Maakt er € 7.595,- van, of € 7.595,00 met centen=True.

    Accepteert een getal of een tekst; een lege waarde levert een lege tekst op,
    zodat een nog niet ingevulde meerprijs geen "€ 0,-" wordt.
    """
    if waarde is None or waarde == "":
        return ""
    if isinstance(waarde, str):
        try:
            getal = _lees_bedrag(waarde)
        except InvalidOperation as fout:
            raise ValueError(f"kan {waarde!r} niet als bedrag lezen") from fout
    else:
        getal = Decimal(str(waarde))

    heel = int(getal)
    rest = (getal - heel).copy_abs()
    duizendtallen = f"{abs(heel):,}".replace(",", ".")
    teken = "-" if getal < 0 else ""

    if centen or rest:
        centwaarde = int((rest * 100).quantize(Decimal("1")))
        return f"€ {teken}{duizendtallen},{centwaarde:02d}"
    return f"€ {teken}{duizendtallen},-"


def telwoord(getal) -> str:
    """1 wordt 'één', 2 wordt 'twee'. Boven de twaalf blijft het een cijfer."""
    if getal is None:
        return ""
    try:
        n = int(getal)
    except (TypeError, ValueError):
        return str(getal)
    if 0 <= n < len(TELWOORDEN):
        return TELWOORDEN[n]
    return str(n)


def briefdatum(waarde=None) -> str:
    """26 augustus 2026 -- voluit, zoals in alle brieven."""
    if waarde is None:
        waarde = date.today()
    if isinstance(waarde, str):
        waarde = date.fromisoformat(waarde)
    return f"{waarde.day} {MAANDEN[waarde.month - 1]} {waarde.year}"


def postcode(waarde: str) -> str:
    """Nederlandse notatie met één spatie: 1234 AB."""
    if not waarde:
        return ""
    kaal = waarde.replace(" ", "").upper()
    if len(kaal) == 6 and kaal[:4].isdigit() and kaal[4:].isalpha():
        return f"{kaal[:4]} {kaal[4:]}"
    return waarde.strip()


def meervoud(aantal, enkelvoud: str, meervoudsvorm: str) -> str:
    """Kiest tussen twee vormen. Voor losse woorden binnen een tekstblok."""
    return enkelvoud if (aantal or 0) == 1 else meervoudsvorm


# Deze functies zijn aanroepbaar vanuit de {{ }}-plaatshouders in teksten.yaml.
FUNCTIES = {
    "bedrag": bedrag,
    "telwoord": telwoord,
    "briefdatum": briefdatum,
    "postcode": postcode,
    "meervoud": meervoud,
}
