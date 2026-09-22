import unittest
from datetime import date

from brieventool.opmaak import bedrag, briefdatum, meervoud, postcode, telwoord


class TestBedrag(unittest.TestCase):
    def test_schrijfwijze_van_schilt(self):
        # De vorm komt uit de uitgewerkte brieven: € 7.595,- en niet € 7.595,00.
        self.assertEqual(bedrag(7595), "€ 7.595,-")
        self.assertEqual(bedrag(220), "€ 220,-")
        self.assertEqual(bedrag(1265000), "€ 1.265.000,-")

    def test_met_centen(self):
        self.assertEqual(bedrag(4995, centen=True), "€ 4.995,00")

    def test_centen_in_de_waarde_blijven_staan(self):
        self.assertEqual(bedrag("3900.50"), "€ 3.900,50")

    def test_leeg_blijft_leeg(self):
        # Een niet ingevulde meerprijs mag geen "€ 0,-" worden.
        self.assertEqual(bedrag(None), "")
        self.assertEqual(bedrag(""), "")

    def test_nul_is_wel_een_bedrag(self):
        self.assertEqual(bedrag(0), "€ 0,-")

    def test_al_opgemaakt_bedrag_blijft_gelijk(self):
        self.assertEqual(bedrag("€ 7.595,-"), "€ 7.595,-")

    def test_onleesbaar_bedrag_geeft_duidelijke_fout(self):
        with self.assertRaises(ValueError):
            bedrag("ongeveer vijfduizend")


class TestOverigeOpmaak(unittest.TestCase):
    def test_telwoord(self):
        self.assertEqual(telwoord(1), "één")
        self.assertEqual(telwoord(3), "drie")
        self.assertEqual(telwoord(15), "15")     # boven twaalf blijft het een cijfer

    def test_briefdatum_voluit(self):
        self.assertEqual(briefdatum(date(2026, 8, 26)), "26 augustus 2026")
        self.assertEqual(briefdatum("2026-03-02"), "2 maart 2026")

    def test_postcode(self):
        self.assertEqual(postcode("2984BM"), "2984 BM")
        self.assertEqual(postcode("2984  bm"), "2984 BM")
        self.assertEqual(postcode(""), "")

    def test_meervoud(self):
        self.assertEqual(meervoud(1, "de unit", "de units"), "de unit")
        self.assertEqual(meervoud(3, "de unit", "de units"), "de units")


if __name__ == "__main__":
    unittest.main()
