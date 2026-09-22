"""Toetst het uitlezen van het briefpapier voor de voorvertoning.

Het scherm liet eerst een zelfbedachte kop zien, waardoor de voorvertoning niet
leek op de brief die eruit rolde. Deze toetsen bewaken dat wat het scherm te
zien krijgt uit het sjabloon komt en niet verzonnen is.
"""

import unittest
import zipfile
from pathlib import Path

from brieventool.briefpapier import BriefpapierFout, beeld, lees

WORTEL = Path(__file__).resolve().parent.parent
SJABLOON = WORTEL / "sjablonen" / "brief.docx"
BRON = WORTEL / "bronbrieven" / "wand enkelvoud.dotx"


class TestBriefpapier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.papier = lees(SJABLOON)

    def test_paginaformaat_is_a4(self):
        pagina = self.papier["pagina"]
        self.assertAlmostEqual(pagina["breedte"], 210.0, delta=0.5)
        self.assertAlmostEqual(pagina["hoogte"], 297.0, delta=0.5)

    def test_marges_komen_uit_het_sjabloon(self):
        # Nagemeten in de bronbrief: 4 cm boven, 2,8 links, 2,5 rechts, 2 onder.
        pagina = self.papier["pagina"]
        self.assertAlmostEqual(pagina["boven"], 40.0, delta=0.5)
        self.assertAlmostEqual(pagina["links"], 28.0, delta=0.5)
        self.assertAlmostEqual(pagina["rechts"], 25.0, delta=0.5)
        self.assertAlmostEqual(pagina["onder"], 20.0, delta=0.5)

    def test_de_gegevens_rechtsboven_staan_erin(self):
        regels = self.papier["kop"]["regels"]
        self.assertIn("Schilt Bedrijven B.V.", regels)
        self.assertIn("Energieweg 29", regels)
        self.assertTrue(any("KvK" in r for r in regels))
        self.assertTrue(any("IBAN" in r for r in regels))

    def test_het_logo_in_de_kop(self):
        beelden = self.papier["kop"]["beelden"]
        self.assertEqual(len(beelden), 1)
        self.assertTrue(beelden[0]["naam"].endswith(".jpeg"))
        self.assertGreater(beelden[0]["breedte"], 10)
        self.assertGreater(beelden[0]["hoogte"], 1)

    def test_de_voettekst_staat_erin(self):
        tekst = " ".join(self.papier["voet"]["regels"])
        self.assertIn("Metaalunie", tekst)
        self.assertIn("privacyverklaring", tekst)

    def test_de_classificatiemarkering_is_geen_brieftekst(self):
        # "C2-Vertrouwelijk" is een markering van Word en hoort niet in beeld.
        for regel in self.papier["voet"]["regels"] + self.papier["kop"]["regels"]:
            self.assertNotIn("C2-Vertrouwelijk", regel)

    def test_niet_toonbare_beelden_worden_gemeld(self):
        # Een EMF kan een browser niet tonen; stil weglaten zou de indruk wekken
        # dat het ook niet in de brief staat.
        self.assertIn("image3.emf", self.papier["onbekende_beelden"])

    def test_alle_beelden_zijn_ook_echt_op_te_halen(self):
        for deel in ("kop", "voet"):
            for plaatje in self.papier[deel]["beelden"]:
                with self.subTest(plaatje["naam"]):
                    inhoud, soort = beeld(SJABLOON, plaatje["naam"])
                    self.assertTrue(inhoud)
                    self.assertTrue(soort.startswith("image/"))


class TestBeeldOphalen(unittest.TestCase):
    def test_onbekende_naam(self):
        with self.assertRaises(BriefpapierFout):
            beeld(SJABLOON, "bestaatniet.png")

    def test_niet_toonbare_soort(self):
        with self.assertRaises(BriefpapierFout) as gevangen:
            beeld(SJABLOON, "image3.emf")
        self.assertIn("browser", str(gevangen.exception))

    def test_geen_uitbraak_uit_het_sjabloon(self):
        # Een naam met een pad erin mag niet buiten word/media/ komen.
        for poging in ("../../etc/passwd", "../document.xml", "/etc/passwd"):
            with self.subTest(poging), self.assertRaises(BriefpapierFout):
                beeld(SJABLOON, poging)

    def test_ontbrekend_sjabloon(self):
        with self.assertRaises(BriefpapierFout):
            lees(WORTEL / "sjablonen" / "bestaatniet.docx")


class TestGelijkAanDeBronbrief(unittest.TestCase):
    """Het briefpapier van het sjabloon moet dat van de bronbrief zijn."""

    def test_zelfde_kopregels_als_de_bronbrief(self):
        self.assertEqual(lees(SJABLOON)["kop"]["regels"], lees(BRON)["kop"]["regels"])

    def test_zelfde_beelden_als_de_bronbrief(self):
        with zipfile.ZipFile(SJABLOON) as sjabloon, zipfile.ZipFile(BRON) as bron:
            eigen = {n for n in sjabloon.namelist() if n.startswith("word/media/")}
            origineel = {n for n in bron.namelist() if n.startswith("word/media/")}
        self.assertEqual(eigen, origineel)


if __name__ == "__main__":
    unittest.main()
