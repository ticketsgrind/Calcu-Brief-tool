"""Toetst de overdracht van een calculatie naar een briefconcept.

Uitgangspunt van de hele module (zie overdracht.py): nooit gokken en stil
invullen. Elke test hieronder hoort dus bij een van de drie statussen
("direct", "afgeleid", "keuze_nodig") of bij wat er expres NIET wordt
overgenomen.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from brieventool import laad
from brieventool.controle import ontbrekende_gegevens
from brieventool.samenstellen import stel_samen
from calculatie import rekenkern as rk
from overdracht import zet_over

WORTEL = Path(__file__).resolve().parent.parent
GEGEVENS = rk.laad_gegevens()


def status_van(overdracht, pad):
    for item in overdracht:
        if item.pad == pad:
            return item
    return None


class TestDirecteOvername(unittest.TestCase):
    def test_datum_en_qnummer(self):
        staat = rk.nieuwe_staat()
        staat["meta"]["datum"] = "2026-09-01"
        staat["meta"]["qnummer"] = "Q.1080000.6.01"
        offerte, overdracht = zet_over(staat, rk.bereken(staat, GEGEVENS))

        self.assertEqual(offerte["briefdatum"], "2026-09-01")
        self.assertEqual(offerte["projectnummer"], "Q.1080000.6.01")
        self.assertEqual(status_van(overdracht, "briefdatum").status, "direct")

    def test_lege_meta_levert_geen_velden(self):
        staat = rk.nieuwe_staat()
        offerte, _ = zet_over(staat, rk.bereken(staat, GEGEVENS))
        self.assertNotIn("briefdatum", offerte)
        self.assertNotIn("projectnummer", offerte)

    def test_klantnaam_wordt_organisatie_maar_gemarkeerd(self):
        staat = rk.nieuwe_staat()
        staat["meta"]["klantnaam"] = "Voorbeeld Vastgoed B.V."
        offerte, overdracht = zet_over(staat, rk.bereken(staat, GEGEVENS))

        self.assertEqual(offerte["organisatie"], "Voorbeeld Vastgoed B.V.")
        item = status_van(overdracht, "organisatie")
        self.assertEqual(item.status, "afgeleid")


class TestVerkoopprijs(unittest.TestCase):
    def test_prijsregel_komt_uit_de_berekening_zelf(self):
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [{"id": "m1", "sectie": "X", "aantal": 1, "prijs": 1000}]
        staat["marge"]["projectPrice"] = 3000
        berekening = rk.bereken(staat, GEGEVENS)

        offerte, overdracht = zet_over(staat, berekening)

        self.assertEqual(offerte["prijsregels"], [{"bedrag": round(berekening["marge"]["verkoopprijs"], 2)}])
        self.assertEqual(offerte["prijssoort"], "totaalprijs")
        self.assertEqual(status_van(overdracht, "prijsregels[0].bedrag").status, "direct")

    def test_particuliere_klant_krijgt_21_procent_btw_erbij(self):
        # De calculatie rekent altijd exclusief btw; de brief voor een
        # particuliere klant moet het bedrag inclusief btw laten zien.
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [{"id": "m1", "sectie": "X", "aantal": 1, "prijs": 1000}]
        staat["marge"]["projectPrice"] = 3000
        berekening = rk.bereken(staat, GEGEVENS)
        verkoopprijs = berekening["marge"]["verkoopprijs"]

        offerte, overdracht = zet_over(staat, berekening, klanttype="particulier")

        self.assertEqual(offerte["prijsregels"], [{"bedrag": round(verkoopprijs * 1.21, 2)}])
        self.assertEqual(status_van(overdracht, "prijsregels[0].bedrag").status, "direct")

    def test_zakelijke_klant_blijft_exclusief_btw(self):
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [{"id": "m1", "sectie": "X", "aantal": 1, "prijs": 1000}]
        staat["marge"]["projectPrice"] = 3000
        berekening = rk.bereken(staat, GEGEVENS)

        offerte, _ = zet_over(staat, berekening, klanttype="zakelijk")

        self.assertEqual(offerte["prijsregels"], [{"bedrag": round(berekening["marge"]["verkoopprijs"], 2)}])

    def test_onbekend_klanttype_gokt_niet_en_blijft_exclusief(self):
        staat = rk.nieuwe_staat()
        staat["materiaal"] = [{"id": "m1", "sectie": "X", "aantal": 1, "prijs": 1000}]
        staat["marge"]["projectPrice"] = 3000
        berekening = rk.bereken(staat, GEGEVENS)

        offerte, _ = zet_over(staat, berekening, klanttype=None)

        self.assertEqual(offerte["prijsregels"], [{"bedrag": round(berekening["marge"]["verkoopprijs"], 2)}])

    def test_zonder_projectprice_geen_prijsregel(self):
        staat = rk.nieuwe_staat()
        offerte, _ = zet_over(staat, rk.bereken(staat, GEGEVENS))
        self.assertNotIn("prijsregels", offerte)


class TestSysteemsoortVertaling(unittest.TestCase):
    def _installatie(self, **veld):
        staat = rk.nieuwe_staat()
        staat["installaties"] = [dict(id="a", merk="Panasonic", montagewijze="Wandmontage",
                                      typeBinnendeel="KIT-71PU3Z5", **veld)]
        return zet_over(staat, rk.bereken(staat, GEGEVENS))

    def test_vrf_wordt_altijd_vrf(self):
        offerte, overdracht = self._installatie(systeemsoort="VRF", aantalBinnendelen=4, aantalBuitendelen=1)
        self.assertEqual(offerte["installaties"][0]["systeemsoort"], "vrf")
        self.assertEqual(status_van(overdracht, "installaties[0].systeemsoort").status, "afgeleid")

    def test_rac_met_een_binnendeel_wordt_splitsystem(self):
        offerte, overdracht = self._installatie(systeemsoort="RAC", aantalBinnendelen=1, aantalBuitendelen=1)
        regel = offerte["installaties"][0]
        self.assertEqual(regel["systeemsoort"], "splitsystem")
        # samenstellen._aantallen() telt bij een splitsystem alleen aantal_systemen.
        self.assertEqual(regel["aantal_systemen"], 1)
        self.assertEqual(status_van(overdracht, "installaties[0].systeemsoort").status, "afgeleid")

    def test_pac_met_meerdere_binnendelen_wordt_multi_splitsystem(self):
        offerte, _ = self._installatie(systeemsoort="PAC", aantalBinnendelen=3, aantalBuitendelen=1)
        regel = offerte["installaties"][0]
        self.assertEqual(regel["systeemsoort"], "multi-splitsystem")
        self.assertEqual(regel["aantal_binnendelen"], 3)
        self.assertEqual(regel["aantal_buitendelen"], 1)

    def test_rac_zonder_aantal_binnendelen_vraagt_een_keuze(self):
        offerte, overdracht = self._installatie(systeemsoort="RAC", aantalBuitendelen=1)
        self.assertNotIn("systeemsoort", offerte["installaties"][0])
        item = status_van(overdracht, "installaties[0].systeemsoort")
        self.assertEqual(item.status, "keuze_nodig")
        self.assertEqual(item.opties, ["splitsystem", "multi-splitsystem"])

    def test_overig_vraagt_een_keuze_tussen_warmtepomp_en_koelmachine(self):
        offerte, overdracht = self._installatie(systeemsoort="Overig", aantalBinnendelen=1, aantalBuitendelen=1)
        self.assertNotIn("systeemsoort", offerte["installaties"][0])
        item = status_van(overdracht, "installaties[0].systeemsoort")
        self.assertEqual(item.status, "keuze_nodig")
        self.assertEqual(item.opties, ["warmtepomp", "vloeistofkoelmachine"])


class TestVeldenDieCalculatieNietKent(unittest.TestCase):
    """klanttype, adres, aanhef, facturering, etc. bestaan niet in de
    calculatie en horen dus ook niet in de overdracht te verschijnen -- ze
    blijven een gewoon, door controle.py bewaakt formulierveld in stap 2."""

    def test_klanttype_wordt_niet_verzonnen(self):
        staat = rk.nieuwe_staat()
        offerte, _ = zet_over(staat, rk.bereken(staat, GEGEVENS))
        self.assertNotIn("klanttype", offerte)
        self.assertNotIn("achternaam", offerte)
        self.assertNotIn("facturering", offerte)


class TestSamenwerkingMetControle(unittest.TestCase):
    """Een keuze_nodig-systeemsoort mag nooit stil een gat in de brief laten:
    hij moet door de bestaande gatencontrole worden opgepikt."""

    def test_keuze_nodig_systeemsoort_wordt_als_ontbrekend_gezien(self):
        staat = rk.nieuwe_staat()
        staat["installaties"] = [{"id": "a", "systeemsoort": "Overig", "merk": "Daikin",
                                  "typeBinnendeel": "X", "aantalBinnendelen": 1, "aantalBuitendelen": 1}]
        offerte, _ = zet_over(staat, rk.bereken(staat, GEGEVENS))
        self.assertIn("de systeemsoort", ontbrekende_gegevens(offerte))

    def test_multi_splitsystem_vraagt_alsnog_om_het_type_buitendeel(self):
        # De calculatie kent geen "type buitendeel"-veld; dat blijft dus altijd
        # een gat totdat de gebruiker het in stap 2 zelf invult.
        staat = rk.nieuwe_staat()
        staat["installaties"] = [{"id": "a", "systeemsoort": "PAC", "merk": "Daikin",
                                  "typeBinnendeel": "X", "aantalBinnendelen": 2, "aantalBuitendelen": 1}]
        offerte, _ = zet_over(staat, rk.bereken(staat, GEGEVENS))
        self.assertIn("het type buitendeel", ontbrekende_gegevens(offerte))

    def test_volledig_ingevulde_overdracht_componeert_een_brief_zonder_crash(self):
        staat = rk.nieuwe_staat()
        staat["meta"]["datum"] = "2026-09-01"
        staat["meta"]["qnummer"] = "Q.1080000.6.01"
        staat["installaties"] = [{"id": "a", "systeemsoort": "RAC", "merk": "Panasonic",
                                  "montagewijze": "Wandmontage", "typeBinnendeel": "KIT-71PU3Z5",
                                  "aantalBinnendelen": 1, "aantalBuitendelen": 1}]
        staat["materiaal"] = [{"id": "m1", "sectie": "X", "aantal": 1, "prijs": 1000}]
        staat["marge"]["projectPrice"] = 3000
        offerte, _ = zet_over(staat, rk.bereken(staat, GEGEVENS))

        # De rest is wat de brief-stap er nog bij zou vragen (nooit door de
        # calculatie geraden): klant, aanhef, aanleiding en dergelijke.
        offerte.update({
            "klanttype": "particulier", "documentsoort": "offerte",
            "installatietype": "airconditioning", "aanspreekvorm": "de heer",
            "achternaam": "De Wit", "straat_huisnummer": "Energieweg 29",
            "postcode": "4231DJ", "plaats": "Meerkerk",
            "locatieaanduiding": "uw woning", "sa_nummer": "35950",
            "aanleiding": "aanvraag", "datum_aanleiding": "1 september",
            "facturering": "in_een_keer", "betaling": "veertien_dagen",
            "werk_inclusief": [], "werk_exclusief": [],
        })

        self.assertEqual(ontbrekende_gegevens(offerte), [])
        brief = stel_samen(offerte, laad(WORTEL))
        self.assertIn(str(round(rk.bereken(staat, GEGEVENS)["marge"]["verkoopprijs"], 2)).split(".")[0],
                      "".join(brief.regels("prijs")).replace(".", ""))


if __name__ == "__main__":
    unittest.main()
