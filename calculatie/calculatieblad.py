"""Het ingevulde Excel-calculatieblad (zoals de losstaande calculatietool dat
al opleverde) genereren uit een calculatie-staat + de uitkomst van
`rekenkern.bereken()`.

**Alle cijfers komen letterlijk uit `rekenkern.py`, nooit uit een
Excel-formule die iets opnieuw uitrekent.** Het sjabloon
(`sjablonen/Template_Calculatieblad.xltx`, het echte bedrijfssjabloon) heeft
op de bladen "Calculatie" en "Quotation sheet" overal SUM/PRODUCT/VLOOKUP-
formules staan die in de originele, losstaande Excel-tool de optelsom en
marge-opbouw deden. Die formules laten we bewust *niet* opnieuw rekenen: elke
cel die geld of uren voorstelt wordt hier overschreven met de kant-en-klare
waarde uit `rekenkern.bereken()` (of een triviale aantal×prijs-vermenigvuldiging,
dezelfde categorie die `scherm/calculatie.js`'s `regelTotaal`/`lijstTotaal`
ook al client-side mag doen, zie CLAUDE.md). Zou je in plaats daarvan de
formules laten staan en alleen de invoercellen vullen, dan reken je in feite
de marge een tweede keer uit -- in Excel in plaats van in Python -- en dat is
precies het risico dat de samenvoeging van calculatie- en brieventool moest
wegnemen (twee plekken die een ander bedrag kunnen laten zien). De enige
plek die zelf nog optelt is dit bestand se eigen sectie-subtotalen
(`_sectie_totalen`) en die doet dat met dezelfde aantal×prijs-regel als
rekenkern.regel_totaal, niet met een eigen rekenregel.

Cel-adressen zijn overgenomen uit een handmatige inspectie van het sjabloon
(zie `analyse/01-rekenbladen-per-tabblad.md` in de losstaande
calculatietool-repo voor de volledige rij-per-rij herkomst). Andere
tabbladen (Info, Mat. lijst, Budget voor admin, YIMM, Parkeertarieven, ...)
worden niet aangeraakt: die zijn óf pure naslag (blijven ongebruikt in de
export) óf halen hun cijfers via een eigen formule uit Quotation sheet/
Calculatie en tonen daardoor vanzelf de juiste waarde zodra Excel het
bestand opent (`fullCalcOnLoad`), zonder dat wij die formules zelf hoeven
te begrijpen of te dupliceren.

Net als `brieventool/sjabloon.py` gebeurt dit met kale ZIP+XML-manipulatie
(stdlib `zipfile`/`re`), niet met `openpyxl`: geen nieuwe afhankelijkheid
nodig, en consistent met hoe deze repo Office-bestanden al genereert.
"""

from __future__ import annotations

import datetime
import io
import re
import zipfile
from pathlib import Path
from typing import Any

from . import rekenkern as rk

SJABLOON = Path(__file__).resolve().parent.parent / "sjablonen" / "Template_Calculatieblad.xltx"

SHEET_CALCULATIE = "xl/worksheets/sheet5.xml"
SHEET_QUOTATION = "xl/worksheets/sheet4.xml"
WORKBOOK = "xl/workbook.xml"
WORKBOOK_RELS = "xl/_rels/workbook.xml.rels"
CONTENT_TYPES = "[Content_Types].xml"
CALC_CHAIN = "xl/calcChain.xml"

# Vaste rijen voor de 13 standaard-uitbestedingsregels resp. 4 standaard-
# equipmentregels (zie rekenkern.UITBESTEDING_DEFAULTS/EQUIPMENT_DEFAULTS) --
# de volgorde in het Excel-blad wijkt af van de volgorde in die Python-lijst,
# vandaar een expliciete naam->rij-koppeling in plaats van positioneel zippen.
UITBESTEDING_RIJEN: dict[str, int] = {
    "IBS / Support Leverancier": 399,
    "Luchtverdeelslang KE Fibertec, incl. inmeten en montage": 400,
    "Kleine kraan": 401,
    "Grote kraan": 402,
    "Betonboring": 403,
    "Dakdekker": 404,
    "Brandwerende afwerking": 405,
    "Hulpconstructie": 406,
    "Elektrotechnisch": 407,
    "Loodgieter/CV": 408,
    "Spuiten grille": 409,
    "Sloopwerkzaamheden": 410,
    "PED keuring (per VRF systeem)": 411,
}
UITBESTEDING_LEGE_RIJEN = [412, 413, 414, 415, 416]

EQUIPMENT_RIJEN: dict[str, int] = {
    "Hoogwerker": 420,
    "Heftruck": 421,
    "Steiger": 422,
    "Huur cilinder koudemiddel (per dag)": 423,
}
EQUIPMENT_LEGE_RIJEN = [424, 425, 426, 427, 428]

SECTIE_SUBTOTAAL_RIJ: dict[str, int] = {
    "APPARATUUR": 30,
    "BALKEN/VOETEN/MUURSTEUN": 73,
    "LEIDINGEN/KABELS/SIFON": 92,
    "POMPEN": 136,
    "INOAC": 155,
    "SOLDEER": 228,
    "WERKSCHAKELAAR": 239,
    "KOUDE MIDDEL": 247,
    "DAKDOORVOERING": 255,
    "TOEBEHOREN LUCHTVERDELING": 265,
}
# Volgorde van de secties zoals ze in Quotation sheet!C30:C39 staan (voor de
# "Detail Purchases"-uitsplitsing daar).
SECTIE_VOLGORDE = list(SECTIE_SUBTOTAAL_RIJ.keys())


def _num(waarde: Any) -> float:
    return rk._num(waarde)


# --------------------------------------------------------------------------
# laag-niveau celbewerking: tekst-vervanging in de ruwe sheet-XML, met
# behoud van alles wat niet expliciet wordt overschreven (stijl, opmaak,
# andere cellen) -- zelfde aanpak als brieventool/sjabloon.py.
# --------------------------------------------------------------------------

def _kolom_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def _cel_delen(ref: str) -> tuple[str, int]:
    m = re.match(r"^([A-Z]+)(\d+)$", ref)
    if not m:
        raise ValueError(f"ongeldige celverwijzing: {ref!r}")
    return m.group(1), int(m.group(2))


def _tekst_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _getal_tekst(waarde: float) -> str:
    if waarde == int(waarde):
        return str(int(waarde))
    tekst = f"{waarde:.6f}".rstrip("0").rstrip(".")
    return tekst


