"""Toetst het ingevulde Excel-calculatieblad (calculatie/calculatieblad.py).

Er is in deze sandbox geen Excel of LibreOffice Calc beschikbaar om het
resultaat mee te openen (zie CLAUDE.md/git-historie) -- deze tests toetsen
daarom zelf, met dezelfde kale XML-aanpak als de module zelf gebruikt, dat
(a) het resultaat een geldig .xlsx-bestand is (welgevormde XML, geen
calcChain.xml meer) en (b) elke cel die geld of uren voorstelt letterlijk de
waarde bevat die rekenkern.bereken() voor diezelfde staat teruggeeft -- nooit
een andere waarde die een Excel-formule daar zelf zou hebben uitgerekend.
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
        entry = next(e for e in GEGEVENS["materiaal_catalogus"] if e["row"] == 270)
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
        for rol, rij in (("projectmanager", 330), ("projectleider", 333), ("werkvoorbereider", 336),
                         ("engineering", 339), ("servicemonteur", 343), ("hoofdmonteur", 356),
                         ("hulpmonteur", 377)):
            definitief = berekening["uren"][rol]["definitief"]
            tarief = staat["uren"][rol]["tarief"]
            self.assertAlmostEqual(calc[f"A{rij}"], definitief, msg=rol)
            self.assertAlmostEqual(calc[f"H{rij}"], definitief * tarief, msg=rol)

    def test_monteur_override_overschrijft_het_blad_ook(self):
        """Een handmatige override (rekenkern se enige weg om af te wijken van
        de auto-formule) moet in het blad ook echt het totaal veranderen --
        dat kan alleen als A356/A377 een letterlijke waarde zijn, geen
        formule die alleen de rijen 357-374 optelt."""
        staat = _voorbeeldstaat()
        staat["uren"]["hoofdmonteur"]["override"] = 5
        _, calc, _, berekening = _bouw(staat)
        self.assertEqual(berekening["uren"]["hoofdmonteur"]["definitief"], 5)
        self.assertEqual(calc["A356"], 5)
        self.assertNotEqual(calc["A356"], calc["A377"])  # hulpmonteur bleef ongemoeid

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
        self.assertEqual(calc["A403"], 1)  # Betonboring
        self.assertEqual(calc["H403"], 200)
        self.assertEqual(calc["A420"], 2)  # Hoogwerker
        self.assertEqual(calc["H420"], 1400)

    def test_eigen_regel_naar_lege_rij(self):
        staat = _voorbeeldstaat()
        _, calc, _, _ = _bouw(staat)
        self.assertEqual(calc["B412"], "Eigen extra werk")
        self.assertEqual(calc["A412"], 1)
        self.assertEqual(calc["F412"], 123)
        self.assertEqual(calc["H412"], 123)

    def test_meer_eigen_regels_dan_lege_rijen_crasht_niet(self):
        staat = rk.nieuwe_staat()
        for i in range(7):
            staat["uitbesteding"].append(
                {"id": f"x{i}", "omschrijving": f"Extra {i}", "eenheid": "POST", "prijs": 10, "aantal": 1, "favoriet": False}
            )
        data, calc, _, berekening = _bouw(staat)
        # de TOTAALCEL komt rechtstreeks uit rekenkern en blijft dus correct,
        # ook als niet elke regel een eigen rij in het blad kreeg.
        self.assertAlmostEqual(calc["H417"], berekening["marge"]["uitbesteding"]["totaal"])

    def test_totalen_matchen_marge(self):
        staat = _voorbeeldstaat()
        _, calc, _, berekening = _bouw(staat)
        marge = berekening["marge"]
        self.assertAlmostEqual(calc["H417"], marge["uitbesteding"]["totaal"])
        self.assertAlmostEqual(calc["H429"], marge["equipment"]["totaal"])
        self.assertAlmostEqual(calc["H433"], marge["parkeerkosten"])
        self.assertAlmostEqual(calc["H434"], marge["overnachtingen"])
        self.assertAlmostEqual(calc["H437"], marge["reiskosten"])


class TestQuotationSheet(unittest.TestCase):
    def test_marge_opbouw_letterlijk(self):
        staat = _voorbeeldstaat()
        _, _, quot, berekening = _bouw(staat)
        marge = berekening["marge"]
        for ref, veld in (("R42", "arbeid"), ("E41", "materiaal"), ("R61", "ic"), ("R67", "fullCost"),
                          ("R69", "resultaat"), ("R74", "garantie"), ("R76", "verkoopprijs")):
            verwacht = marge[veld]["totaal"] if isinstance(marge[veld], dict) else marge[veld]
            self.assertAlmostEqual(quot[ref], verwacht, places=4, msg=ref)
        self.assertAlmostEqual(quot["R71"], marge["projectPrice"], places=4)

    def test_geen_projectprice_laat_marge_velden_leeg(self):
        staat = rk.nieuwe_staat()
        staat["marge"]["projectPrice"] = None
        _, _, quot, berekening = _bouw(staat)
        self.assertIsNone(berekening["marge"]["verkoopprijs"])
        for ref in ("R71", "R69", "P69", "R73", "R74", "R76"):
            self.assertIsNone(quot[ref], msg=ref)

    def test_blanco_staat_bouwt_zonder_fouten(self):
        staat = rk.nieuwe_staat()
        data, calc, quot, berekening = _bouw(staat)
        self.assertGreater(len(data), 0)
        self.assertIsNone(calc["B1"])  # lege tekst wordt een echt lege cel, geen ""


if __name__ == "__main__":
    unittest.main()
