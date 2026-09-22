"""Toetst het uitlezen van een aangeleverd datablad en de plaatsing ervan."""

import tempfile
import unittest
import zipfile
from pathlib import Path

import yaml

from brieventool import laad, stel_samen
from brieventool.bijlage import BijlageFout, tekst_uit_bestand
from brieventool.samenstellen import SamenstelFout

WORTEL = Path(__file__).resolve().parent.parent
DATABLAD = ("PANASONIC PAC i Standaard Cassette KIT-71PU3Z5\n"
            "\n"
            "Type\t\t: S-6071PU3E\n"
            "Koelvermogen\t: 7,1 (2,6 - 7,7) kW\n"
            "\n"
            "Aansluiten op:\n"
            "Type\t\t: U-71PZ3E5A\n")


def offerte(**extra):
    basis = yaml.safe_load(
        (WORTEL / "voorbeelden" / "particulier-wand-enkelvoud.yaml").read_text(encoding="utf-8"))
    return dict(basis, **extra)


class TestUitlezen(unittest.TestCase):
    def setUp(self):
        self.map = tempfile.TemporaryDirectory()
        self.pad = Path(self.map.name)

    def tearDown(self):
        self.map.cleanup()

    def bestand(self, naam, inhoud=DATABLAD):
        doel = self.pad / naam
        doel.write_text(inhoud, encoding="utf-8")
        return doel

    def test_platte_tekst(self):
        uit = tekst_uit_bestand(self.bestand("datablad.txt"))
        self.assertIn("Type\t\t: S-6071PU3E", uit)

    def test_tabs_blijven_staan(self):
        # De uitlijning van een datablad hangt volledig op tabs.
        self.assertIn("\t", tekst_uit_bestand(self.bestand("datablad.txt")))

    def test_lege_regels_ertussen_blijven_staan(self):
        # Die scheiden de binnenunit van de buitenunit.
        uit = tekst_uit_bestand(self.bestand("datablad.txt"))
        self.assertIn("\n\n", uit)

    def test_lege_regels_aan_de_randen_gaan_weg(self):
        uit = tekst_uit_bestand(self.bestand("d.txt", "\n\n  \nType\t: X\n\n\n"))
        self.assertEqual(uit, "Type\t: X")

    def test_word_bestand(self):
        pad = self.pad / "datablad.docx"
        xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org'
               '/wordprocessingml/2006/main"><w:body>'
               '<w:p><w:r><w:t>Type</w:t><w:tab/><w:t>: S-6071PU3E</w:t></w:r></w:p>'
               '<w:p/>'
               '<w:p><w:r><w:t>Koudemiddel</w:t><w:tab/><w:t>: R32</w:t></w:r></w:p>'
               "</w:body></w:document>")
        with zipfile.ZipFile(pad, "w") as z:
            z.writestr("word/document.xml", xml)
        uit = tekst_uit_bestand(pad)
        self.assertEqual(uit, "Type\t: S-6071PU3E\n\nKoudemiddel\t: R32")

    def test_onbekend_soort_noemt_wat_wel_kan(self):
        with self.assertRaises(BijlageFout) as gevangen:
            tekst_uit_bestand(self.bestand("datablad.xlsx"))
        self.assertIn(".docx", str(gevangen.exception))

    def test_ontbrekend_bestand(self):
        with self.assertRaises(BijlageFout):
            tekst_uit_bestand(self.pad / "bestaatniet.txt")

    def test_leeg_bestand(self):
        with self.assertRaises(BijlageFout):
            tekst_uit_bestand(self.bestand("leeg.txt", "\n \n"))

    def test_kapot_word_bestand(self):
        pad = self.pad / "kapot.docx"
        pad.write_bytes(b"dit is geen zip")
        with self.assertRaises(BijlageFout) as gevangen:
            tekst_uit_bestand(pad)
        self.assertIn("Word", str(gevangen.exception))