class SheetSchrijver:
    """Overschrijft cellen in de ruwe XML-tekst van één werkblad. Bestaande
    stijl (het `s`-attribuut) blijft behouden; een eventuele formule
    (`<f>`) wordt altijd verwijderd -- deze cellen worden bewust statisch,
    zie de moduledocstring hierboven."""

    def __init__(self, xml: str):
        self.xml = xml

    def _cel_patroon(self, ref: str) -> re.Pattern:
        return re.compile(r'<c r="' + re.escape(ref) + r'"([^>]*?)(/>|>(.*?)</c>)', re.DOTALL)

    def _rij_patroon(self, rownum: int) -> re.Pattern:
        return re.compile(r'(<row r="' + str(rownum) + r'"[^>]*>)(.*?)(</row>)', re.DOTALL)

    def _stijl_van(self, attrs: str) -> str | None:
        m = re.search(r's="(\d+)"', attrs)
        return m.group(1) if m else None

    def _cel_bouwen(self, ref: str, stijl: str | None, waarde: Any) -> str:
        s_attr = f' s="{stijl}"' if stijl else ""
        if waarde is None or waarde == "":
            return f'<c r="{ref}"{s_attr}/>'
        if isinstance(waarde, str):
            return (f'<c r="{ref}"{s_attr} t="inlineStr"><is>'
                    f'<t xml:space="preserve">{_tekst_escape(waarde)}</t></is></c>')
        return f'<c r="{ref}"{s_attr}><v>{_getal_tekst(float(waarde))}</v></c>'

    def _cel_invoegen(self, ref: str, nieuwe_cel: str) -> None:
        letters, rownum = _cel_delen(ref)
        kolom = _kolom_index(letters)
        rij_patroon = self._rij_patroon(rownum)
        m = rij_patroon.search(self.xml)
        if not m:
            raise ValueError(f"rij {rownum} niet gevonden in het sjabloon (cel {ref})")
        start, eind = m.start(2), m.end(2)
        inhoud = m.group(2)
        invoegpositie = eind
        for cm in re.finditer(r'<c r="([A-Z]+)(\d+)"', inhoud):
            if _kolom_index(cm.group(1)) > kolom:
                invoegpositie = start + cm.start()
                break
        self.xml = self.xml[:invoegpositie] + nieuwe_cel + self.xml[invoegpositie:]

    def zet(self, ref: str, waarde: Any) -> None:
        patroon = self._cel_patroon(ref)
        m = patroon.search(self.xml)
        stijl = self._stijl_van(m.group(1)) if m else None
        nieuwe_cel = self._cel_bouwen(ref, stijl, waarde)
        if m:
            self.xml = self.xml[: m.start()] + nieuwe_cel + self.xml[m.end() :]
        else:
            self._cel_invoegen(ref, nieuwe_cel)


# --------------------------------------------------------------------------
# secties -> subtotalen (dezelfde triviale aantal×prijs-optelling als
# scherm/calculatie.js se regelTotaal/lijstTotaal, hier alleen per sectie)
# --------------------------------------------------------------------------

def _sectie_totalen(materiaal: list[dict[str, Any]]) -> dict[str, float]:
    totalen = {s: 0.0 for s in SECTIE_VOLGORDE}
    for item in materiaal:
        sectie = item.get("sectie")
        if sectie not in totalen:
            continue
        prijs = item.get("prijs")
        if prijs is None or prijs == "":
            continue
        totalen[sectie] += _num(item.get("aantal")) * float(prijs)
    return totalen


def _bonus_en_provisie_pct(staat: dict[str, Any], gegevens: dict[str, Any]) -> tuple[float, float]:
    """Zelfde opzoeking als rekenkern.marge_berekening -- hier herhaald (niet
    opnieuw uitgevonden) om ook Calculatie!F440/F443 en Quotation sheet!P73
    letterlijk te kunnen vullen in plaats van via de VLOOKUP-formule."""
    omzetbonus_provisie = gegevens["omzetbonus_provisie"]
    bonus_pct = next((b["bonus"] for b in omzetbonus_provisie["omzetbonus"]
                      if b["klant"] == staat["instellingen"]["bonusklant"]), 0)
    provisie_pct = next((p["provisie"] for p in omzetbonus_provisie["provisie"]
                         if p["klant"] == staat["instellingen"]["provisieklant"]), 0)
    return bonus_pct, provisie_pct


def _parkeertarief(staat: dict[str, Any], gegevens: dict[str, Any]) -> float:
    parkeertarieven = gegevens["parkeertarieven"]
    provincie = staat["instellingen"]["provincie"]
    return next((p["tarief_per_uur"] for p in parkeertarieven if p["provincie"] == provincie), 0)


# --------------------------------------------------------------------------
# Calculatie-blad
# --------------------------------------------------------------------------

def _vul_kop(w: SheetSchrijver, staat: dict[str, Any], berekening: dict[str, Any]) -> None:
    meta = staat.get("meta") or {}
    w.zet("B1", meta.get("qnummer") or "")
    w.zet("B2", meta.get("projectnaam") or "")
    w.zet("B3", meta.get("klantnaam") or "")
    w.zet("B4", meta.get("klantnummer") or "")
    w.zet("D1", meta.get("uitgangspunten") or "")

    w.zet("B5", rk.verdeelboxen_aantal(staat))
    leiding_meters_totaal = sum(
        _num(item.get("aantal")) for item in berekening["materiaal"]
        if item.get("row") is not None and 93 <= item["row"] <= 106
    )
    w.zet("B6", leiding_meters_totaal)
    w.zet("B7", staat["instellingen"]["moeilijkheid"])
    w.zet("B8", staat["instellingen"].get("reistijd") or 0)
    w.zet("B9", rk.ploegdagen(staat))

    marge = berekening["marge"]
    if marge.get("ic"):
        w.zet("F1", marge["overigeKosten"] / marge["ic"])
        w.zet("F2", 1 - marge["overigeKosten"] / marge["ic"])


def _vul_installaties(w: SheetSchrijver, staat: dict[str, Any]) -> None:
    totalen = rk.installatie_totalen(staat)
    w.zet("B12", totalen["VRF"]["buiten"])
    w.zet("B13", totalen["VRF"]["binnen"])
    w.zet("B16", totalen["RAC"]["buiten"])
    w.zet("B17", totalen["RAC"]["binnen"])
    # rekenkern voegt PAC en Overig samen (PACOverig); het Excel-blad houdt ze
    # als twee losse slots (rijen 19-21 resp. 23-25) -- hier dus zelf
    # opnieuw uitgesplitst per systeemsoort, niet uit rekenkern gehaald.
    pac = {"buiten": 0.0, "binnen": 0.0}
    overig = {"buiten": 0.0, "binnen": 0.0}
    for i in staat["installaties"]:
        if i.get("systeemsoort") == "PAC":
            pac["buiten"] += _num(i.get("aantalBuitendelen"))
            pac["binnen"] += _num(i.get("aantalBinnendelen"))
        elif i.get("systeemsoort") == "Overig":
            overig["buiten"] += _num(i.get("aantalBuitendelen"))
            overig["binnen"] += _num(i.get("aantalBinnendelen"))
    w.zet("B20", pac["buiten"])
    w.zet("B21", pac["binnen"])
    w.zet("B24", overig["buiten"])
    w.zet("B25", overig["binnen"])


