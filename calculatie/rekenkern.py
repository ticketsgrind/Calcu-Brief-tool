"""De rekenkern van de calculatietool, geport naar Python.

Dit is een regel-voor-regel vertaling van de rekenkern in
`referenties/calculatietool-schilt/tools/app.js` (VRF/RAC/PAC-urenformules,
marge-opbouw). De DOM-weergave van die tool (het bouwen van installatiekaarten,
het zoeken in de materiaalcatalogus, favorieten, enz.) hoort hier niet bij en
blijft in de browser — alleen de getallen die ook in de brief terechtkomen
(verkoopprijs, resultaat, uren) worden hier, en dus maar op één plek, berekend.
Dat voorkomt dat het scherm en de brief ooit een ander bedrag laten zien.

Elke functie hieronder is getoetst tegen de 39 vaste controles uit de
oorspronkelijke `tools/test_engine.js`, overgezet naar
`tests/test_rekenkern.py`, zodat de uitkomsten aantoonbaar gelijk zijn
gebleven aan de eerder tegen Excel geverifieerde cijfers.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

MOEILIJKHEID_FACTOR: dict[str, float] = {"Makkelijk": 0.8, "Standaard": 1, "Moeilijk": 1.2}

UUR_TABEL: dict[str, dict[str, float]] = {
    "VRF": {"buiten1": 12, "buitenN": 8, "binnen": 8},
    "RAC": {"buiten": 2, "binnen": 3},
    "PAC": {"buiten": 8, "binnen": 8},
    "Overig": {"buiten": 8, "binnen": 8},
}

ROL_LABELS: dict[str, str] = {
    "projectmanager": "Projectmanager", "projectleider": "Projectleider",
    "werkvoorbereider": "Werkvoorbereider", "engineering": "Engineering",
    "servicemonteur": "Servicemonteur", "hoofdmonteur": "Hoofdmonteur",
    "hulpmonteur": "Hulpmonteur", "verkoper": "Verkoper",
}

DEFAULT_TARIEVEN: dict[str, float] = {
    "projectmanager": 158, "projectleider": 112, "werkvoorbereider": 93, "engineering": 112,
    "servicemonteur": 81, "hoofdmonteur": 69, "hulpmonteur": 56, "verkoper": 158,
}

UITBESTEDING_DEFAULTS: list[dict[str, Any]] = [
    {"omschrijving": "Kleine kraan", "eenheid": "ST", "prijs": 500, "favoriet": True},
    {"omschrijving": "Grote kraan", "eenheid": "ST", "prijs": None, "favoriet": True},
    {"omschrijving": "Betonboring", "eenheid": "ST", "prijs": 200, "favoriet": True},
    {"omschrijving": "IBS / Support Leverancier", "eenheid": "ST", "prijs": None, "favoriet": False},
    {"omschrijving": "Luchtverdeelslang KE Fibertec, incl. inmeten en montage", "eenheid": "M", "prijs": 140, "favoriet": False},
    {"omschrijving": "Dakdekker", "eenheid": "POST", "prijs": None, "favoriet": False},
    {"omschrijving": "Brandwerende afwerking", "eenheid": "POST", "prijs": None, "favoriet": False},
    {"omschrijving": "Hulpconstructie", "eenheid": "POST", "prijs": None, "favoriet": False},
    {"omschrijving": "Elektrotechnisch", "eenheid": "POST", "prijs": None, "favoriet": False},
    {"omschrijving": "Loodgieter/CV", "eenheid": "POST", "prijs": None, "favoriet": False},
    {"omschrijving": "Spuiten grille", "eenheid": "POST", "prijs": 250, "favoriet": False},
    {"omschrijving": "Sloopwerkzaamheden", "eenheid": "POST", "prijs": None, "favoriet": False},
    {"omschrijving": "PED keuring (per VRF systeem)", "eenheid": "ST", "prijs": 75, "favoriet": False},
]

EQUIPMENT_DEFAULTS: list[dict[str, Any]] = [
    {"omschrijving": "Hoogwerker", "eenheid": "WEEK", "prijs": 700, "favoriet": True},
    {"omschrijving": "Heftruck", "eenheid": "POST", "prijs": None, "favoriet": True},
    {"omschrijving": "Steiger", "eenheid": "POST", "prijs": None, "favoriet": True},
    {"omschrijving": "Huur cilinder koudemiddel (per dag)", "eenheid": "DAG", "prijs": 0.27, "favoriet": False},
]

DATA_MAP = Path(__file__).resolve().parent.parent / "data"

_uid = [1]


def _nieuw_id() -> str:
    _uid[0] += 1
    return f"id{_uid[0]}"


# --------------------------------------------------------------------------
# Gegevens (stamdata): materiaalcatalogus, YIMM-prijzen, parkeertarieven,
# omzetbonus/provisie. Alleen wat de rekenkern zelf nodig heeft; de
# zoekfunctionaliteit voor Panasonic/Daikin/YIMM blijft in de browser.
# --------------------------------------------------------------------------

def laad_gegevens(map_pad: Path | str | None = None) -> dict[str, Any]:
    wortel = Path(map_pad) if map_pad else DATA_MAP
    return {
        "materiaal_catalogus": _laad_json(wortel / "materiaal_catalogus.json"),
        "yimm": _laad_json(wortel / "yimm.json"),
        "parkeertarieven": _laad_json(wortel / "parkeertarieven.json"),
        "omzetbonus_provisie": _laad_json(wortel / "omzetbonus_provisie.json"),
    }


def _laad_json(pad: Path) -> Any:
    return json.loads(pad.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# helpers (1-op-1 uit app.js)
# --------------------------------------------------------------------------

def _num(waarde: Any, default: float = 0.0) -> float:
    """Number(x) || 0 — leeg/ongeldig/None wordt de meegegeven default."""
    if waarde is None or waarde == "":
        return default
    try:
        n = float(waarde)
    except (TypeError, ValueError):
        return default
    if n != n:  # NaN
        return default
    return n


def round2(n: float) -> float:
    return math.floor(n * 100 + 0.5) / 100


def round_up(n: float, d: int = 0) -> float:
    f = 10 ** d
    return math.ceil(round2(n * f) - 1e-9) / f


def ceiling_excel(n: float, sig: float) -> float:
    if not sig:
        return 0
    return math.ceil(round2(n / sig) - 1e-9) * sig


def non_negatief(waarde: Any) -> Any:
    """Geen van de rekenkern-velden mag negatief zijn; tekst blijft ongemoeid."""
    if waarde == "" or waarde is None:
        return waarde
    try:
        n = float(waarde)
    except (TypeError, ValueError):
        return waarde
    return 0 if n < 0 else waarde


def nieuwe_staat() -> dict[str, Any]:
    return {
        "meta": {"qnummer": "", "projectnaam": "", "klantnaam": "", "klantnummer": "",
                 "uitgangspunten": "", "datum": ""},
        "instellingen": {"moeilijkheid": "Standaard", "reistijd": 1,
                          "provincie": "Geen parkeerkosten",
                          "bonusklant": "Geen bonusdragende klant",
                          "provisieklant": "Geen provisie"},
        "installaties": [],
        "materiaal": [],
        "uren": {
            "projectmanager": {"werk": 0, "reis": 0, "tarief": DEFAULT_TARIEVEN["projectmanager"]},
            "projectleider": {"werk": 0, "reis": 0, "tarief": DEFAULT_TARIEVEN["projectleider"]},
            "werkvoorbereider": {"werk": 0, "reis": 0, "tarief": DEFAULT_TARIEVEN["werkvoorbereider"]},
            "engineering": {"werk": 0, "reis": 0, "tarief": DEFAULT_TARIEVEN["engineering"]},
            "servicemonteur": {"overig": 0, "tarief": DEFAULT_TARIEVEN["servicemonteur"], "override": None},
            "hoofdmonteur": {"tarief": DEFAULT_TARIEVEN["hoofdmonteur"], "override": None},
            "hulpmonteur": {"tarief": DEFAULT_TARIEVEN["hulpmonteur"], "override": None},
            "verkoper": {"uren": 0, "tarief": DEFAULT_TARIEVEN["verkoper"]},
        },
        "uitbesteding": [dict(d, id=_nieuw_id(), aantal=0) for d in UITBESTEDING_DEFAULTS],
        "equipment": [dict(d, id=_nieuw_id(), aantal=0) for d in EQUIPMENT_DEFAULTS],
        "overig": {"nachten": 0, "nachtprijs": 150},
        "marge": {"contingencyReserves": 0, "contingencyOnderhandeling": 0, "projectPrice": None},
    }


# --------------------------------------------------------------------------
# rekenkern — automatisch gekoppelde materiaalaantallen
# --------------------------------------------------------------------------

def catalogus_item(artikelcode: str | None, yimm: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not artikelcode:
        return None
    return next((a for a in yimm if a.get("code") == artikelcode), None)


def materiaal_regel_uit_catalogus(catalogus_entry: dict[str, Any], yimm: list[dict[str, Any]]) -> dict[str, Any]:
    live = catalogus_item(catalogus_entry.get("artikelcode"), yimm)
    return {
        "id": _nieuw_id(),
        "sectie": catalogus_entry.get("sectie"),
        "row": catalogus_entry.get("row"),
        "bron": catalogus_entry.get("bron"),
        "artikelcode": catalogus_entry.get("artikelcode"),
        "omschrijving": (live or {}).get("omschrijving") if live else catalogus_entry.get("omschrijving"),
        "eenheid": (live or {}).get("eenheid") if live else catalogus_entry.get("eenheid"),
        "prijs": (live or {}).get("prijs") if live else catalogus_entry.get("prijs"),
        "per_meter_type": catalogus_entry.get("per_meter_type"),
        "leiding_categorie": catalogus_entry.get("leiding_categorie"),
        "montage_uur_per_eenheid": catalogus_entry.get("montage_uur_per_eenheid"),
        "servicemonteur_trigger": catalogus_entry.get("servicemonteur_trigger"),
        "instellingen_koppeling": catalogus_entry.get("instellingen_koppeling"),
        "afgeleid": bool(catalogus_entry.get("afgeleid_van")),
        "aantal": 1,
    }


def sync_afgeleide_aantallen(staat: dict[str, Any], gegevens: dict[str, Any]) -> None:
    """Trillingsdempers e.d. die automatisch meekomen met een bronartikel."""
    materiaal_catalogus = gegevens["materiaal_catalogus"]
    yimm = gegevens["yimm"]

    aantal_per_row: dict[Any, float] = {}
    for r in staat["materiaal"]:
        row = r.get("row")
        if row is not None:
            aantal_per_row[row] = aantal_per_row.get(row, 0) + _num(r.get("aantal"))

    for cat_entry in materiaal_catalogus:
        afgeleid_van = cat_entry.get("afgeleid_van")
        if not afgeleid_van:
            continue
        afgeleid_aantal = sum(aantal_per_row.get(d["row"], 0) * d["factor"] for d in afgeleid_van)
        regel = next((r for r in staat["materiaal"] if r.get("row") == cat_entry.get("row")), None)
        if afgeleid_aantal > 0:
            if regel is not None:
                regel["aantal"] = afgeleid_aantal
            else:
                nieuwe_regel = materiaal_regel_uit_catalogus(cat_entry, yimm)
                nieuwe_regel["aantal"] = afgeleid_aantal
                staat["materiaal"].append(nieuwe_regel)
        elif regel is not None:
            staat["materiaal"] = [r for r in staat["materiaal"] if r is not regel]


# --------------------------------------------------------------------------
# rekenkern — installaties → uren
# --------------------------------------------------------------------------

def installatie_totalen(staat: dict[str, Any]) -> dict[str, dict[str, float]]:
    t = {"VRF": {"buiten": 0.0, "binnen": 0.0}, "RAC": {"buiten": 0.0, "binnen": 0.0},
         "PACOverig": {"buiten": 0.0, "binnen": 0.0}}
    for i in staat["installaties"]:
        buiten = _num(i.get("aantalBuitendelen"))
        binnen = _num(i.get("aantalBinnendelen"))
        soort = i.get("systeemsoort")
        if soort == "VRF":
            t["VRF"]["buiten"] += buiten
            t["VRF"]["binnen"] += binnen
        elif soort == "RAC":
            t["RAC"]["buiten"] += buiten
            t["RAC"]["binnen"] += binnen
        else:  # PAC + Overig, zoals in het Excel-blad
            t["PACOverig"]["buiten"] += buiten
            t["PACOverig"]["binnen"] += binnen
    return t


def leiding_meters(staat: dict[str, Any]) -> dict[str, float]:
    m = {"hard_2pijps": 0.0, "hard_3pijps": 0.0, "zacht_2pijps": 0.0}
    for r in staat["materiaal"]:
        categorie = r.get("leiding_categorie")
        if categorie in m:
            m[categorie] += _num(r.get("aantal"))
    return m


def montage_toebehoren_uren(staat: dict[str, Any]) -> float:
    u = 0.0
    for r in staat["materiaal"]:
        per_eenheid = r.get("montage_uur_per_eenheid")
        if per_eenheid:
            u += _num(r.get("aantal")) * per_eenheid
    return u


def centrale_regelaar_aantal(staat: dict[str, Any]) -> float:
    r = next((r for r in staat["materiaal"] if r.get("servicemonteur_trigger") == "centrale_regelaar"), None)
    return _num(r.get("aantal")) if r else 0


def verdeelboxen_aantal(staat: dict[str, Any]) -> float:
    """B5 in Excel ("Aantal verdeelboxen") is geen los invulveld maar =A34: het
    volgt automatisch de materiaalregel "VERDEELBOXEN" (Apparatuur)."""
    r = next((r for r in staat["materiaal"] if r.get("instellingen_koppeling") == "verdeelboxen"), None)
    return _num(r.get("aantal")) if r else 0


def monteur_werkuren_auto(staat: dict[str, Any]) -> float:
    """Werkuren-formule die identiek is voor Hoofd- en Hulpmonteur in het Excel-blad."""
    t = installatie_totalen(staat)
    lm = leiding_meters(staat)
    u = 0.0
    if t["VRF"]["buiten"] == 1:
        u += UUR_TABEL["VRF"]["buiten1"]
    elif t["VRF"]["buiten"] > 1:
        u += UUR_TABEL["VRF"]["buitenN"] * t["VRF"]["buiten"]
    u += t["VRF"]["binnen"] * UUR_TABEL["VRF"]["binnen"]
    u += verdeelboxen_aantal(staat) * 8  # BC controller
    u += t["RAC"]["buiten"] * UUR_TABEL["RAC"]["buiten"]
    u += t["RAC"]["binnen"] * UUR_TABEL["RAC"]["binnen"]
    u += t["PACOverig"]["buiten"] * UUR_TABEL["PAC"]["buiten"]
    u += t["PACOverig"]["binnen"] * UUR_TABEL["PAC"]["binnen"]
    u += montage_toebehoren_uren(staat)  # kabelgoot/condensafvoer/pvc (0,25u/m) + toebehoren luchtverdeling
    u += lm["hard_2pijps"] * 0.25
    u += lm["zacht_2pijps"] * 0.25
    u += lm["hard_3pijps"] * 0.33
    return u


def ploegdagen(staat: dict[str, Any]) -> float:
    # B9 = ((SUM werkuren hoofd + SUM werkuren hulp)/16) * factor; hoofd en hulp zijn identiek.
    werk = monteur_werkuren_auto(staat)
    factor = MOEILIJKHEID_FACTOR[staat["instellingen"]["moeilijkheid"]]
    return ((werk + werk) / 16) * factor


def reisuren_monteur(staat: dict[str, Any]) -> float:
    reistijd = _num(staat["instellingen"].get("reistijd"))
    factor = MOEILIJKHEID_FACTOR[staat["instellingen"]["moeilijkheid"]]
    if reistijd <= 0:
        return 0
    return ceiling_excel((round_up(ploegdagen(staat), 0) * reistijd) / factor, reistijd)


def monteur_voorstel(staat: dict[str, Any]) -> float:
    werk = monteur_werkuren_auto(staat)
    factor = MOEILIJKHEID_FACTOR[staat["instellingen"]["moeilijkheid"]]
    reis = reisuren_monteur(staat)
    return round_up(werk * factor + reis, 0)


def servicemonteur_voorstel(staat: dict[str, Any]) -> dict[str, float]:
    t = installatie_totalen(staat)
    auto = 8 if centrale_regelaar_aantal(staat) > 0 else 0
    vrf_ibs = t["VRF"]["buiten"] * 8
    werk = auto + vrf_ibs + _num(staat["uren"]["servicemonteur"].get("overig"))
    factor = MOEILIJKHEID_FACTOR[staat["instellingen"]["moeilijkheid"]]
    reistijd = _num(staat["instellingen"].get("reistijd"))
    reis = ceiling_excel((werk / 8) * reistijd, reistijd) if reistijd > 0 else 0
    return {"werk": werk, "auto": auto, "vrfIbs": vrf_ibs, "reis": reis,
            "totaal": round_up(werk * factor + reis, 0)}


def rol_uren(staat: dict[str, Any], rol: str) -> dict[str, float | None]:
    if rol in ("hoofdmonteur", "hulpmonteur"):
        voorstel = monteur_voorstel(staat)
        ov = staat["uren"][rol].get("override")
        return {"voorstel": voorstel, "definitief": voorstel if ov is None else _num(ov)}
    if rol == "servicemonteur":
        sm = servicemonteur_voorstel(staat)
        ov = staat["uren"]["servicemonteur"].get("override")
        return {"voorstel": sm["totaal"], "definitief": sm["totaal"] if ov is None else _num(ov)}
    if rol == "verkoper":
        return {"voorstel": None, "definitief": _num(staat["uren"]["verkoper"].get("uren"))}
    r = staat["uren"][rol]
    totaal = round_up(_num(r.get("werk")) + _num(r.get("reis")), 0)
    return {"voorstel": None, "definitief": totaal}


def arbeid_totaal(staat: dict[str, Any]) -> float:
    totaal = 0.0
    for rol in ROL_LABELS:
        definitief = rol_uren(staat, rol)["definitief"]
        totaal += definitief * _num(staat["uren"][rol].get("tarief"))
    return totaal


# --------------------------------------------------------------------------
# rekenkern — materiaal / uitbesteding / equipment
# --------------------------------------------------------------------------

def regel_totaal(r: dict[str, Any]) -> float | None:
    ruwe_prijs = r.get("prijs")
    prijs = None if ruwe_prijs is None or ruwe_prijs == "" else float(ruwe_prijs)
    aantal = _num(r.get("aantal"))
    if prijs is None:
        return None  # onbekend — nooit een schijnbedrag
    return aantal * prijs


def lijst_totaal(lijst: list[dict[str, Any]]) -> dict[str, Any]:
    totaal = 0.0
    onvolledig = 0
    for r in lijst:
        t = regel_totaal(r)
        if t is None:
            if _num(r.get("aantal")) > 0:
                onvolledig += 1
        else:
            totaal += t
    return {"totaal": totaal, "onvolledig": onvolledig}


# --------------------------------------------------------------------------
# rekenkern — marge-opbouw (Quotation-sheet-equivalent)
# --------------------------------------------------------------------------

def marge_berekening(staat: dict[str, Any], gegevens: dict[str, Any]) -> dict[str, Any]:
    materiaal = lijst_totaal(staat["materiaal"])
    uitbesteding = lijst_totaal(staat["uitbesteding"])
    equipment = lijst_totaal(staat["equipment"])
    arbeid = arbeid_totaal(staat)

    parkeeruren = ploegdagen(staat) * 8
    parkeertarieven = gegevens["parkeertarieven"]
    parkeertarief = next((p["tarief_per_uur"] for p in parkeertarieven
                          if p["provincie"] == staat["instellingen"]["provincie"]), 0)
    parkeerkosten = parkeeruren * parkeertarief
    overnachtingen = _num(staat["overig"].get("nachten")) * _num(staat["overig"].get("nachtprijs"))
    reiskosten = parkeerkosten + overnachtingen

    overhead_inkoop = materiaal["totaal"] * 0.12
    overhead_uitbesteding = uitbesteding["totaal"] * 0.12
    contingency_reserves = _num(staat["marge"].get("contingencyReserves"))
    contingency_onderhandeling = _num(staat["marge"].get("contingencyOnderhandeling"))

    overige_kosten = (materiaal["totaal"] + overhead_inkoop + uitbesteding["totaal"] + overhead_uitbesteding
                       + equipment["totaal"] + reiskosten + contingency_reserves + contingency_onderhandeling)

    ic = arbeid + overige_kosten
    lost = ic * 0.04
    financial = ic * 0.007
    group_fees = ic * 0.04
    full_cost = ic + lost + financial + group_fees

    ruwe_price = staat["marge"].get("projectPrice")
    project_price = None if ruwe_price is None or ruwe_price == "" else float(ruwe_price)
    resultaat = None if project_price is None else project_price - full_cost

    omzetbonus_provisie = gegevens["omzetbonus_provisie"]
    bonus_pct = next((b["bonus"] for b in omzetbonus_provisie["omzetbonus"]
                      if b["klant"] == staat["instellingen"]["bonusklant"]), 0)
    provisie_pct = next((p["provisie"] for p in omzetbonus_provisie["provisie"]
                         if p["klant"] == staat["instellingen"]["provisieklant"]), 0)
    omzetbonus = None if project_price is None else project_price * bonus_pct
    garantie = None if project_price is None else project_price * 0.0125
    verkoopprijs = None if project_price is None else (project_price + omzetbonus + garantie) / (1 - provisie_pct)
    resultaat_pct = (resultaat / verkoopprijs) if (verkoopprijs and resultaat is not None) else None

    return {
        "materiaal": materiaal, "uitbesteding": uitbesteding, "equipment": equipment, "arbeid": arbeid,
        "parkeeruren": parkeeruren, "parkeerkosten": parkeerkosten, "overnachtingen": overnachtingen,
        "reiskosten": reiskosten, "overheadInkoop": overhead_inkoop, "overheadUitbesteding": overhead_uitbesteding,
        "contingencyReserves": contingency_reserves, "contingencyOnderhandeling": contingency_onderhandeling,
        "overigeKosten": overige_kosten, "ic": ic, "lost": lost, "financial": financial, "groupFees": group_fees,
        "fullCost": full_cost, "projectPrice": project_price, "resultaat": resultaat, "omzetbonus": omzetbonus,
        "garantie": garantie, "verkoopprijs": verkoopprijs, "resultaatPct": resultaat_pct,
    }


def bereken(staat: dict[str, Any], gegevens: dict[str, Any] | None = None) -> dict[str, Any]:
    """Eén aanroep die precies doet wat het scherm op elke wijziging nodig heeft:
    afgeleide materiaalregels bijwerken, de uren per rol en de volledige
    marge-opbouw teruggeven. `staat["materiaal"]` wordt in-place aangevuld met
    eventuele afgeleide regels (trillingsdempers e.d.), zodat het antwoord de
    volledige, weer te geven materiaallijst bevat."""
    gegevens = gegevens or laad_gegevens()
    sync_afgeleide_aantallen(staat, gegevens)
    uren = {rol: rol_uren(staat, rol) for rol in ROL_LABELS}
    marge = marge_berekening(staat, gegevens)
    return {
        "materiaal": staat["materiaal"],
        "uren": uren,
        "verdeelboxenAantal": verdeelboxen_aantal(staat),
        "monteurWerkurenAuto": monteur_werkuren_auto(staat),
        "servicemonteurVoorstel": servicemonteur_voorstel(staat),
        "marge": marge,
    }
