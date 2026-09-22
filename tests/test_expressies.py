import unittest

from brieventool.expressies import ExpressieFout, evalueer, is_waar


class TestExpressies(unittest.TestCase):
    ctx = {
        "klanttype": "particulier",
        "aantal_binnenunits": 3,
        "organisatie": None,
        "werk_inclusief": ["demontage", "montage"],
        "regel": {"systeemsoort": "splitsystem", "aantal_systemen": 2, "positie": None},
    }

    def evalueer(self, expr):
        return evalueer(expr, self.ctx, {"telwoord": lambda n: {1: "één", 2: "twee"}[n]})

    def test_vergelijking(self):
        self.assertTrue(self.evalueer("klanttype == 'particulier'"))
        self.assertFalse(self.evalueer("klanttype == 'zakelijk'"))
        self.assertTrue(self.evalueer("aantal_binnenunits > 1"))

    def test_logica(self):
        self.assertTrue(self.evalueer("klanttype == 'particulier' and aantal_binnenunits > 1"))
        self.assertFalse(self.evalueer("klanttype == 'zakelijk' and aantal_binnenunits > 1"))
        self.assertTrue(self.evalueer("not organisatie"))

    def test_lidmaatschap(self):
        self.assertTrue(self.evalueer("'demontage' in werk_inclusief"))
        self.assertFalse(self.evalueer("'transport' in werk_inclusief"))

    def test_attribuut_op_woordenboek(self):
        self.assertTrue(self.evalueer("regel.systeemsoort == 'splitsystem'"))
        self.assertTrue(self.evalueer("not regel.positie"))

    def test_onbekende_naam_is_leeg_niet_fout(self):
        # 'organisatie' mag ontbreken bij een particulier; de voorwaarde hoort dan
        # onwaar te zijn en niet de hele brief te laten klappen.
        self.assertFalse(self.evalueer("bestaat_niet"))
        self.assertFalse(self.evalueer("bestaat_niet == 'iets'"))

    def test_vergelijking_met_ontbrekende_waarde_klapt_niet(self):
        self.assertFalse(self.evalueer("bestaat_niet > 1"))

    def test_functieaanroep(self):
        self.assertEqual(self.evalueer("telwoord(regel.aantal_systemen)"), "twee")

    def test_jinja_if_zonder_else(self):
        # teksten.yaml is in Jinja-stijl geschreven; Python eist een else.
        self.assertEqual(self.evalueer("'s' if regel.aantal_systemen > 1"), "s")
        self.assertEqual(self.evalueer("'s' if regel.aantal_systemen > 5"), "")

    def test_lege_voorwaarde_is_altijd_waar(self):
        self.assertTrue(is_waar("", self.ctx))
        self.assertTrue(is_waar(None, self.ctx))

    def test_code_uitvoeren_wordt_geweigerd(self):
        # Het tekstenbestand mag door iedereen aangepast worden; het mag daarmee
        # geen manier worden om code te draaien.
        for gevaarlijk in ("__import__('os').system('ls')",
                           "open('/etc/passwd').read()",
                           "klanttype.__class__"):
            with self.assertRaises(ExpressieFout):
                self.evalueer(gevaarlijk)

    def test_onbekende_functie_wordt_geweigerd(self):
        with self.assertRaises(ExpressieFout):
            self.evalueer("verwijder_alles()")

    def test_onleesbare_expressie_noemt_de_expressie(self):
        with self.assertRaises(ExpressieFout) as gevangen:
            self.evalueer("klanttype ==")
        self.assertIn("klanttype ==", str(gevangen.exception))


if __name__ == "__main__":
    unittest.main()