def _vul_materiaal(w: SheetSchrijver, berekening: dict[str, Any]) -> None:
    for item in berekening["materiaal"]:
        row = item.get("row")
        if row is None:
            continue
        aantal = _num(item.get("aantal"))
        prijs = item.get("prijs")
        w.zet(f"A{row}", aantal)
        w.zet(f"D{row}", item.get("omschrijving") or "")
        w.zet(f"E{row}", item.get("eenheid") or "")
        if prijs is None or prijs == "":
            w.zet(f"F{row}", "")
            w.zet(f"H{row}", "")
        else:
            w.zet(f"F{row}", float(prijs))
            w.zet(f"H{row}", aantal * float(prijs))

    for sectie, totaal in _sectie_totalen(berekening["materiaal"]).items():
        w.zet(f"H{SECTIE_SUBTOTAAL_RIJ[sectie]}", totaal)


def _monteur_termen(staat: dict[str, Any]) -> dict[str, float]:
    """De afzonderlijke posten die samen rekenkern.monteur_werkuren_auto()
    vormen, hier uit elkaar gehaald om ze zichtbaar per rij (357-368/378-389)
    te kunnen tonen -- dezelfde functies als rekenkern zelf gebruikt, geen
    herhaling van de rekenregels erin."""
    t = rk.installatie_totalen(staat)
    lm = rk.leiding_meters(staat)
    vrf_buiten = (rk.UUR_TABEL["VRF"]["buiten1"] if t["VRF"]["buiten"] == 1
                  else rk.UUR_TABEL["VRF"]["buitenN"] * t["VRF"]["buiten"] if t["VRF"]["buiten"] > 1 else 0)
    materiaal_op_row = {item["row"]: item for item in staat["materiaal"] if item.get("row") is not None}
    kabelgoot_m = sum(_num(materiaal_op_row[r]["aantal"]) for r in (123, 124, 125) if r in materiaal_op_row)
    return {
        "vrf_buiten": vrf_buiten,
        "vrf_binnen": t["VRF"]["binnen"] * rk.UUR_TABEL["VRF"]["binnen"],
        "verdeelboxen": rk.verdeelboxen_aantal(staat) * 8,
        "rac_buiten": t["RAC"]["buiten"] * rk.UUR_TABEL["RAC"]["buiten"],
        "rac_binnen": t["RAC"]["binnen"] * rk.UUR_TABEL["RAC"]["binnen"],
        "pac_overig_buiten": t["PACOverig"]["buiten"] * rk.UUR_TABEL["PAC"]["buiten"],
        "pac_overig_binnen": t["PACOverig"]["binnen"] * rk.UUR_TABEL["PAC"]["binnen"],
        "montage_kabelgoot": kabelgoot_m * 0.25,
        "montage_toebehoren": rk.montage_toebehoren_uren(staat),
        "leiding_hard_2pijps": lm["hard_2pijps"] * 0.25,
        "leiding_zacht_2pijps": lm["zacht_2pijps"] * 0.25,
        "leiding_hard_3pijps": lm["hard_3pijps"] * 0.33,
    }


def _vul_uren(w: SheetSchrijver, staat: dict[str, Any], berekening: dict[str, Any]) -> None:
    uren_staat = staat["uren"]
    uren_out = berekening["uren"]

    def eenvoudige_rol(rol: str, totaal_rij: int, werk_rij: int, reis_rij: int, f_rij: int) -> None:
        werk = _num(uren_staat[rol].get("werk"))
        reis = _num(uren_staat[rol].get("reis"))
        w.zet(f"B{werk_rij}", werk); w.zet(f"C{werk_rij}", werk)
        w.zet(f"B{reis_rij}", reis); w.zet(f"C{reis_rij}", reis)
        tarief = _num(uren_staat[rol].get("tarief"))
        w.zet(f"F{f_rij}", tarief)
        definitief = uren_out[rol]["definitief"]
        w.zet(f"A{totaal_rij}", definitief)
        w.zet(f"H{totaal_rij}", definitief * tarief)

    eenvoudige_rol("projectmanager", 330, 331, 332, 330)
    eenvoudige_rol("projectleider", 333, 334, 335, 333)
    eenvoudige_rol("werkvoorbereider", 336, 337, 338, 336)
    eenvoudige_rol("engineering", 339, 340, 341, 339)

    # Servicemonteur (343): rijen 344-353 zijn de voorstel-opbouw, rekenkern
    # kent alleen "auto" (centrale regelaar), "vrfIbs" en één vrije "overig"
    # -- die laatste komt op rij 347 (TOESLAG UREN OPTIONEEL), de enige van
    # de resterende sjabloonregels die als vrij invulveld bedoeld is.
    sm = rk.servicemonteur_voorstel(staat)
    w.zet("B344", sm["auto"]); w.zet("C344", sm["auto"])
    w.zet("B345", sm["vrfIbs"]); w.zet("C345", sm["vrfIbs"])
    overig = _num(uren_staat["servicemonteur"].get("overig"))
    w.zet("B347", overig); w.zet("C347", overig)
    w.zet("B354", sm["reis"]); w.zet("C354", sm["reis"])
    tarief_sm = _num(uren_staat["servicemonteur"].get("tarief"))
    w.zet("F343", tarief_sm)
    definitief_sm = uren_out["servicemonteur"]["definitief"]
    w.zet("A343", definitief_sm)
    w.zet("H343", definitief_sm * tarief_sm)

    # Hoofd- en hulpmonteur (356/377): identieke opbouw, zie
    # rekenkern.monteur_werkuren_auto(). De uitsplitsing hieronder is puur
    # voor de leesbaarheid van het blad -- het totaal (A356/A377) komt
    # rechtstreeks uit rekenkern, ook als daar een handmatige override op
    # staat (dan wijkt het totaal af van de som van deze rijen, met opzet).
    termen = _monteur_termen(staat)
    reis_monteur = rk.reisuren_monteur(staat)
    for rol, totaal_rij, rijen in (
        ("hoofdmonteur", 356, dict(vrf_buiten=357, vrf_binnen=358, verdeelboxen=359, rac_buiten=360,
                                    rac_binnen=361, pac_overig_buiten=362, pac_overig_binnen=363,
                                    montage_kabelgoot=364, montage_toebehoren=365,
                                    leiding_hard_2pijps=366, leiding_zacht_2pijps=367, leiding_hard_3pijps=368,
                                    reis=375, f=356)),
        ("hulpmonteur", 377, dict(vrf_buiten=378, vrf_binnen=379, verdeelboxen=380, rac_buiten=381,
                                   rac_binnen=382, pac_overig_buiten=383, pac_overig_binnen=384,
                                   montage_kabelgoot=385, montage_toebehoren=386,
                                   leiding_hard_2pijps=387, leiding_zacht_2pijps=388, leiding_hard_3pijps=389,
                                   reis=396, f=377)),
    ):
        for term, rijnum in rijen.items():
            if term in ("reis", "f"):
                continue
            waarde = termen[term]
            w.zet(f"B{rijnum}", waarde); w.zet(f"C{rijnum}", waarde)
        w.zet(f"B{rijen['reis']}", reis_monteur); w.zet(f"C{rijen['reis']}", reis_monteur)
        tarief = _num(uren_staat[rol].get("tarief"))
        w.zet(f"F{rijen['f']}", tarief)
        definitief = uren_out[rol]["definitief"]
        w.zet(f"A{totaal_rij}", definitief)
        w.zet(f"H{totaal_rij}", definitief * tarief)


