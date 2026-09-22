"""Toetst de geporte rekenkern tegen dezelfde cijfers als de oorspronkelijke
`tools/test_engine.js` uit de calculatietool — rechtstreeks overgezet, zodat
aantoonbaar is dat de Python-versie dezelfde, tegen Excel geverifieerde,
uitkomsten geeft. De twee scenario's die alleen de Panasonic/Daikin-
productzoekfunctie toetsten (scenario 6 en 7 in het origineel) zijn niet
overgezet: die zoekfunctie blijft in de browser, hier wordt alleen de
rekenkern getoetst.
"""

from __future__ import annotations

import copy
import unittest

from calculatie import rekenkern as rk

GEGEVENS = rk.laad_gegevens()


def nieuwe_staat_met(**wijziging):
    staat = rk.nieuwe_staat()
    staat.update(copy.deepcopy(wijziging))
    return staat


class TestUrenformules(unittest.TestCase):
    """Scenario 1 en 2 uit test_engine.js: RAC- en PAC-installaties."""

    def test_scenario1_rac_installatie(self):
        staat = nieuwe_staat_met(
            installaties=[{"id": "a", "systeemsoort": "RAC", "aantalBuitendelen": 2, "aantalBinnendelen": 4}],
            materiaal=[{"id": "m1", "sectie": "LEIDINGEN/KABELS/SIFON",
                        "leiding_categorie": "hard_2pijps", "aantal": 14}],
        )
        staat["instellingen"]["moeilijkheid"] = "Standaard"
        staat["instellingen"]["reistijd"] = 1

        self.assertAlmostEqual(rk.monteur_werkuren_auto(staat), 19.5, places=6)
        self.assertAlmostEqual(rk.ploegdagen(staat), 2.4375, places=6)
        self.assertAlmostEqual(rk.reisuren_monteur(staat), 3, places=6)
        self.assertAlmostEqual(rk.monteur_voorstel(staat), 23, places=6)

    def test_scenario2_pac_installatie_en_arbeid(self):
        staat = nieuwe_staat_met(
            installaties=[{"id": "a", "systeemsoort": "PAC", "aantalBuitendelen": 2, "aantalBinnendelen": 3}],
            materiaal=[{"id": "m1", "sectie": "LEIDINGEN/KABELS/SIFON",
                        "leiding_categorie": "zacht_2pijps", "aantal": 60}],
        )
        staat["instellingen"]["moeilijkheid"] = "Standaard"
        staat["instellingen"]["reistijd"] = 1.5

        self.assertAlmostEqual(rk.monteur_werkuren_auto(staat), 55, places=6)
        self.assertAlmostEqual(rk.ploegdagen(staat), 6.875, places=6)
        self.assertAlmostEqual(rk.reisuren_monteur(staat), 10.5, places=6)
        self.assertAlmostEqual(rk.monteur_voorstel(staat), 66, places=6)

        uren = rk.rol_uren(staat, "hoofdmonteur")
        self.assertAlmostEqual(uren["definitief"], 66, places=6)

        staat["uren"]["hoofdmonteur"]["tarief"] = 69
        staat["uren"]["hulpmonteur"]["tarief"] = 56
        arbeid = rk.arbeid_totaal(staat)
        self.assertAlmostEqual(arbeid, 66 * 69 + 66 * 56, places=6)

    def test_op_aanvraag_telt_nooit_mee_als_schijnbedrag(self):
        lijst = [
            {"id": "u1", "omschrijving": "Grote kraan", "aantal": 1, "eenheid": "ST", "prijs": None},
            {"id": "u2", "omschrijving": "Kleine kraan", "aantal": 1, "eenheid": "ST", "prijs": 500},
        ]
        resultaat = rk.lijst_totaal(lijst)
        self.assertAlmostEqual(resultaat["totaal"], 500, places=6)
        self.assertEqual(resultaat["onvolledig"], 1)


