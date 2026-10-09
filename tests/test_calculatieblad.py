"""Toetst het ingevulde Excel-calculatieblad (calculatie/calculatieblad.py).

Er is in deze sandbox geen Excel of LibreOffice Calc beschikbaar om het
resultaat mee te openen (zie CLAUDE.md/git-historie) -- deze tests toetsen
daarom zelf, met dezelfde kale XML-aanpak als de module zelf gebruikt, dat
(a) het resultaat een geldig .xlsx-bestand is (welgevormde XML, geen
calcChain.xml meer) en (b) elke cel die geld of uren voorstelt letterlijk de
waarde bevat die rekenkern.bereken() voor diezelfde staat teruggeeft -- nooit
een andere waarde die een Excel-formule daar zelf zou hebben uitgerekend.

Het tweede deel van dit bestand (vanaf TestInlezenRondje) toetst de
omgekeerde richting, lees_calculatieblad(): een al ingevuld blad terug naar
een calculatie-staat. Die tests draaien zowel tegen bestanden die deze module
zelf exporteert (inlineStr) als tegen het echte, originele sjabloonbestand
zelf (sjablonen/Template_Calculatieblad.xltx, met zijn echte shared strings
en nog intacte sjabloonformules) -- dat laatste is de beste benadering van
een écht met de hand ingevuld bestand die hier zonder een door Lars
aangeleverd voorbeeld te krijgen is; zie CLAUDE.md voor die kanttekening.
"""

from __future__ import annotations

import io
import re
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from calculatie import calculatieblad as cb
from calculatie import rekenkern as rk