def _vul_kosten_lijst(
    w: SheetSchrijver, lijst: list[dict[str, Any]], rijen: dict[str, int], lege_rijen: list[int]
) -> None:
    """Uitbesteding/equipment: vaste rijen voor de bekende standaardregels
    (gematcht op omschrijving), eigen toegevoegde regels naar de vrije
    "lege" rijen aan het eind van dat blok."""
    vrije_rijen = list(lege_rijen)
    for item in lijst:
        row = rijen.get(item.get("omschrijving"))
        nieuw = row is None
        if nieuw:
            if not vrije_rijen:
                continue  # meer eigen regels dan het sjabloon vrije rijen heeft
            row = vrije_rijen.pop(0)
            w.zet(f"B{row}", item.get("omschrijving") or "")
            w.zet(f"E{row}", item.get("eenheid") or "")
        aantal = _num(item.get("aantal"))
        prijs = item.get("prijs")
        w.zet(f"A{row}", aantal)
        if prijs is None or prijs == "":
            w.zet(f"F{row}", "op aanvraag")
            w.zet(f"H{row}", "")
        else:
            w.zet(f"F{row}", float(prijs))
            w.zet(f"H{row}", aantal * float(prijs))


def _vul_uitbesteding_equipment_overig(
    w: SheetSchrijver, staat: dict[str, Any], berekening: dict[str, Any], gegevens: dict[str, Any]
) -> None:
    marge = berekening["marge"]
    _vul_kosten_lijst(w, staat["uitbesteding"], UITBESTEDING_RIJEN, UITBESTEDING_LEGE_RIJEN)
    w.zet("H417", marge["uitbesteding"]["totaal"])
    _vul_kosten_lijst(w, staat["equipment"], EQUIPMENT_RIJEN, EQUIPMENT_LEGE_RIJEN)
    w.zet("H429", marge["equipment"]["totaal"])

    w.zet("A432", marge["parkeeruren"])
    w.zet("D433", staat["instellingen"]["provincie"])
    w.zet("F433", _parkeertarief(staat, gegevens))
    w.zet("H433", marge["parkeerkosten"])
    w.zet("A434", _num(staat["overig"].get("nachten")))
    w.zet("F434", _num(staat["overig"].get("nachtprijs")))
    w.zet("H434", marge["overnachtingen"])
    w.zet("H437", marge["reiskosten"])

    bonus_pct, provisie_pct = _bonus_en_provisie_pct(staat, gegevens)
    w.zet("D440", staat["instellingen"]["bonusklant"])
    w.zet("F440", bonus_pct)
    w.zet("D443", staat["instellingen"]["provisieklant"])
    w.zet("F443", provisie_pct)


# --------------------------------------------------------------------------
# Quotation sheet
# --------------------------------------------------------------------------

def _vul_quotation(
    w: SheetSchrijver, staat: dict[str, Any], berekening: dict[str, Any], gegevens: dict[str, Any]
) -> None:
    uren_staat = staat["uren"]
    uren_out = berekening["uren"]
    marge = berekening["marge"]

    def rolkosten(rol: str) -> float:
        return uren_out[rol]["definitief"] * _num(uren_staat[rol].get("tarief"))

    w.zet("M21", _num(uren_staat["projectmanager"].get("tarief")))
    w.zet("R21", rolkosten("projectmanager"))
    w.zet("M22", _num(uren_staat["projectleider"].get("tarief")))
    w.zet("R22", rolkosten("projectleider") + rolkosten("engineering"))
    w.zet("M23", _num(uren_staat["werkvoorbereider"].get("tarief")))
    w.zet("R23", rolkosten("werkvoorbereider"))
    w.zet("I24", "Verkoper")
    w.zet("L24", uren_out["verkoper"]["definitief"])
    w.zet("M24", _num(uren_staat["verkoper"].get("tarief")))
    w.zet("R24", rolkosten("verkoper"))
    w.zet("M25", _num(uren_staat["servicemonteur"].get("tarief")))
    w.zet("R25", rolkosten("servicemonteur"))
    w.zet("M26", _num(uren_staat["hoofdmonteur"].get("tarief")))
    w.zet("R26", rolkosten("hoofdmonteur"))
    w.zet("M29", _num(uren_staat["hulpmonteur"].get("tarief")))
    w.zet("R29", rolkosten("hulpmonteur"))

    # SHORT TRIP ALLOWANCE / TRANSFER QUOTATION FULL COST (I38/I39): twee
    # vaste Q-kosten-regels die in het kale sjabloon zelf als R38=M38*P38 /
    # R39=M39*P39-formules staan -- hier, net als de rest van dit blad, wordt
    # de kant-en-klare rekenkern-waarde geschreven en de formule verwijderd
    # (zie de moduledocstring). R42 ("S/TOTAL LABOUR COSTS") is in het
    # sjabloon zelf SUM(R34:R40), dus arbeid + deze twee regels samen.
    w.zet("M38", _num(staat["overig"].get("shortTripDagen")))
    w.zet("P38", _num(staat["overig"].get("shortTripTarief")))
    w.zet("R38", marge["shortTripKosten"])
    w.zet("M39", _num(staat["overig"].get("transferUren")))
    w.zet("P39", _num(staat["overig"].get("transferTarief")))
    w.zet("R39", marge["transferKosten"])
    w.zet("R42", marge["arbeid"] + marge["shortTripKosten"] + marge["transferKosten"])

    sectie_totalen = _sectie_totalen(berekening["materiaal"])
    for i, sectie in enumerate(SECTIE_VOLGORDE):
        w.zet(f"E{30 + i}", sectie_totalen[sectie])
    w.zet("E41", marge["materiaal"]["totaal"])

    w.zet("E44", marge["uitbesteding"]["totaal"])
    w.zet("E50", marge["uitbesteding"]["totaal"])
    w.zet("E53", marge["equipment"]["totaal"])
    w.zet("E54", marge["contingencyReserves"])
    w.zet("E55", marge["contingencyOnderhandeling"])
    w.zet("E59", marge["equipment"]["totaal"] + marge["contingencyReserves"] + marge["contingencyOnderhandeling"])

    w.zet("R46", marge["materiaal"]["totaal"])
    w.zet("R47", marge["overheadInkoop"])
    w.zet("R48", marge["uitbesteding"]["totaal"])
    w.zet("R49", marge["overheadUitbesteding"])
    w.zet("R51", marge["equipment"]["totaal"] + marge["contingencyReserves"] + marge["contingencyOnderhandeling"])
    w.zet("R52", marge["reiskosten"])
    w.zet("R59", marge["overigeKosten"])

    w.zet("R61", marge["ic"])
    w.zet("R63", marge["lost"])
    w.zet("R64", marge["financial"])
    w.zet("R65", marge["groupFees"])
    w.zet("R67", marge["fullCost"])

    w.zet("R71", marge["projectPrice"])
    w.zet("R69", marge["resultaat"])
    w.zet("P69", marge["resultaatPct"])
    bonus_pct, _ = _bonus_en_provisie_pct(staat, gegevens)
    w.zet("P73", bonus_pct)
    w.zet("R73", marge["omzetbonus"])
    w.zet("R74", marge["garantie"])
    w.zet("R76", marge["verkoopprijs"])