class TestSpecificatiesInDeBrief(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bib = laad(WORTEL)

    def regels(self, **extra):
        brief = stel_samen(offerte(**extra), self.bib)
        return brief.secties["technische_specificaties"]

    def test_zie_bijlage_blijft_werken(self):
        regels = self.regels(technische_specificaties="zie_bijlage")
        self.assertEqual([a.tekst for a in regels], ["TECHNISCHE SPECIFICATIES", "Zie bijlage."])
        # De kop staat vet, "Zie bijlage." staat cursief en niet vet -- op
        # verzoek van Lars (17 september 2026), zie analyse/vragen.md.
        self.assertEqual(regels[0].stijl, "kopvet")
        self.assertFalse(regels[0].cursief)
        self.assertNotEqual(regels[1].stijl, "kopvet")
        self.assertTrue(regels[1].cursief)

    def test_ingetypte_tekst(self):
        regels = self.regels(technische_specificaties="uitgeschreven",
                             technische_specificaties_tekst="Type\t: KIT-TZ35CKE")
        self.assertEqual(regels[0].stijl, "kopvet")
        self.assertEqual(regels[1].tekst, "Type\t: KIT-TZ35CKE")

    def test_tekst_uit_een_bestand(self):
        with tempfile.TemporaryDirectory() as tijdelijk:
            pad = Path(tijdelijk) / "blad.txt"
            pad.write_text(DATABLAD, encoding="utf-8")
            regels = self.regels(technische_specificaties="uitgeschreven",
                                 technische_specificaties_bestand=str(pad))
        self.assertIn("Type\t\t: S-6071PU3E", [a.tekst for a in regels])

    def test_lege_regels_uit_het_datablad_blijven_staan(self):
        with tempfile.TemporaryDirectory() as tijdelijk:
            pad = Path(tijdelijk) / "blad.txt"
            pad.write_text(DATABLAD, encoding="utf-8")
            regels = self.regels(technische_specificaties="uitgeschreven",
                                 technische_specificaties_bestand=str(pad))
        self.assertTrue(any(not a.tekst for a in regels), "de scheiding tussen de units is weg")

    def test_geen_witregel_tussen_de_specificatieregels(self):
        # In de brieven staan die regels tegen elkaar aan; alleen na de laatste
        # komt een witregel, zodat de volgende sectie los staat.
        regels = self.regels(technische_specificaties="uitgeschreven",
                             technische_specificaties_tekst="Type\t: A\nKoudemiddel\t: R32")
        letterlijk = [a for a in regels if a.letterlijk]
        self.assertEqual([a.witregel_erna for a in letterlijk], [False, True])

    def test_ingetypte_tekst_wint_van_het_bestand(self):
        with tempfile.TemporaryDirectory() as tijdelijk:
            pad = Path(tijdelijk) / "blad.txt"
            pad.write_text(DATABLAD, encoding="utf-8")
            regels = self.regels(technische_specificaties="uitgeschreven",
                                 technische_specificaties_tekst="Zelf ingetypt",
                                 technische_specificaties_bestand=str(pad))
        self.assertNotIn("S-6071PU3E", " ".join(a.tekst for a in regels))

    def test_uitgeschreven_zonder_inhoud_geeft_duidelijke_fout(self):
        with self.assertRaises(SamenstelFout) as gevangen:
            self.regels(technische_specificaties="uitgeschreven")
        self.assertIn("technische_specificaties_bestand", str(gevangen.exception))

    def test_ontbrekend_bestand_noemt_het_pad(self):
        with self.assertRaises(SamenstelFout) as gevangen:
            self.regels(technische_specificaties="uitgeschreven",
                        technische_specificaties_bestand="weg.docx")
        self.assertIn("weg.docx", str(gevangen.exception))

    def test_maar_een_variant_tegelijk(self):
        for keuze in ("zie_bijlage", "uitgeschreven"):
            with self.subTest(keuze):
                regels = self.regels(technische_specificaties=keuze,
                                     technische_specificaties_tekst="Type\t: A")
                koppen = [a for a in regels if a.stijl == "kopvet"]
                # Bij "zie_bijlage" is alleen de kop "TECHNISCHE SPECIFICATIES"
                # nog kopvet; "Zie bijlage." staat sindsdien cursief, niet vet.
                self.assertEqual(len(koppen), 1)


if __name__ == "__main__":
    unittest.main()