class TestMargeBerekening(unittest.TestCase):
    """Scenario 3 uit test_engine.js: de volledige marge-keten."""

    def test_scenario3_volledige_keten(self):
        staat = rk.nieuwe_staat()
        staat["installaties"] = []
        staat["materiaal"] = [{"id": "m1", "sectie": "X", "aantal": 1, "prijs": 1000}]
        staat["uitbesteding"] = [{"id": "u1", "omschrijving": "x", "aantal": 1, "eenheid": "ST", "prijs": 100}]
        staat["equipment"] = [{"id": "e1", "omschrijving": "x", "aantal": 1, "eenheid": "ST", "prijs": 50}]
        for rol in ("projectmanager", "projectleider", "werkvoorbereider", "engineering"):
            staat["uren"][rol]["werk"] = 0
            staat["uren"][rol]["reis"] = 0
        staat["uren"]["servicemonteur"]["overig"] = 0
        staat["uren"]["servicemonteur"]["override"] = 0
        staat["uren"]["hoofdmonteur"]["override"] = 0
        staat["uren"]["hulpmonteur"]["override"] = 0
        staat["uren"]["verkoper"]["uren"] = 10
        staat["uren"]["verkoper"]["tarief"] = 100
        staat["instellingen"]["provincie"] = "Geen parkeerkosten"
        staat["overig"]["nachten"] = 0
        staat["marge"]["contingencyReserves"] = 200
        staat["marge"]["contingencyOnderhandeling"] = 0
        staat["marge"]["projectPrice"] = 3000
        staat["instellingen"]["bonusklant"] = "Geen bonusdragende klant"
        staat["instellingen"]["provisieklant"] = "Geen provisie"

        m = rk.marge_berekening(staat, GEGEVENS)
        self.assertAlmostEqual(m["materiaal"]["totaal"], 1000, places=6)
        self.assertAlmostEqual(m["arbeid"], 1000, places=6)
        self.assertAlmostEqual(m["overigeKosten"], 1482, places=6)
        self.assertAlmostEqual(m["ic"], 2482, places=6)
        self.assertAlmostEqual(m["fullCost"], 2697.934, places=3)
        self.assertAlmostEqual(m["resultaat"], 302.066, places=3)
        self.assertAlmostEqual(m["garantie"], 37.5, places=6)
        self.assertAlmostEqual(m["verkoopprijs"], 3037.5, places=6)
        self.assertAlmostEqual(m["resultaatPct"], 0.09944444, delta=0.0001)

    def test_verlies_geeft_negatief_resultaat(self):
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [{"id": "m1", "sectie": "X", "aantal": 1, "prijs": 1000}]
        staat["marge"]["projectPrice"] = 1
        m = rk.marge_berekening(staat, GEGEVENS)
        self.assertLess(m["resultaat"], 0)


class TestAfgeleideAantallen(unittest.TestCase):
    """Scenario 4 uit test_engine.js: automatisch gekoppelde materiaalregels
    (bijv. trillingsdempers die altijd meekomen met een MPC-consoleset)."""

    def test_trillingsdempers_automatisch_aangemaakt(self):
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [{"id": "mpc", "sectie": "BALKEN/VOETEN/MUURSTEUN", "row": 84, "aantal": 3}]
        rk.sync_afgeleide_aantallen(staat, GEGEVENS)
        demper = next((r for r in staat["materiaal"] if r.get("row") == 87), None)
        self.assertIsNotNone(demper)
        self.assertEqual(demper["aantal"], 12)
        self.assertTrue(demper["afgeleid"])

    def test_trillingsdempers_verdwijnen_met_trigger(self):
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [{"id": "mpc", "sectie": "BALKEN/VOETEN/MUURSTEUN", "row": 84, "aantal": 3}]
        rk.sync_afgeleide_aantallen(staat, GEGEVENS)
        staat["materiaal"] = [r for r in staat["materiaal"] if r.get("row") != 84]
        rk.sync_afgeleide_aantallen(staat, GEGEVENS)
        self.assertFalse(any(r.get("row") == 87 for r in staat["materiaal"]))

    def test_twee_bronnen_tellen_samen_op(self):
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [
            {"id": "mpc", "sectie": "BALKEN/VOETEN/MUURSTEUN", "row": 84, "aantal": 1},
            {"id": "rodigas", "sectie": "BALKEN/VOETEN/MUURSTEUN", "row": 85, "aantal": 2},
        ]
        rk.sync_afgeleide_aantallen(staat, GEGEVENS)
        demper = next(r for r in staat["materiaal"] if r.get("row") == 87)
        self.assertEqual(demper["aantal"], 12)


class TestVerdeelboxen(unittest.TestCase):
    """Scenario 5: "Aantal verdeelboxen" volgt de materiaalregel VERDEELBOXEN,
    inclusief de 8u BC-controller-uren die daarvan afhangen."""

    def test_verdeelboxen_zonder_materiaalregel(self):
        staat = rk.nieuwe_staat()
        self.assertEqual(rk.verdeelboxen_aantal(staat), 0)

    def test_verdeelboxen_volgt_materiaalregel(self):
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [{"id": "vb", "sectie": "APPARATUUR", "row": 34,
                                "instellingen_koppeling": "verdeelboxen", "aantal": 3}]
        self.assertEqual(rk.verdeelboxen_aantal(staat), 3)
        self.assertEqual(rk.monteur_werkuren_auto(staat), 24)


class TestRobuustheid(unittest.TestCase):
    """Scenario 8: nooit een negatief aantal/prijs/uren laten meetellen."""

    def test_non_negatief(self):
        self.assertEqual(rk.non_negatief("-5"), 0)
        self.assertEqual(rk.non_negatief("5"), "5")
        self.assertEqual(rk.non_negatief(""), "")
        self.assertEqual(rk.non_negatief("Trillingsdemper"), "Trillingsdemper")
        self.assertEqual(rk.non_negatief("-"), "-")


if __name__ == "__main__":
    unittest.main()