# --------------------------------------------------------------------------
# samenvoegen tot een .xlsx
# --------------------------------------------------------------------------

def _workbook_naar_normale_sheet(xml: str) -> str:
    return xml.replace(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    )


def _content_types_zonder_calcchain(xml: str) -> str:
    return re.sub(r'<Override PartName="/xl/calcChain\.xml"[^/]*/>', "", xml)


def _workbook_rels_zonder_calcchain(xml: str) -> str:
    return re.sub(r'<Relationship [^>]*Target="calcChain\.xml"[^/]*/>', "", xml)


def _workbook_met_fullcalc(xml: str) -> str:
    if "fullCalcOnLoad" in xml:
        return xml
    if "<calcPr " in xml:
        return re.sub(r"<calcPr ", '<calcPr fullCalcOnLoad="1" ', xml, count=1)
    return xml.replace("</workbook>", '<calcPr fullCalcOnLoad="1"/></workbook>')


class CalculatiebladFout(Exception):
    pass


def schrijf_calculatieblad(
    staat: dict[str, Any],
    gegevens: dict[str, Any] | None = None,
    sjabloon_pad: Path | str = SJABLOON,
) -> bytes:
    """Bouwt het ingevulde Excel-calculatieblad voor één calculatie-staat en
    geeft de bytes van het resulterende .xlsx-bestand terug."""
    sjabloon_pad = Path(sjabloon_pad)
    if not sjabloon_pad.exists():
        raise CalculatiebladFout(f"sjabloon niet gevonden: {sjabloon_pad}")
    gegevens = gegevens or rk.laad_gegevens()
    berekening = rk.bereken(staat, gegevens)

    with zipfile.ZipFile(sjabloon_pad) as zin:
        namen = zin.namelist()
        inhoud: dict[str, bytes] = {n: zin.read(n) for n in namen}

    calc_xml = inhoud[SHEET_CALCULATIE].decode("utf-8")
    w_calc = SheetSchrijver(calc_xml)
    _vul_kop(w_calc, staat, berekening)
    _vul_installaties(w_calc, staat)
    _vul_materiaal(w_calc, berekening)
    _vul_uren(w_calc, staat, berekening)
    _vul_uitbesteding_equipment_overig(w_calc, staat, berekening, gegevens)
    inhoud[SHEET_CALCULATIE] = w_calc.xml.encode("utf-8")

    quot_xml = inhoud[SHEET_QUOTATION].decode("utf-8")
    w_quot = SheetSchrijver(quot_xml)
    _vul_quotation(w_quot, staat, berekening, gegevens)
    inhoud[SHEET_QUOTATION] = w_quot.xml.encode("utf-8")

    inhoud[CONTENT_TYPES] = _content_types_zonder_calcchain(
        _workbook_naar_normale_sheet(inhoud[CONTENT_TYPES].decode("utf-8"))
    ).encode("utf-8")
    inhoud[WORKBOOK_RELS] = _workbook_rels_zonder_calcchain(
        inhoud[WORKBOOK_RELS].decode("utf-8")
    ).encode("utf-8")
    inhoud[WORKBOOK] = _workbook_met_fullcalc(inhoud[WORKBOOK].decode("utf-8")).encode("utf-8")
    del inhoud[CALC_CHAIN]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for naam in namen:
            if naam == CALC_CHAIN:
                continue
            zout.writestr(naam, inhoud[naam])
    return buf.getvalue()


# ============================================================================
# Een al ingevuld calculatieblad terug INLEZEN naar een calculatie-staat.
# ============================================================================
#
# Op verzoek van Lars (2 oktober 2026): alle bestaande calculaties staan al
# in dit Excel-sjabloon (zoals vóór deze tool met de hand werd bijgehouden),
# dus naast het hierboven beschreven downloaden moet een al ingevulde
# .xlsx ook weer INGELADEN kunnen worden -- zodat voor een bestaande
# calculatie alsnog snel een brief gemaakt kan worden.
#
# **Het vertrekpunt is exact de omgekeerde celtabel van schrijf_calculatieblad
# hierboven** -- elke cel die _vul_* daar als eigen, overschrijfbare INVOER
# beschrijft, is hier een leesbare bron voor een state-veld; elke cel die
# daar een AFGELEIDE/berekende waarde is (bijv. B5/B6/B9, de "definitief"-
# formules in de uren-sectie, F440/F443, alle Quotation-sheet-totalen) wordt
# hier bewust NIET gelezen -- die komt vanzelf weer goed zodra
# rekenkern.bereken() op de geïmporteerde staat draait. Dat is dezelfde
# "één plek per berekening"-regel als de rest van dit bestand, nu toegepast
# op import: wij lezen nooit een rekenkern-uitkomst terug als ware het invoer.
#
# **Moet zowel een bestand aankunnen dat deze tool zelf exporteerde (platte
# getallen/`inlineStr`, zie SheetSchrijver hierboven) als een ECHT met de
# hand ingevuld bestand uit de oorspronkelijke, losstaande Excel-tool** --
# en dat laatste is de eigenlijke reden voor dit bestaan: zo'n bestand laat de
# formules van het sjabloon over het algemeen gewoon intact (iemand vult het
# gewoon in zoals een willekeurig Excel-bestand) en gebruikt voor tekst bijna
# altijd shared strings (`t="s"`, een verwijzing naar `xl/sharedStrings.xml`)
# in plaats van inline-tekst -- SheetLezer hieronder leest daarom altijd de
# gecachte `<v>`/tekstwaarde die Excel bij een cel bewaart, ongeacht of die
# cel een formule heeft: dat is precies wat Excel bij de laatste keer
# opslaan ook liet zien, en voor een formuleset die een eigen invoerveld
# alleen maar doorrekent (bijv. A343 = ROUNDUP(...)) is dat exact de waarde
# die we willen -- zie _lees_uren hieronder voor hoe we die vervolgens
# onderscheiden van een bewuste handmatige override.
#
# **Niet herleidbaar: losse installatieregels.** schrijf_calculatieblad
# exporteert per systeemsoort alleen het TOTAAL aantal buiten-/binnendelen
# (B12/13, B16/17, B20/21, B24/25) -- zo deed de oorspronkelijke, losstaande
# Excel-tool dit al vóór deze tool bestond; er is geen cel die vastlegt uit
# hoeveel LOSSE installaties (met een eigen merk/montagewijze/model) die
# totalen zijn opgebouwd. Import maakt daarom per systeemsoort met een
# niet-nul totaal precies ÉÉN synthetische installatieregel aan met dat
# totaal, en laat merk/montagewijze/model bewust leeg -- nooit een gok welke
# installatie(s) dat totaal vormen. De geretourneerde waarschuwingenlijst
# noemt dit altijd expliciet zodra er installaties zijn geïmporteerd.