GEGEVENS = rk.laad_gegevens()
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _cellen(xlsx_bytes: bytes, sheet_pad: str) -> dict[str, float | str | None]:
    """Leest alle celwaarden van één blad uit de gegenereerde .xlsx, met
    gedeelde en inline strings opgelost -- puur voor het toetsen hier, geen
    onderdeel van calculatieblad.py zelf."""
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        gedeeld = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                gedeeld.append("".join(t.text or "" for t in si.iter(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
        sheet = ET.fromstring(z.read(sheet_pad))

    waarden: dict[str, float | str | None] = {}
    for row in sheet.find("m:sheetData", NS):
        for c in row.findall("m:c", NS):
            ref = c.get("r")
            t = c.get("t")
            if t == "inlineStr":
                is_el = c.find("m:is", NS)
                tekst = "".join(el.text or "" for el in is_el.iter(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")) if is_el is not None else ""
                waarden[ref] = tekst
                continue
            v_el = c.find("m:v", NS)
            if v_el is None:
                waarden[ref] = None
                continue
            if t == "s":
                waarden[ref] = gedeeld[int(v_el.text)]
            elif t in ("str", "b", "e"):
                # str/b/e = cache van een (nog niet aangeraakte) formulecel
                # met een tekst-, boolean- of foutresultaat -- komt hier
                # alleen voor bij ONgemoeide sjabloonrijen (VLOOKUP-
                # omschrijvingen e.d.), nooit bij een cel die deze module
                # zelf beschrijft.
                waarden[ref] = v_el.text
            else:
                waarden[ref] = float(v_el.text)
    return waarden


def _bouw(staat: dict) -> tuple[bytes, dict[str, float | str | None], dict[str, float | str | None], dict]:
    berekening = rk.bereken(staat, GEGEVENS)
    data = cb.schrijf_calculatieblad(staat, GEGEVENS)
    calc = _cellen(data, cb.SHEET_CALCULATIE)
    quot = _cellen(data, cb.SHEET_QUOTATION)
    return data, calc, quot, berekening


def _voorbeeldstaat() -> dict:
    staat = rk.nieuwe_staat()
    staat["meta"] = {"qnummer": "Q.999", "projectnaam": "Testproject", "klantnaam": "Test Klant BV",
                      "klantnummer": "K-1", "uitgangspunten": "Een aanname.", "datum": "2026-09-29"}
    staat["instellingen"]["moeilijkheid"] = "Moeilijk"
    staat["instellingen"]["reistijd"] = 2
    staat["instellingen"]["provincie"] = "Noord-Holland"
    staat["installaties"] = [
        {"id": "a", "systeemsoort": "VRF", "aantalBuitendelen": 1, "aantalBinnendelen": 4},
        {"id": "b", "systeemsoort": "RAC", "aantalBuitendelen": 2, "aantalBinnendelen": 2},
    ]

    def pak(row: int, aantal: float) -> dict:
        entry = next(e for e in GEGEVENS["materiaal_catalogus"] if e["row"] == row)
        regel = rk.materiaal_regel_uit_catalogus(entry, GEGEVENS["yimm"])
        regel["aantal"] = aantal
        return regel

    staat["materiaal"] = [pak(31, 1), pak(34, 2), pak(93, 15.5), pak(102, 8)]
    staat["materiaal"][0]["prijs"] = 450  # projectbestelling: eigen prijs, zoals de UI toelaat
    staat["uren"]["projectmanager"]["werk"] = 4
    staat["uren"]["projectmanager"]["reis"] = 1
    staat["uren"]["servicemonteur"]["overig"] = 3
    staat["uren"]["verkoper"]["uren"] = 6
    staat["uitbesteding"][2]["aantal"] = 1  # Betonboring (heeft altijd een vaste prijs)
    staat["equipment"][0]["aantal"] = 2  # Hoogwerker
    staat["uitbesteding"].append(
        {"id": "x1", "omschrijving": "Eigen extra werk", "eenheid": "POST", "prijs": 123, "aantal": 1, "favoriet": False}
    )
    staat["overig"]["nachten"] = 2
    staat["overig"]["shortTripDagen"] = 2
    staat["overig"]["shortTripTarief"] = 65
    staat["overig"]["transferUren"] = 5
    staat["overig"]["transferTarief"] = 158
    staat["marge"]["contingencyReserves"] = 100
    staat["marge"]["contingencyOnderhandeling"] = 50
    staat["marge"]["projectPrice"] = 15000
    return staat


class TestBestandsstructuur(unittest.TestCase):
    def test_geldige_zip_zonder_calcchain(self):
        data, _, _, _ = _bouw(_voorbeeldstaat())
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIsNone(z.testzip())
            self.assertNotIn("xl/calcChain.xml", z.namelist())
            for naam in ("xl/worksheets/sheet4.xml", "xl/worksheets/sheet5.xml",
                         "[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"):
                ET.fromstring(z.read(naam))  # gooit bij niet-welgevormde XML

    def test_contenttype_is_gewone_werkmap_niet_sjabloon(self):
        data, _, _, _ = _bouw(_voorbeeldstaat())
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            ct = z.read("[Content_Types].xml").decode("utf-8")
        self.assertNotIn("spreadsheetml.template.main+xml", ct)
        self.assertIn("spreadsheetml.sheet.main+xml", ct)

    def test_fullcalconload_gezet(self):
        data, _, _, _ = _bouw(_voorbeeldstaat())
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            wb = z.read("xl/workbook.xml").decode("utf-8")
        self.assertIn('fullCalcOnLoad="1"', wb)

    def test_onbestaand_sjabloon_geeft_duidelijke_fout(self):
        with self.assertRaises(cb.CalculatiebladFout):
            cb.schrijf_calculatieblad(_voorbeeldstaat(), GEGEVENS, sjabloon_pad=Path("/bestaat/niet.xltx"))


class TestKopEnInstallaties(unittest.TestCase):
    def test_meta_en_kop(self):
        staat = _voorbeeldstaat()
        _, calc, _, berekening = _bouw(staat)
        self.assertEqual(calc["B1"], "Q.999")
        self.assertEqual(calc["B2"], "Testproject")
        self.assertEqual(calc["B3"], "Test Klant BV")
        self.assertEqual(calc["B4"], "K-1")
        self.assertEqual(calc["D1"], "Een aanname.")
        self.assertEqual(calc["B7"], "Moeilijk")
        self.assertEqual(calc["B8"], 2)
        self.assertAlmostEqual(calc["B9"], rk.ploegdagen(staat))
        self.assertEqual(calc["B5"], rk.verdeelboxen_aantal(staat))
        self.assertEqual(calc["B6"], 15.5 + 8)  # som van de leidingregels (rijen 93-106)

    def test_installaties_per_systeemsoort(self):
        staat = _voorbeeldstaat()
        _, calc, _, _ = _bouw(staat)
        self.assertEqual((calc["B12"], calc["B13"]), (1, 4))  # VRF
        self.assertEqual((calc["B16"], calc["B17"]), (2, 2))  # RAC
        self.assertEqual((calc["B20"], calc["B21"]), (0, 0))  # PAC
        self.assertEqual((calc["B24"], calc["B25"]), (0, 0))  # Overig

    def test_pac_en_overig_apart_gehouden(self):
        """rekenkern voegt PAC+Overig samen (installatie_totalen); het
        Excel-blad houdt ze als twee losse slots -- dit moet dus zelf
        opnieuw worden uitgesplitst, niet 1-op-1 uit rekenkern gehaald."""
        staat = rk.nieuwe_staat()
        staat["installaties"] = [
            {"id": "a", "systeemsoort": "PAC", "aantalBuitendelen": 3, "aantalBinnendelen": 3},
            {"id": "b", "systeemsoort": "Overig", "aantalBuitendelen": 1, "aantalBinnendelen": 1},
        ]
        _, calc, _, _ = _bouw(staat)
        self.assertEqual((calc["B20"], calc["B21"]), (3, 3))
        self.assertEqual((calc["B24"], calc["B25"]), (1, 1))


class TestMateriaal(unittest.TestCase):
    def test_regels_en_sectiesubtotalen(self):
        staat = _voorbeeldstaat()
        _, calc, _, berekening = _bouw(staat)
        self.assertEqual(calc["A31"], 1)
        self.assertEqual(calc["F31"], 450)
        self.assertEqual(calc["H31"], 450)
        self.assertEqual(calc["A93"], 15.5)
        # calculatieblad.py schrijft getallen met 6 decimalen (ruim genoeg
        # voor een bedrag in euro's) -- de laatste decimalen van een repeterend
        # getal als 23,32903703... gaan daarbij verloren, met opzet.
        self.assertAlmostEqual(calc["H93"], 15.5 * next(
            m["prijs"] for m in berekening["materiaal"] if m["row"] == 93), places=4)
        for sectie, rij in cb.SECTIE_SUBTOTAAL_RIJ.items():
            verwacht = sum(
                rk._num(m["aantal"]) * m["prijs"] for m in berekening["materiaal"]
                if m["sectie"] == sectie and m.get("prijs") is not None
            )
            self.assertAlmostEqual(calc[f"H{rij}"] or 0, verwacht, places=4, msg=sectie)

    def test_afgeleide_regel_komt_ook_letterlijk_terecht(self):
        staat = rk.nieuwe_staat()
        entry = next(e for e in GEGEVENS["materiaal_catalogus"] if e["row"] == 269)  # Frontrooster FD-Q-Z 600
        regel = rk.materiaal_regel_uit_catalogus(entry, GEGEVENS["yimm"])
        regel["aantal"] = 4
        staat["materiaal"] = [regel]
        _, calc, _, berekening = _bouw(staat)
        afgeleid = [m for m in berekening["materiaal"] if m.get("afgeleid")]
        self.assertTrue(afgeleid, "verwacht minstens één automatisch afgeleide materiaalregel")
        for m in afgeleid:
            self.assertEqual(calc[f"A{m['row']}"], rk._num(m["aantal"]))

    def test_onbekende_prijs_geeft_lege_cel_geen_schijnbedrag(self):
        staat = rk.nieuwe_staat()
        onbekend = next(u for u in staat["uitbesteding"] if u["prijs"] is None)
        onbekend["aantal"] = 1
        _, calc, _, _ = _bouw(staat)
        row = cb.UITBESTEDING_RIJEN[onbekend["omschrijving"]]
        self.assertEqual(calc[f"F{row}"], "op aanvraag")
        self.assertIsNone(calc[f"H{row}"])


class TestUren(unittest.TestCase):
    def test_definitieve_uren_en_kosten_matchen_rekenkern(self):
        staat = _voorbeeldstaat()
        _, calc, _, berekening = _bouw(staat)
        for rol, rij in (("projectmanager", 329), ("projectleider", 332), ("werkvoorbereider", 335),
                         ("engineering", 338), ("servicemonteur", 342), ("hoofdmonteur", 355),
                         ("hulpmonteur", 376)):
            definitief = berekening["uren"][rol]["definitief"]
            tarief = staat["uren"][rol]["tarief"]
            self.assertAlmostEqual(calc[f"A{rij}"], definitief, msg=rol)
            self.assertAlmostEqual(calc[f"H{rij}"], definitief * tarief, msg=rol)

    def test_monteur_override_overschrijft_het_blad_ook(self):
        """Een handmatige override (rekenkern se enige weg om af te wijken van
        de auto-formule) moet in het blad ook echt het totaal veranderen --
        dat kan alleen als A355/A376 een letterlijke waarde zijn, geen
        formule die alleen de rijen 356-373 optelt."""
        staat = _voorbeeldstaat()
        staat["uren"]["hoofdmonteur"]["override"] = 5
        _, calc, _, berekening = _bouw(staat)
        self.assertEqual(berekening["uren"]["hoofdmonteur"]["definitief"], 5)
        self.assertEqual(calc["A355"], 5)
        self.assertNotEqual(calc["A355"], calc["A376"])  # hulpmonteur bleef ongemoeid

    def test_verkoper_op_quotation_sheet(self):
        staat = _voorbeeldstaat()
        _, _, quot, berekening = _bouw(staat)
        self.assertEqual(quot["I24"], "Verkoper")
        self.assertEqual(quot["L24"], berekening["uren"]["verkoper"]["definitief"])
        self.assertAlmostEqual(
            quot["R24"], berekening["uren"]["verkoper"]["definitief"] * staat["uren"]["verkoper"]["tarief"]
        )


class TestUitbestedingEquipmentOverig(unittest.TestCase):
    def test_bekende_regel_op_vaste_rij(self):
        staat = _voorbeeldstaat()
        _, calc, _, _ = _bouw(staat)
        self.assertEqual(calc["A402"], 1)  # Betonboring
        self.assertEqual(calc["H402"], 200)
        self.assertEqual(calc["A419"], 2)  # Hoogwerker
        self.assertEqual(calc["H419"], 1400)

    def test_eigen_regel_naar_lege_rij(self):
        staat = _voorbeeldstaat()
        _, calc, _, _ = _bouw(staat)
        self.assertEqual(calc["B411"], "Eigen extra werk")
        self.assertEqual(calc["A411"], 1)
        self.assertEqual(calc["F411"], 123)
        self.assertEqual(calc["H411"], 123)

    def test_meer_eigen_regels_dan_lege_rijen_crasht_niet(self):
        staat = rk.nieuwe_staat()
        for i in range(7):
            staat["uitbesteding"].append(
                {"id": f"x{i}", "omschrijving": f"Extra {i}", "eenheid": "POST", "prijs": 10, "aantal": 1, "favoriet": False}
            )
        data, calc, _, berekening = _bouw(staat)
        # de TOTAALCEL komt rechtstreeks uit rekenkern en blijft dus correct,
        # ook als niet elke regel een eigen rij in het blad kreeg.
        self.assertAlmostEqual(calc["H416"], berekening["marge"]["uitbesteding"]["totaal"])

    def test_totalen_matchen_marge(self):
        staat = _voorbeeldstaat()
        _, calc, _, berekening = _bouw(staat)
        marge = berekening["marge"]
        self.assertAlmostEqual(calc["H416"], marge["uitbesteding"]["totaal"])
        self.assertAlmostEqual(calc["H428"], marge["equipment"]["totaal"])
        self.assertAlmostEqual(calc["H432"], marge["parkeerkosten"])
        self.assertAlmostEqual(calc["H433"], marge["overnachtingen"])
        self.assertAlmostEqual(calc["H436"], marge["reiskosten"])


class TestQuotationSheet(unittest.TestCase):
    def test_marge_opbouw_letterlijk(self):
        staat = _voorbeeldstaat()
        _, _, quot, berekening = _bouw(staat)
        marge = berekening["marge"]
        # R42 ("S/TOTAL LABOUR COSTS") is in het sjabloon zelf SUM(R34:R40),
        # dus arbeid + short trip allowance + transfer quotation full cost --
        # geen los veld in `marge`, vandaar hier samengesteld i.p.v. in de
        # for-loop hieronder.
        self.assertAlmostEqual(
            quot["R42"], marge["arbeid"] + marge["shortTripKosten"] + marge["transferKosten"], places=4)
        for ref, veld in (("E41", "materiaal"), ("R61", "ic"), ("R67", "fullCost"),
                          ("R69", "resultaat"), ("R75", "garantie"), ("R77", "verkoopprijs")):
            verwacht = marge[veld]["totaal"] if isinstance(marge[veld], dict) else marge[veld]
            self.assertAlmostEqual(quot[ref], verwacht, places=4, msg=ref)

    def test_short_trip_en_transfer_cellen(self):
        staat = _voorbeeldstaat()
        _, _, quot, berekening = _bouw(staat)
        marge = berekening["marge"]
        self.assertAlmostEqual(quot["M38"], staat["overig"]["shortTripDagen"])
        self.assertAlmostEqual(quot["P38"], staat["overig"]["shortTripTarief"])
        self.assertAlmostEqual(quot["R38"], marge["shortTripKosten"])
        self.assertAlmostEqual(quot["M39"], staat["overig"]["transferUren"])
        self.assertAlmostEqual(quot["P39"], staat["overig"]["transferTarief"])
        self.assertAlmostEqual(quot["R39"], marge["transferKosten"])
        self.assertAlmostEqual(marge["shortTripKosten"], 2 * 65)
        self.assertAlmostEqual(marge["transferKosten"], 5 * 158)
        self.assertAlmostEqual(quot["R71"], marge["projectPrice"], places=4)

    def test_geen_projectprice_laat_marge_velden_leeg(self):
        staat = rk.nieuwe_staat()
        staat["marge"]["projectPrice"] = None
        _, _, quot, berekening = _bouw(staat)
        self.assertIsNone(berekening["marge"]["verkoopprijs"])
        for ref in ("R71", "R69", "P69", "R73", "R74", "R75", "R77"):
            self.assertIsNone(quot[ref], msg=ref)

    def test_blanco_staat_bouwt_zonder_fouten(self):
        staat = rk.nieuwe_staat()
        data, calc, quot, berekening = _bouw(staat)
        self.assertGreater(len(data), 0)
        self.assertIsNone(calc["B1"])  # lege tekst wordt een echt lege cel, geen ""


class TestBetalingskorting(unittest.TestCase):
    """Nieuw sinds de sjabloonupdate van oktober 2026 (zie CLAUDE.md): een
    derde debiteur-korting-lijst naast omzetbonus/provisie, met een eigen
    Quotation sheet-rij (R74) tussen OMZETBONUS (R73) en GARANTIE (nu R75)."""

    def test_schrijft_kortingklant_en_percentage(self):
        staat = rk.nieuwe_staat()
        staat["instellingen"]["kortingklant"] = "Hoppenbrouwers"
        staat["marge"]["projectPrice"] = 1000
        _, calc, quot, berekening = _bouw(staat)
        self.assertEqual(calc["D442"], "Hoppenbrouwers")
        self.assertAlmostEqual(calc["F442"], 0.02)
        self.assertAlmostEqual(quot["P74"], 0.02)
        self.assertAlmostEqual(quot["R74"], berekening["marge"]["betalingskorting"])
        self.assertAlmostEqual(berekening["marge"]["betalingskorting"], 1000 * 0.02)

    def test_telt_mee_in_de_verkoopprijs(self):
        """Dezelfde optelsom als omzetbonus/garantie (Quotation sheet!R77 =
        (R71+R73+R74+R75)/(1-F445)), niet een korting die van de prijs afgaat
        -- zo staat de formule ook letterlijk in het sjabloon."""
        staat = rk.nieuwe_staat()
        staat["marge"]["projectPrice"] = 1000
        zonder = rk.marge_berekening(staat, GEGEVENS)
        staat["instellingen"]["kortingklant"] = "Hoppenbrouwers"
        met = rk.marge_berekening(staat, GEGEVENS)
        self.assertAlmostEqual(met["verkoopprijs"] - zonder["verkoopprijs"], 20, places=6)

    def test_oud_opgeslagen_project_zonder_kortingklant_blijft_werken(self):
        """Een staat van vóór deze toevoeging mist het veld instellingen.
        kortingklant nog helemaal -- moet gewoon als 'geen korting' rekenen
        i.p.v. een KeyError te geven (zie de .get() in rekenkern/calculatieblad)."""
        staat = rk.nieuwe_staat()
        del staat["instellingen"]["kortingklant"]
        staat["marge"]["projectPrice"] = 1000
        berekening = rk.bereken(staat, GEGEVENS)
        self.assertAlmostEqual(berekening["marge"]["betalingskorting"], 0)
        data, calc, _, _ = _bouw(staat)
        self.assertEqual(calc["D442"], "Geen betalingskorting")


class TestKortingklantRondje(unittest.TestCase):
    def test_bekende_kortingklant_komt_over(self):
        staat = rk.nieuwe_staat()
        staat["instellingen"]["kortingklant"] = "Hoppenbrouwers"
        data = cb.schrijf_calculatieblad(staat, GEGEVENS)
        geimporteerd, waarschuwingen = cb.lees_calculatieblad(data, GEGEVENS)
        self.assertEqual(geimporteerd["instellingen"]["kortingklant"], "Hoppenbrouwers")
        self.assertEqual(waarschuwingen, [])

    def test_onbekende_kortingklant_valt_terug_met_waarschuwing(self):
        staat = rk.nieuwe_staat()
        data = cb.schrijf_calculatieblad(staat, GEGEVENS)
        data = _herschrijf_cel(data, cb.SHEET_CALCULATIE, "D442", "Een Klant Die Niet Bestaat")
        geimporteerd, waarschuwingen = cb.lees_calculatieblad(data, GEGEVENS)
        self.assertEqual(geimporteerd["instellingen"]["kortingklant"], "Geen betalingskorting")
        self.assertTrue(any("betalingskorting" in w for w in waarschuwingen))


# ============================================================================
# lees_calculatieblad(): de omgekeerde richting.
# ============================================================================

def _herschrijf_cel(xlsx_bytes: bytes, sheet_pad: str, ref: str, waarde) -> bytes:
    """Testhulp: overschrijft één cel in een al gebouwde .xlsx (via dezelfde
    SheetSchrijver die de module zelf gebruikt) -- voor het naspelen van een
    bestand met een onherkenbare/handmatig aangepaste waarde, zonder zelf een
    heel werkboek te moeten bouwen."""
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zin:
        inhoud = {n: zin.read(n) for n in zin.namelist()}
    w = cb.SheetSchrijver(inhoud[sheet_pad].decode("utf-8"))
    w.zet(ref, waarde)
    inhoud[sheet_pad] = w.xml.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for naam, data in inhoud.items():
            zout.writestr(naam, data)
    return buf.getvalue()


def _rondje(staat: dict) -> tuple[dict, list[str], dict, dict]:
    """Exporteert staat, leest 'm meteen weer in, en herberekent beide --
    geeft (geimporteerde_staat, waarschuwingen, orig_berekening, imp_berekening)."""
    orig_berekening = rk.bereken(staat, GEGEVENS)
    data = cb.schrijf_calculatieblad(staat, GEGEVENS)
    geimporteerd, waarschuwingen = cb.lees_calculatieblad(data, GEGEVENS)
    imp_berekening = rk.bereken(geimporteerd, GEGEVENS)
    return geimporteerd, waarschuwingen, orig_berekening, imp_berekening


class TestInlezenRondje(unittest.TestCase):
    """Export -> import -> herberekenen moet dezelfde marge/uren teruggeven
    als de oorspronkelijke staat -- dat bewijst dat de omgekeerde celtabel
    klopt voor alles wat wél herleidbaar is (zie de moduledocstring in
    calculatieblad.py voor wat bewust niet herleidbaar is: losse
    installatieregels)."""

    def test_voorbeeldstaat_marge_en_uren_matchen(self):
        staat = _voorbeeldstaat()
        _, waarschuwingen, orig, imp = _rondje(staat)
        for veld in orig["marge"]:
            verwacht, gekregen = orig["marge"][veld], imp["marge"][veld]
            if isinstance(verwacht, dict):
                self.assertAlmostEqual(verwacht["totaal"], gekregen["totaal"], places=2, msg=veld)
            elif verwacht is None:
                self.assertIsNone(gekregen, msg=veld)
            else:
                self.assertAlmostEqual(verwacht, gekregen, places=2, msg=veld)
        for rol in orig["uren"]:
            self.assertAlmostEqual(orig["uren"][rol]["definitief"], imp["uren"][rol]["definitief"],
                                   places=2, msg=rol)
        self.assertIn("totalen per systeemsoort", waarschuwingen[0])

    def test_meta_en_instellingen_komen_over(self):
        staat = _voorbeeldstaat()
        geimporteerd, _, _, _ = _rondje(staat)
        self.assertEqual(geimporteerd["meta"]["qnummer"], "Q.999")
        self.assertEqual(geimporteerd["meta"]["projectnaam"], "Testproject")
        self.assertEqual(geimporteerd["meta"]["klantnaam"], "Test Klant BV")
        self.assertEqual(geimporteerd["instellingen"]["moeilijkheid"], "Moeilijk")
        self.assertEqual(geimporteerd["instellingen"]["reistijd"], 2)
        self.assertEqual(geimporteerd["instellingen"]["provincie"], "Noord-Holland")

    def test_alle_vier_systeemsoorten_als_aparte_installatie(self):
        staat = rk.nieuwe_staat()
        staat["installaties"] = [
            {"id": "a", "systeemsoort": "VRF", "aantalBuitendelen": 1, "aantalBinnendelen": 4},
            {"id": "b", "systeemsoort": "RAC", "aantalBuitendelen": 2, "aantalBinnendelen": 2},
            {"id": "c", "systeemsoort": "PAC", "aantalBuitendelen": 1, "aantalBinnendelen": 1},
            {"id": "d", "systeemsoort": "Overig", "aantalBuitendelen": 1, "aantalBinnendelen": 1},
        ]
        geimporteerd, waarschuwingen, _, _ = _rondje(staat)
        soorten = {i["systeemsoort"]: i for i in geimporteerd["installaties"]}
        self.assertEqual(set(soorten), {"VRF", "RAC", "PAC", "Overig"})
        self.assertEqual(soorten["VRF"]["aantalBuitendelen"], 1)
        self.assertEqual(soorten["VRF"]["aantalBinnendelen"], 4)
        self.assertEqual(soorten["PAC"]["aantalBuitendelen"], 1)
        self.assertEqual(soorten["Overig"]["aantalBuitendelen"], 1)
        # geen merk/montagewijze/model te herleiden -- moet leeg blijven, geen gok
        for i in geimporteerd["installaties"]:
            self.assertEqual(i["merk"], "")
            self.assertEqual(i["typeBinnendeel"], "")
        self.assertTrue(any("totalen per systeemsoort" in w for w in waarschuwingen))

    def test_lege_systeemsoort_wordt_geen_installatie(self):
        staat = rk.nieuwe_staat()
        staat["installaties"] = [{"id": "a", "systeemsoort": "VRF", "aantalBuitendelen": 1, "aantalBinnendelen": 1}]
        geimporteerd, waarschuwingen, _, _ = _rondje(staat)
        self.assertEqual(len(geimporteerd["installaties"]), 1)
        self.assertEqual(geimporteerd["installaties"][0]["systeemsoort"], "VRF")

    def test_geen_installaties_geeft_geen_waarschuwing_erover(self):
        staat = rk.nieuwe_staat()
        _, waarschuwingen, _, _ = _rondje(staat)
        self.assertEqual(waarschuwingen, [])

    def test_hoofd_en_hulpmonteur_override_herkend(self):
        staat = _voorbeeldstaat()
        staat["uren"]["hoofdmonteur"]["override"] = 999
        geimporteerd, _, _, imp = _rondje(staat)
        self.assertEqual(geimporteerd["uren"]["hoofdmonteur"]["override"], 999)
        self.assertEqual(imp["uren"]["hoofdmonteur"]["definitief"], 999)
        # hulpmonteur bleef ongemoeid -- geen override geïmporteerd
        self.assertIsNone(geimporteerd["uren"]["hulpmonteur"]["override"])

    def test_servicemonteur_override_herkend(self):
        staat = _voorbeeldstaat()
        staat["uren"]["servicemonteur"]["override"] = 77
        geimporteerd, _, _, imp = _rondje(staat)
        self.assertEqual(geimporteerd["uren"]["servicemonteur"]["override"], 77)
        self.assertEqual(imp["uren"]["servicemonteur"]["definitief"], 77)

    def test_geen_override_blijft_none_na_rondje(self):
        """Zonder override moet importeren ook geen override VERZINNEN --
        anders zou elke import een vals-overschreven calculatie opleveren."""
        staat = _voorbeeldstaat()
        self.assertIsNone(staat["uren"]["hoofdmonteur"]["override"])
        geimporteerd, _, _, _ = _rondje(staat)
        self.assertIsNone(geimporteerd["uren"]["hoofdmonteur"]["override"])
        self.assertIsNone(geimporteerd["uren"]["hulpmonteur"]["override"])
        self.assertIsNone(geimporteerd["uren"]["servicemonteur"]["override"])

    def test_materiaal_met_eigen_prijs_komt_terug(self):
        staat = _voorbeeldstaat()  # rij 31 krijgt daar een eigen prijs van 450
        geimporteerd, _, _, _ = _rondje(staat)
        regel = next(m for m in geimporteerd["materiaal"] if m["row"] == 31)
        self.assertEqual(regel["prijs"], 450)

    def test_afgeleide_materiaalregel_komt_mee_en_herrekent_hetzelfde(self):
        staat = rk.nieuwe_staat()
        entry84 = next(e for e in GEGEVENS["materiaal_catalogus"] if e["row"] == 84)
        entry85 = next(e for e in GEGEVENS["materiaal_catalogus"] if e["row"] == 85)
        r84 = rk.materiaal_regel_uit_catalogus(entry84, GEGEVENS["yimm"]); r84["aantal"] = 2
        r85 = rk.materiaal_regel_uit_catalogus(entry85, GEGEVENS["yimm"]); r85["aantal"] = 2
        staat["materiaal"] = [r84, r85]
        _, _, orig, imp = _rondje(staat)
        self.assertAlmostEqual(orig["marge"]["materiaal"]["totaal"], imp["marge"]["materiaal"]["totaal"], places=2)

    def test_materiaal_zonder_row_komt_bewust_niet_terug(self):
        """Een via de Panasonic/Daikin-zoekbalk (scherm/calculatie.js, bron
        "panasonic"/"daikin") of als PROJECTBESTELLING-vrije-regel toegevoegd
        materiaalartikel heeft geen 'row' -- _vul_materiaal hierboven slaat
        zo'n regel al over bij het EXPORTEREN (geen Excel-rij om in te
        schrijven), dus is 'm ook bij het weer inlezen nooit terug te vinden.
        Geen bug: dezelfde, al bestaande beperking in beide richtingen, zie
        CLAUDE.md. Een calculatie met ALLEEN zo'n regel levert dus een lege
        materiaallijst op na een rondje export+import."""
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [{
            "id": "m1", "sectie": "APPARATUUR", "bron": "panasonic", "panasonic_id": "RAC-4",
            "artikelcode": "KIT-TZ20-CKE", "omschrijving": "Wandmodel TZ 20", "eenheid": "ST",
            "prijs": 495.9, "aantal": 1, "row": None,
        }]
        geimporteerd, _, _, _ = _rondje(staat)
        self.assertEqual(geimporteerd["materiaal"], [])

    def test_kaal_getal_in_een_tekstkolom_geeft_geen_punt_nul(self):
        """Aangetroffen in een écht ingevuld bestand van Lars (2 oktober
        2026): iemand typte "1" (geen tekst) in de TYPE-kolom (D) van een
        eigen APPARATUUR-regel. tekst() moet dat als "1" teruggeven, niet als
        "1.0" (wat str(1.0) zonder deze opmaak zou doen)."""
        staat = rk.nieuwe_staat()
        data = cb.schrijf_calculatieblad(staat, GEGEVENS)
        data = _herschrijf_cel(data, cb.SHEET_CALCULATIE, "A37", 1)
        data = _herschrijf_cel(data, cb.SHEET_CALCULATIE, "D37", 1)
        geimporteerd, _ = cb.lees_calculatieblad(data, GEGEVENS)
        regel = next(m for m in geimporteerd["materiaal"] if m["row"] == 37)
        self.assertEqual(regel["omschrijving"], "1")

    def test_eigen_uitbestedingsregel_komt_terug(self):
        staat = _voorbeeldstaat()  # heeft al "Eigen extra werk" op een lege rij
        geimporteerd, _, _, _ = _rondje(staat)
        eigen = next((u for u in geimporteerd["uitbesteding"] if u["omschrijving"] == "Eigen extra werk"), None)
        self.assertIsNotNone(eigen)
        self.assertEqual(eigen["prijs"], 123)
        self.assertEqual(eigen["aantal"], 1)

    def test_alle_standaard_uitbesteding_en_equipment_regels_blijven_bestaan(self):
        staat = rk.nieuwe_staat()
        geimporteerd, _, _, _ = _rondje(staat)
        self.assertEqual(len(geimporteerd["uitbesteding"]), len(rk.UITBESTEDING_DEFAULTS))
        self.assertEqual(len(geimporteerd["equipment"]), len(rk.EQUIPMENT_DEFAULTS))
        self.assertEqual({u["omschrijving"] for u in geimporteerd["uitbesteding"]},
                         {d["omschrijving"] for d in rk.UITBESTEDING_DEFAULTS})

    def test_onbekende_prijs_blijft_onbekend_geen_schijnbedrag(self):
        staat = rk.nieuwe_staat()
        staat["uitbesteding"][1]["aantal"] = 1  # "Grote kraan": prijs=None in UITBESTEDING_DEFAULTS
        geimporteerd, _, _, _ = _rondje(staat)
        regel = next(u for u in geimporteerd["uitbesteding"] if u["omschrijving"] == "Grote kraan")
        self.assertEqual(regel["aantal"], 1)
        self.assertIsNone(regel["prijs"])

    def test_overig_en_marge_komen_over(self):
        staat = _voorbeeldstaat()
        geimporteerd, _, _, _ = _rondje(staat)
        self.assertEqual(geimporteerd["overig"]["nachten"], 2)
        self.assertEqual(geimporteerd["overig"]["shortTripDagen"], 2)
        self.assertEqual(geimporteerd["overig"]["shortTripTarief"], 65)
        self.assertEqual(geimporteerd["overig"]["transferUren"], 5)
        self.assertEqual(geimporteerd["overig"]["transferTarief"], 158)
        self.assertEqual(geimporteerd["marge"]["contingencyReserves"], 100)
        self.assertEqual(geimporteerd["marge"]["contingencyOnderhandeling"], 50)
        self.assertEqual(geimporteerd["marge"]["projectPrice"], 15000)

    def test_short_trip_nul_blijft_nul_na_rondje(self):
        """Een kersverse staat (short trip/transfer nog op hun standaardwaarde,
        zie rk.nieuwe_staat()) mag na een exportrondje niet opeens een gokwaarde
        krijgen -- alleen transferTarief heeft een niet-nul standaard
        (DEFAULT_TARIEVEN["projectmanager"], hetzelfde tarief als
        projectmanager), de rest blijft 0."""
        staat = rk.nieuwe_staat()
        geimporteerd, _, _, _ = _rondje(staat)
        self.assertEqual(geimporteerd["overig"]["shortTripDagen"], 0)
        self.assertEqual(geimporteerd["overig"]["shortTripTarief"], 0)
        self.assertEqual(geimporteerd["overig"]["transferUren"], 0)
        self.assertEqual(geimporteerd["overig"]["transferTarief"], rk.DEFAULT_TARIEVEN["projectmanager"])

    def test_geen_projectprice_blijft_none_niet_nul(self):
        staat = rk.nieuwe_staat()
        self.assertIsNone(staat["marge"]["projectPrice"])
        geimporteerd, _, _, _ = _rondje(staat)
        self.assertIsNone(geimporteerd["marge"]["projectPrice"])


class TestInlezenEchteSjabloon(unittest.TestCase):
    """Het échte, originele sjabloonbestand zelf inlezen -- gebruikt op alle
    tekstvelden ECHTE shared strings (t="s") en laat de meeste formules van
    het sjabloon intact (zie sheet5.xml se A343 e.d.), precies zoals een
    met de hand in Excel ingevuld bestand dat ook zou doen. Dit is de
    dichtstbijzijnde benadering van een écht bestand die hier zonder een
    door Lars aangeleverd voorbeeld te krijgen is."""

    @classmethod
    def setUpClass(cls):
        cls.data = cb.SJABLOON.read_bytes()

    def test_leest_zonder_fouten_en_zonder_waarschuwingen(self):
        staat, waarschuwingen = cb.lees_calculatieblad(self.data, GEGEVENS)
        self.assertEqual(waarschuwingen, [])
        self.assertEqual(staat["installaties"], [])
        self.assertEqual(staat["materiaal"], [])

    def test_instellingen_matchen_de_ingebakken_standaardkeuzes(self):
        staat, _ = cb.lees_calculatieblad(self.data, GEGEVENS)
        self.assertEqual(staat["instellingen"]["moeilijkheid"], "Standaard")
        self.assertEqual(staat["instellingen"]["provincie"], "Geen parkeerkosten")
        self.assertEqual(staat["instellingen"]["bonusklant"], "Geen bonusdragende klant")
        self.assertEqual(staat["instellingen"]["kortingklant"], "Geen betalingskorting")
        self.assertEqual(staat["instellingen"]["provisieklant"], "Geen provisie")

    def test_blanco_sjabloon_rekent_door_zonder_fouten(self):
        staat, _ = cb.lees_calculatieblad(self.data, GEGEVENS)
        berekening = rk.bereken(staat, GEGEVENS)
        self.assertIsNone(berekening["marge"]["projectPrice"])
        self.assertIsNone(berekening["marge"]["verkoopprijs"])

    def test_qnummer_voorvoegsel_uit_het_sjabloon_komt_mee(self):
        # B1 heeft in het kale sjabloon alvast "Q." staan (shared string) --
        # bevestigt dat shared-string-tekst uit een écht bestand goed wordt gelezen.
        staat, _ = cb.lees_calculatieblad(self.data, GEGEVENS)
        self.assertEqual(staat["meta"]["qnummer"], "Q.")


class TestInlezenWaarschuwingen(unittest.TestCase):
    """Een onherkende waarde (bijv. een provincie die niet meer in
    data/parkeertarieven.json voorkomt) mag nooit een gok worden of de import
    laten crashen -- terugval op de standaardwaarde, met een waarschuwing."""

    def test_onbekende_provincie_valt_terug_met_waarschuwing(self):
        staat = _voorbeeldstaat()
        data = cb.schrijf_calculatieblad(staat, GEGEVENS)
        data = _herschrijf_cel(data, cb.SHEET_CALCULATIE, "D432", "Een Provincie Die Niet Bestaat")
        geimporteerd, waarschuwingen = cb.lees_calculatieblad(data, GEGEVENS)
        self.assertEqual(geimporteerd["instellingen"]["provincie"], "Geen parkeerkosten")
        self.assertTrue(any("provincie" in w for w in waarschuwingen))

    def test_onbekende_moeilijkheidsgraad_valt_terug_met_waarschuwing(self):
        staat = _voorbeeldstaat()
        data = cb.schrijf_calculatieblad(staat, GEGEVENS)
        data = _herschrijf_cel(data, cb.SHEET_CALCULATIE, "B7", "Extreem Moeilijk")
        geimporteerd, waarschuwingen = cb.lees_calculatieblad(data, GEGEVENS)
        self.assertEqual(geimporteerd["instellingen"]["moeilijkheid"], "Standaard")
        self.assertTrue(any("moeilijkheidsgraad" in w for w in waarschuwingen))

    def test_onbekende_bonusklant_valt_terug_met_waarschuwing(self):
        staat = _voorbeeldstaat()
        data = cb.schrijf_calculatieblad(staat, GEGEVENS)
        data = _herschrijf_cel(data, cb.SHEET_CALCULATIE, "D439", "Een Klant Die Niet Meer Bestaat")
        geimporteerd, waarschuwingen = cb.lees_calculatieblad(data, GEGEVENS)
        self.assertEqual(geimporteerd["instellingen"]["bonusklant"], "Geen bonusdragende klant")
        self.assertTrue(any("bonusklant" in w for w in waarschuwingen))


class TestInlezenFoutafhandeling(unittest.TestCase):
    def test_geen_geldig_zipbestand_geeft_duidelijke_fout(self):
        with self.assertRaises(cb.CalculatiebladFout):
            cb.lees_calculatieblad(b"dit is geen Excel-bestand")

    def test_zip_zonder_workbook_geeft_duidelijke_fout(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("willekeurig.txt", "inhoud")
        with self.assertRaises(cb.CalculatiebladFout):
            cb.lees_calculatieblad(buf.getvalue())

    def test_ontbrekend_tabblad_geeft_duidelijke_fout(self):
        staat = rk.nieuwe_staat()
        data = cb.schrijf_calculatieblad(staat, GEGEVENS)
        with zipfile.ZipFile(io.BytesIO(data)) as zin:
            inhoud = {n: zin.read(n) for n in zin.namelist()}
        wb = inhoud["xl/workbook.xml"].decode("utf-8")
        inhoud["xl/workbook.xml"] = wb.replace('name="Calculatie"', 'name="Iets Anders"').encode("utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zout:
            for naam, data_ in inhoud.items():
                zout.writestr(naam, data_)
        with self.assertRaises(cb.CalculatiebladFout):
            cb.lees_calculatieblad(buf.getvalue())


if __name__ == "__main__":
    unittest.main()
