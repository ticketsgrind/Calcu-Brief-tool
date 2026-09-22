"""Toetst dat de tool geen brief met gaten erin oplevert.

Een leeg antwoord werd stilzwijgend als niets ingevuld: "bedraagt netto." of
"Ons project no." zonder nummer. Op het scherm valt dat op, in een verstuurde
brief niet meer.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from brieventool.controle import melding, ontbrekende_gegevens

WORTEL = Path(__file__).resolve().parent.parent


def offerte(**wijziging):
    uit = yaml.safe_load((WORTEL / "voorbeelden" / "particulier-wand-enkelvoud.yaml")
                         .read_text(encoding="utf-8"))
    uit["briefdatum"] = str(uit["briefdatum"])
    uit.update(wijziging)
    return uit


class TestOntbrekendeGegevens(unittest.TestCase):
    def test_een_volledige_offerte_mist_niets(self):
        self.assertEqual(ontbrekende_gegevens(offerte()), [])

    def test_elk_gat_wordt_gemeld(self):
        # Elk van deze velden liet een zichtbaar gat in de brief achter.
        for veld, verwacht in [
            ("achternaam", "de achternaam"),
            ("straat_huisnummer", "straat en huisnummer"),
            ("postcode", "de postcode"),
            ("plaats", "de plaats"),
            ("projectnummer", "het projectnummer"),
            ("locatieaanduiding", "de betreft-regel"),
            ("sa_nummer", "het SA-nummer"),
            ("datum_aanleiding", "de datum van de aanleiding"),
        ]:
            with self.subTest(veld):
                self.assertEqual(ontbrekende_gegevens(offerte(**{veld: ""})), [verwacht])

    def test_bedrag_ontbreekt(self):
        self.assertEqual(ontbrekende_gegevens(offerte(prijsregels=[{"bedrag": ""}])),
                         ["het bedrag"])
        self.assertEqual(ontbrekende_gegevens(offerte(prijsregels=[])), ["het bedrag"])

    def test_installatie_zonder_gegevens(self):
        kaal = offerte(installaties=[{"systeemsoort": "splitsystem"}])
        self.assertEqual(ontbrekende_gegevens(kaal),
                         ["het merk", "het type binnendeel"])

    def test_installatie_zonder_systeemsoort(self):
        # Zonder systeemsoort matcht geen enkel blok in "systeemomschrijving";
        # die installatieregel krijgt dan stilzwijgend geen omschrijving.
        zonder = dict(offerte()["installaties"][0])
        zonder.pop("systeemsoort", None)
        self.assertIn("de systeemsoort", ontbrekende_gegevens(offerte(installaties=[zonder])))

    def test_de_ruimte_mag_leeg_blijven(self):
        # Zonder ruimte komt er gewoon geen kopregel boven de installatie; dat
        # is geen gat in de brief.
        leeg = offerte(installaties=[dict(offerte()["installaties"][0], ruimte="")])
        self.assertEqual(ontbrekende_gegevens(leeg), [])

    def test_eigen_kopregel_zonder_ruimte(self):
        eigen = offerte(installaties=[dict(offerte()["installaties"][0], ruimte="",
                                           eigen_kop="Vervanging airconditioning t.b.v. de hal")])
        self.assertEqual(ontbrekende_gegevens(eigen), [])

    def test_een_eigen_opstelling_noemt_de_ruimte_wel(self):
        # "De buitenunit voor <ruimte> wordt geplaatst ..." -- dan is hij nodig.
        regel = dict(offerte()["installaties"][0], ruimte="",
                     opstelling_buitenunit="muursteun")
        self.assertEqual(ontbrekende_gegevens(offerte(installaties=[regel])), ["de ruimte"])

    def test_meerdere_installaties_noemen_het_regelnummer(self):
        twee = offerte()
        twee["installaties"] = [dict(twee["installaties"][0]),
                                dict(twee["installaties"][0], merk="")]
        self.assertEqual(ontbrekende_gegevens(twee), ["het merk van regel 2"])

    def test_buitendeel_alleen_bij_multi_en_vrf(self):
        een = offerte()
        een["installaties"] = [dict(een["installaties"][0], systeemsoort="multi-splitsystem",
                                    type_buitendeel="")]
        self.assertIn("het type buitendeel", ontbrekende_gegevens(een))
        # Een splitsysteem noemt het buitendeel niet apart in de brief.
        self.assertNotIn("het type buitendeel", ontbrekende_gegevens(offerte()))

    def test_adviseur_alleen_bij_een_gesprek(self):
        self.assertIn("de naam van de adviseur",
                      ontbrekende_gegevens(offerte(aanleiding="onderhoud", adviseur="")))
        self.assertNotIn("de naam van de adviseur",
                         ontbrekende_gegevens(offerte(aanleiding="aanvraag", adviseur="")))

    def test_opdrachtbevestiging_vraagt_om_een_opdrachtnummer(self):
        # "Onder dankzegging bevestigen wij hiermede uw schriftelijke opdrachtnr.
        # <nummer> d.d. <datum> jl." -- allebei nodig, anders staat er een gat.
        bevestiging = offerte(documentsoort="opdrachtbevestiging",
                              aanleiding="opdrachtbevestiging", opdrachtnummer="")
        self.assertEqual(ontbrekende_gegevens(bevestiging), ["het opdrachtnummer"])
        bevestiging["opdrachtnummer"] = "12345"
        self.assertEqual(ontbrekende_gegevens(bevestiging), [])

    def test_een_offerte_vraagt_niet_om_een_opdrachtnummer(self):
        self.assertEqual(ontbrekende_gegevens(offerte(opdrachtnummer="")), [])

    def test_de_melding_noemt_alles(self):
        tekst = melding(["het bedrag", "de plaats"])
        self.assertIn("het bedrag en de plaats", tekst)
        self.assertIn("ontbreken", tekst)
        self.assertIn("ontbreekt", melding(["het bedrag"]))


class TestOpdrachtregel(unittest.TestCase):
    """De opdrachtregel maakt geen halve brief, tenzij je erom vraagt."""

    def draai(self, offerte_gegevens, *extra):
        with tempfile.TemporaryDirectory() as tijdelijk:
            pad = Path(tijdelijk) / "offerte.yaml"
            pad.write_text(yaml.safe_dump(offerte_gegevens, allow_unicode=True), encoding="utf-8")
            doel = Path(tijdelijk) / "brief.docx"
            klaar = subprocess.run(
                ["python3", "-m", "brieventool", str(pad), "--docx", str(doel), *extra],
                capture_output=True, text=True, cwd=WORTEL)
            return klaar, doel.exists()

    def test_weigert_een_offerte_zonder_bedrag(self):
        klaar, geschreven = self.draai(offerte(prijsregels=[{"bedrag": ""}]))
        self.assertEqual(klaar.returncode, 1)
        self.assertIn("het bedrag", klaar.stderr)
        self.assertFalse(geschreven)

    def test_met_toch_komt_hij_er_wel(self):
        klaar, geschreven = self.draai(offerte(prijsregels=[{"bedrag": ""}]), "--toch")
        self.assertEqual(klaar.returncode, 0, klaar.stderr)
        self.assertTrue(geschreven)


if __name__ == "__main__":
    unittest.main()