# Shared strings (xl/sharedStrings.xml): <si><t>...</t></si> per string, index
# = positie in dat bestand. Een <si> kan de tekst in meerdere <r><t>-runs
# opsplitsen (rich text/verschillende opmaak binnen één cel); die runs worden
# hier weer aaneengeplakt, de opmaak zelf doet er voor een celwaarde niet toe.
_SI_PATROON = re.compile(r"<si>(.*?)</si>", re.DOTALL)
_T_PATROON = re.compile(r"<t[^>]*>(.*?)</t>", re.DOTALL)


def _tekst_unescape(s: str) -> str:
    return (s.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'")
             .replace("&amp;", "&"))


def _laad_shared_strings(inhoud: dict[str, bytes]) -> list[str]:
    ruw = inhoud.get("xl/sharedStrings.xml")
    if not ruw:
        return []
    xml = ruw.decode("utf-8")
    return [_tekst_unescape("".join(_T_PATROON.findall(si.group(1))))
            for si in _SI_PATROON.finditer(xml)]


def _sheet_pad(inhoud: dict[str, bytes], tabblad_naam: str) -> str:
    """Zoekt het interne bestandspad (bijv. "xl/worksheets/sheet5.xml") bij
    een tabbladnaam, via workbook.xml + workbook.xml.rels -- niet hardcoded
    op "sheet5.xml"/"sheet4.xml" zoals de schrijfkant hierboven doet, want een
    écht, jarenlang met de hand bijgehouden bestand kan een andere interne
    volgorde hebben dan het sjabloon op dit moment, ook al heet het tabblad
    zelf nog steeds "Calculatie"/"Quotation sheet" (de tabnaam is wat de
    gebruiker in Excel ziet en dus stabiel blijft)."""
    try:
        wb = inhoud["xl/workbook.xml"].decode("utf-8")
    except KeyError as fout:
        raise CalculatiebladFout("dit is geen geldig Excel-bestand (geen workbook.xml)") from fout

    rid = None
    for sheet_tag in re.finditer(r"<sheet\b[^>]*/?>", wb):
        tag = sheet_tag.group(0)
        if re.search(r'\bname="' + re.escape(tabblad_naam) + r'"', tag):
            m = re.search(r'\br:id="(rId\d+)"', tag)
            if m:
                rid = m.group(1)
                break
    if rid is None:
        raise CalculatiebladFout(f"tabblad {tabblad_naam!r} niet gevonden in dit werkboek")

    try:
        rels = inhoud["xl/_rels/workbook.xml.rels"].decode("utf-8")
    except KeyError as fout:
        raise CalculatiebladFout("dit is geen geldig Excel-bestand (geen workbook.xml.rels)") from fout
    m = re.search(r'<Relationship Id="' + re.escape(rid) + r'"[^>]*Target="([^"]+)"', rels)
    if not m:
        raise CalculatiebladFout(f"kan tabblad {tabblad_naam!r} niet terugvinden (ontbrekende relatie)")
    doel = m.group(1).lstrip("/")
    return doel if doel.startswith("xl/") else f"xl/{doel}"


class SheetLezer:
    """Leest cel-waarden uit de ruwe XML van één werkblad -- het omgekeerde
    van SheetSchrijver hierboven. `waarde()` geeft een float, een str, of
    None (lege/ontbrekende cel) terug, ongeacht of de cel plat is of een
    formule heeft (dan de laatst gecachte `<v>`, zie de moduledocstring
    hierboven voor waarom dat hier precies goed is)."""

    def __init__(self, xml: str, shared_strings: list[str]):
        self.xml = xml
        self._shared = shared_strings

    def _cel_match(self, ref: str) -> re.Match[str] | None:
        patroon = re.compile(r'<c r="' + re.escape(ref) + r'"([^>]*?)(?:/>|>(.*?)</c>)', re.DOTALL)
        return patroon.search(self.xml)

    def waarde(self, ref: str) -> float | str | None:
        m = self._cel_match(ref)
        if not m or m.group(2) is None:
            return None
        attrs, binnen = m.group(1), m.group(2)
        type_m = re.search(r'\bt="([a-zA-Z]+)"', attrs)
        t = type_m.group(1) if type_m else None

        if t == "inlineStr":
            return _tekst_unescape("".join(_T_PATROON.findall(binnen)))
        v_m = re.search(r"<v>(.*?)</v>", binnen, re.DOTALL)
        if t == "s":
            if not v_m:
                return None
            idx = int(v_m.group(1))
            return self._shared[idx] if 0 <= idx < len(self._shared) else None
        if t == "str":
            return _tekst_unescape(v_m.group(1)) if v_m else None
        if t in ("b", "e"):
            return None  # boolean/formulefout (#VALUE! e.d.) -- geen bruikbare invoer
        if not v_m or v_m.group(1) == "":
            return None
        try:
            return float(v_m.group(1))
        except ValueError:
            return None

    def tekst(self, ref: str) -> str:
        w = self.waarde(ref)
        if w is None:
            return ""
        # Een "tekst"-kolom kan best een kaal getal bevatten -- aangetroffen
        # in een écht ingevuld bestand (Lars, 2 oktober 2026): iemand typte
        # "1" in de TYPE-kolom van een eigen APPARATUUR-regel. str(1.0) geeft
        # dan "1.0" -- dezelfde opmaak als _getal_tekst() hierboven (de
        # schrijfkant) voorkomt dat exact zo'n lelijke ".0" hier weer naar
        # buiten lekt.
        if isinstance(w, (int, float)):
            return _getal_tekst(w)
        return str(w).strip()

    def getal(self, ref: str, default: float = 0.0) -> float:
        w = self.waarde(ref)
        return float(w) if isinstance(w, (int, float)) else default


def _prijs_uit(waarde: float | str | None) -> float | None:
    """"op aanvraag" (of iets anders niet-numeriek) wordt net als bij een
    leeg veld None -- nooit een verzonnen prijs."""
    return waarde if isinstance(waarde, (int, float)) else None


def _lees_kop(l: SheetLezer, staat: dict[str, Any]) -> None:
    meta = staat["meta"]
    meta["qnummer"] = l.tekst("B1")
    meta["projectnaam"] = l.tekst("B2")
    meta["klantnaam"] = l.tekst("B3")
    meta["klantnummer"] = l.tekst("B4")
    meta["uitgangspunten"] = l.tekst("D1")
    # Geen cel in het sjabloon bewaart de offertedatum (zie _vul_kop
    # hierboven, die 'm ook nergens schrijft) -- vandaag is hetzelfde, enige
    # zinnige startpunt als een gloednieuw project (nieuwe_staat() aan de
    # scherm/calculatie.js-kant doet dat ook al zo).
    meta["datum"] = datetime.date.today().isoformat()


def _lees_instellingen(
    l: SheetLezer, staat: dict[str, Any], gegevens: dict[str, Any], waarschuwingen: list[str]
) -> None:
    instellingen = staat["instellingen"]

    moeilijkheid = l.tekst("B7")
    if moeilijkheid in rk.MOEILIJKHEID_FACTOR:
        instellingen["moeilijkheid"] = moeilijkheid
    elif moeilijkheid:
        waarschuwingen.append(
            f"onbekende moeilijkheidsgraad {moeilijkheid!r} in het bestand -- teruggevallen op 'Standaard'")

    instellingen["reistijd"] = l.getal("B8", 1)

    provincies = {p["provincie"] for p in gegevens["parkeertarieven"]}
    provincie = l.tekst("D433")
    if provincie in provincies:
        instellingen["provincie"] = provincie
    elif provincie:
        waarschuwingen.append(
            f"onbekende provincie {provincie!r} in het bestand -- teruggevallen op 'Geen parkeerkosten'")

    bonusklanten = {b["klant"] for b in gegevens["omzetbonus_provisie"]["omzetbonus"]}
    bonusklant = l.tekst("D440")
    if bonusklant in bonusklanten:
        instellingen["bonusklant"] = bonusklant
    elif bonusklant:
        waarschuwingen.append(
            f"onbekende bonusklant {bonusklant!r} in het bestand -- teruggevallen op 'Geen bonusdragende klant'")

    provisieklanten = {p["klant"] for p in gegevens["omzetbonus_provisie"]["provisie"]}
    provisieklant = l.tekst("D443")
    if provisieklant in provisieklanten:
        instellingen["provisieklant"] = provisieklant
    elif provisieklant:
        waarschuwingen.append(
            f"onbekende provisieklant {provisieklant!r} in het bestand -- teruggevallen op 'Geen provisie'")


# (systeemsoort, cel aantal buitendelen, cel aantal binnendelen) -- zie
# _vul_installaties hierboven, en de moduledocstring voor de beperking dat
# hier alleen het TOTAAL per systeemsoort uit valt te lezen, nooit losse
# installatieregels.
_INSTALLATIE_CELLEN: list[tuple[str, str, str]] = [
    ("VRF", "B12", "B13"),
    ("RAC", "B16", "B17"),
    ("PAC", "B20", "B21"),
    ("Overig", "B24", "B25"),
]


def _lees_installaties(l: SheetLezer, staat: dict[str, Any]) -> None:
    for systeemsoort, buiten_ref, binnen_ref in _INSTALLATIE_CELLEN:
        buiten = l.getal(buiten_ref)
        binnen = l.getal(binnen_ref)
        if not buiten and not binnen:
            continue
        staat["installaties"].append({
            "id": rk._nieuw_id(), "systeemsoort": systeemsoort,
            "merk": "", "montagewijze": "", "typeBinnendeel": "", "materiaalId": None,
            "aantalBuitendelen": buiten, "aantalBinnendelen": binnen,
        })


def _lees_materiaal(l: SheetLezer, staat: dict[str, Any], gegevens: dict[str, Any]) -> None:
    yimm = gegevens["yimm"]
    for cat_entry in gegevens["materiaal_catalogus"]:
        row = cat_entry.get("row")
        if row is None:
            continue
        aantal = l.getal(f"A{row}")
        if not aantal:
            continue
        # De structurele velden (sectie/bron/artikelcode/leiding_categorie/...)
        # zijn intrinsieke eigenschappen van déze catalogusrij en komen dus uit
        # de (huidige) catalogus; omschrijving/eenheid/prijs zijn wat ooit in
        # déze offerte werd getoond en komen daarom uit het Excel-bestand zelf
        # -- een prijs kan intussen gewijzigd zijn, en dit moet de historische
        # offerte reproduceren, niet een nieuwe met de prijzen van vandaag.
        regel = rk.materiaal_regel_uit_catalogus(cat_entry, yimm)
        regel["aantal"] = aantal
        omschrijving = l.tekst(f"D{row}")
        if omschrijving:
            regel["omschrijving"] = omschrijving
        eenheid = l.tekst(f"E{row}")
        if eenheid:
            regel["eenheid"] = eenheid
        regel["prijs"] = _prijs_uit(l.waarde(f"F{row}"))
        staat["materiaal"].append(regel)


def _lees_overig(l: SheetLezer, staat: dict[str, Any]) -> None:
    staat["overig"]["nachten"] = l.getal("A434", 0)
    staat["overig"]["nachtprijs"] = l.getal("F434", 150)


def _lees_quotation_overig(lq: SheetLezer, staat: dict[str, Any]) -> None:
    """SHORT TRIP ALLOWANCE / TRANSFER QUOTATION FULL COST (Quotation
    sheet!M38/P38, M39/P39) -- zie _vul_quotation voor de schrijfkant. Staan
    op Quotation sheet, niet Calculatie, dus een eigen functie met `lq` in
    plaats van `_lees_overig` hierboven uit te breiden."""
    overig = staat["overig"]
    overig["shortTripDagen"] = lq.getal("M38", 0)
    overig["shortTripTarief"] = lq.getal("P38", 0)
    overig["transferUren"] = lq.getal("M39", 0)
    overig["transferTarief"] = lq.getal("P39", rk.DEFAULT_TARIEVEN["projectmanager"])


def _lees_marge_van_quotation(lq: SheetLezer, staat: dict[str, Any]) -> None:
    staat["marge"]["contingencyReserves"] = lq.getal("E54", 0)
    staat["marge"]["contingencyOnderhandeling"] = lq.getal("E55", 0)
    # R71 staat in een kersvers/nooit ingevuld sjabloon al op een kale 0 (zie
    # de moduledocstring) -- dat is niet te onderscheiden van een bewust
    # ingevulde verkoopprijs van nul euro, die in de praktijk nooit voorkomt.
    # Een gelezen 0 wordt daarom net als leeg behandeld: None, net als een
    # project waarvoor nog geen prijs is bepaald.
    prijs = lq.getal("R71")
    staat["marge"]["projectPrice"] = prijs if prijs else None


def _lees_kosten_lijst(
    l: SheetLezer, rijen: dict[str, int], lege_rijen: list[int], defaults: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Uitbesteding/equipment: de standaardregels staan altijd op hun vaste
    rij (zie rijen), eigen toegevoegde regels ("eigen regel") in de vrije
    rijen aan het eind -- het omgekeerde van _vul_kosten_lijst hierboven."""
    uit: list[dict[str, Any]] = []
    for default in defaults:
        naam = default["omschrijving"]
        row = rijen[naam]
        uit.append({
            "id": rk._nieuw_id(), "omschrijving": naam, "eenheid": default["eenheid"],
            "prijs": _prijs_uit(l.waarde(f"F{row}")), "aantal": l.getal(f"A{row}", 0),
            "favoriet": default["favoriet"],
        })
    for row in lege_rijen:
        omschrijving = l.tekst(f"B{row}")
        if not omschrijving:
            continue
        uit.append({
            "id": rk._nieuw_id(), "omschrijving": omschrijving, "eenheid": l.tekst(f"E{row}"),
            "prijs": _prijs_uit(l.waarde(f"F{row}")), "aantal": l.getal(f"A{row}", 0),
            "favoriet": True,
        })
    return uit


def _lees_uitbesteding_equipment(l: SheetLezer, staat: dict[str, Any]) -> None:
    staat["uitbesteding"] = _lees_kosten_lijst(l, UITBESTEDING_RIJEN, UITBESTEDING_LEGE_RIJEN, rk.UITBESTEDING_DEFAULTS)
    staat["equipment"] = _lees_kosten_lijst(l, EQUIPMENT_RIJEN, EQUIPMENT_LEGE_RIJEN, rk.EQUIPMENT_DEFAULTS)


_OVEREENKOMST_MARGE = 0.01  # afrondingsmarge bij het vergelijken van "definitief" met het herberekende voorstel


def _lees_uren(l: SheetLezer, lq: SheetLezer, staat: dict[str, Any]) -> None:
    """Vereist dat instellingen/installaties/materiaal/overig al in `staat`
    staan (zie de aanroep in lees_calculatieblad) -- de override-detectie
    hieronder herberekent het automatische voorstel met rekenkern zelf, en
    dat voorstel hangt van al die velden af."""
    uren = staat["uren"]

    def eenvoudige_rol(rol: str, werk_rij: int, reis_rij: int, f_rij: int) -> None:
        uren[rol]["werk"] = l.getal(f"B{werk_rij}", 0)
        uren[rol]["reis"] = l.getal(f"B{reis_rij}", 0)
        uren[rol]["tarief"] = l.getal(f"F{f_rij}", rk.DEFAULT_TARIEVEN[rol])

    eenvoudige_rol("projectmanager", 331, 332, 330)
    eenvoudige_rol("projectleider", 334, 335, 333)
    eenvoudige_rol("werkvoorbereider", 337, 338, 336)
    eenvoudige_rol("engineering", 340, 341, 339)

    uren["servicemonteur"]["overig"] = l.getal("B347", 0)
    uren["servicemonteur"]["tarief"] = l.getal("F343", rk.DEFAULT_TARIEVEN["servicemonteur"])
    uren["hoofdmonteur"]["tarief"] = l.getal("F356", rk.DEFAULT_TARIEVEN["hoofdmonteur"])
    uren["hulpmonteur"]["tarief"] = l.getal("F377", rk.DEFAULT_TARIEVEN["hulpmonteur"])

    # Verkoper staat alleen op Quotation sheet (geen eigen rij op Calculatie),
    # zie _vul_quotation hierboven.
    uren["verkoper"]["uren"] = lq.getal("L24", 0)
    uren["verkoper"]["tarief"] = lq.getal("M24", rk.DEFAULT_TARIEVEN["verkoper"])

    # A343/A356/A377 zijn in het sjabloon zelf formules die het voorstel
    # uitrekenen (ROUNDUP(...), identiek aan rk.servicemonteur_voorstel()/
    # monteur_voorstel()) -- maar met de hand te overschrijven, vandaar de
    # override-velden in rk.nieuwe_staat(). Een vergelijking met wat dat
    # voorstel NU (met de net geïmporteerde installaties/materiaal/overig)
    # zou zijn, onderscheidt "nooit aangeraakt" van "bewust overschreven":
    # wijken ze meer dan een kleine afrondingsmarge af, dan was het een
    # override, en komt die met de geïmporteerde, echte waarde mee.
    sm_voorstel = rk.servicemonteur_voorstel(staat)["totaal"]
    sm_definitief = l.getal("A343")
    if abs(sm_definitief - sm_voorstel) > _OVEREENKOMST_MARGE:
        uren["servicemonteur"]["override"] = sm_definitief

    mv_voorstel = rk.monteur_voorstel(staat)
    for rol, ref in (("hoofdmonteur", "A356"), ("hulpmonteur", "A377")):
        definitief = l.getal(ref)
        if abs(definitief - mv_voorstel) > _OVEREENKOMST_MARGE:
            uren[rol]["override"] = definitief


def lees_calculatieblad(
    inhoud_bytes: bytes, gegevens: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[str]]:
    """Leest een ingevuld Excel-calculatieblad (dit sjabloon, met de hand
    ingevuld in de oorspronkelijke, losstaande Excel-tool, of hier zelf eerder
    mee geëxporteerd) terug in een calculatie-staat die rekenkern.bereken()
    kan doorrekenen -- zie de uitleg bovenaan deze sectie voor de precieze
    omgekeerde celtabel en waarom losse installatieregels hier niet uit te
    herleiden zijn.

    Geeft (staat, waarschuwingen) terug: `staat` heeft exact de vorm van
    rekenkern.nieuwe_staat(), `waarschuwingen` is een lijst leesbare zinnen
    over wat niet herkend kon worden (en dus op een standaardwaarde is
    teruggevallen) of wat de gebruiker na het inladen zelf moet controleren --
    nooit een stille gok, net als overdracht.py."""
    gegevens = gegevens or rk.laad_gegevens()

    try:
        with zipfile.ZipFile(io.BytesIO(inhoud_bytes)) as zin:
            inhoud = {naam: zin.read(naam) for naam in zin.namelist()}
    except zipfile.BadZipFile as fout:
        raise CalculatiebladFout("dit is geen geldig Excel-bestand (.xlsx)") from fout

    shared_strings = _laad_shared_strings(inhoud)
    calc_pad = _sheet_pad(inhoud, "Calculatie")
    quot_pad = _sheet_pad(inhoud, "Quotation sheet")
    try:
        l = SheetLezer(inhoud[calc_pad].decode("utf-8"), shared_strings)
        lq = SheetLezer(inhoud[quot_pad].decode("utf-8"), shared_strings)
    except KeyError as fout:
        raise CalculatiebladFout(f"tabblad-bestand {fout} ontbreekt in dit .xlsx-bestand") from fout

    staat = rk.nieuwe_staat()
    waarschuwingen: list[str] = []

    _lees_kop(l, staat)
    _lees_instellingen(l, staat, gegevens, waarschuwingen)
    _lees_installaties(l, staat)
    _lees_materiaal(l, staat, gegevens)
    _lees_overig(l, staat)
    _lees_quotation_overig(lq, staat)
    _lees_marge_van_quotation(lq, staat)
    _lees_uitbesteding_equipment(l, staat)
    _lees_uren(l, lq, staat)  # na instellingen/installaties/materiaal/overig, zie daar

    if staat["installaties"]:
        waarschuwingen.append(
            "De installaties zijn overgenomen als totalen per systeemsoort (zo legt het "
            "Excel-blad dit vast), niet als losse installatieregels -- controleer en vul "
            "zelf merk, montagewijze en model aan bij elke installatiekaart."
        )

    return staat, waarschuwingen
