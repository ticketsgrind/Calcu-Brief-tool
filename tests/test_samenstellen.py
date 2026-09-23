"""Toetst de samenstelling tegen de echte bibliotheek in analyse/teksten.yaml."""

import unittest
from pathlib import Path

import yaml

from brieventool import laad, stel_samen

WORTEL = Path(__file__).resolve().parent.parent


def voorbeeld(naam):
    return yaml.safe_load((WORTEL / "voorbeelden" / naam).read_text(encoding="utf-8"))


class TestBibliotheek(unittest.TestCase):
    def test_bibliotheek_laadt(self):
        bib = laad(WORTEL)
        self.assertGreater(len(bib.blokken), 100)
        self.assertEqual(len({b.id for b in bib.blokken}), len(bib.blokken))

    def test_geen_notities_in_de_brieftekst(self):
        # Aantekeningen horen in het veld `notitie`, niet in de tekst: anders
        # belanden ze in de brief naar de klant.
        for blok in laad(WORTEL).blokken:
            self.assertNotIn("#", blok.tekst, f"blok {blok.id} heeft een # in de tekst")

    def test_geen_letterlijke_tab_ontsnapping(self):
        for blok in laad(WORTEL).blokken:
            self.assertNotIn("\\t", blok.tekst, f"blok {blok.id} heeft een letterlijke \\t")


class TestParticuliereBrief(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brief = stel_samen(voorbeeld("particulier-wand-enkelvoud.yaml"), laad(WORTEL))

    def test_geen_waarschuwingen(self):
        self.assertEqual(self.brief.waarschuwingen, [])

    def test_btw_inclusief_bij_particulier(self):
        prijs = "\n".join(self.brief.regels("prijs"))
        self.assertIn("inclusief 21% btw", prijs)
        self.assertNotIn("exclusief", prijs)

    def test_enkelvoud(self):
        tekst = self.brief.tekst()
        self.assertIn("De binnenunit is ontworpen", tekst)
        self.assertIn("een airconditioninginstallatie", tekst)
        self.assertIn("De buitenunit wordt geplaatst", tekst)

    def test_geen_kredietwaardigheid_bij_particulier(self):
        self.assertNotIn("Kredietwaardigheid", "\n".join(self.brief.regels("voorwaarden")))

    def test_condenspomp_particulier_tarief(self):
        self.assertIn("€ 260,- per stuk", "\n".join(self.brief.regels("prijs")))

    def test_referentie_wordt_voorgesteld(self):
        self.assertEqual(self.brief.context["referentie"], "NV/LH/SA35923")

    def test_referentie_zonder_sa_nummer_zet_geen_sa_alvast(self):
        # Tot 17 september 2026 kwam er ongeacht het veld altijd een "SA" te
        # staan, ook zonder ingevuld nummer -- op verzoek van Lars weg.
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        offerte["sa_nummer"] = ""
        brief = stel_samen(offerte, laad(WORTEL))
        self.assertEqual(brief.context["referentie"], "NV/LH")
        self.assertNotIn("SA", brief.context["referentie"])

    def test_bedrag_in_nederlandse_notatie(self):
        self.assertIn("€ 3.900,- netto", "\n".join(self.brief.regels("prijs")))

    def test_geen_openstaande_plaatshouders(self):
        self.assertNotIn("{{", self.brief.tekst())


class TestZakelijkeBrief(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brief = stel_samen(voorbeeld("zakelijk-cassette-meervoud.yaml"), laad(WORTEL))

    def test_geen_waarschuwingen(self):
        self.assertEqual(self.brief.waarschuwingen, [])

    def test_btw_exclusief_bij_zakelijk(self):
        self.assertIn("exclusief 21% btw", "\n".join(self.brief.regels("prijs")))

    def test_meervoud(self):
        tekst = self.brief.tekst()
        self.assertIn("De binnenunits zijn", tekst)
        self.assertIn("airconditioninginstallaties", tekst)
        self.assertIn("De buitenunits worden geplaatst", tekst)

    def test_kredietwaardigheid_bij_zakelijk(self):
        self.assertIn("Kredietwaardigheid", "\n".join(self.brief.regels("voorwaarden")))

    def test_condenspomp_zakelijk_tarief(self):
        self.assertIn("€ 220,- per stuk", "\n".join(self.brief.regels("prijs")))

    def test_installatieregels_staan_bij_hun_ruimte(self):
        # Kopregel en installatieregel horen te alterneren, niet eerst alle
        # kopregels en daarna alle installatieregels.
        spec = self.brief.regels("specificatie")
        self.assertEqual(len(spec), 4)
        self.assertTrue(spec[0].startswith("T.b.v."))
        self.assertTrue(spec[1].startswith("Het leveren en monteren"))
        self.assertTrue(spec[2].startswith("T.b.v."))
        self.assertTrue(spec[3].startswith("Het leveren en monteren"))

    def test_telwoord_in_de_specificatie(self):
        self.assertIn("twee luchtgekoelde splitsystem inverterunits", self.brief.regels("specificatie")[1])
        self.assertIn("één luchtgekoelde splitsystem inverterunit ", self.brief.regels("specificatie")[3])

    def test_organisatie_boven_het_adres(self):
        regels = self.brief.regels("geadresseerde")
        self.assertEqual(regels[0], "Voorbeeld Vastgoed B.V.")
        self.assertTrue(regels[1].startswith("T.a.v."), regels[1])

    def test_geen_openstaande_plaatshouders(self):
        self.assertNotIn("{{", self.brief.tekst())


class TestOpmaakVanAlineas(unittest.TestCase):
    """De opmaak is nagemeten aan de bronbrieven; zie analyse/skelet.md."""

    @classmethod
    def setUpClass(cls):
        cls.brief = stel_samen(voorbeeld("particulier-wand-enkelvoud.yaml"), laad(WORTEL))

    def test_opsommingsregels_staan_tegen_elkaar_aan(self):
        # In de bronbrieven staat er geen witregel tussen twee opsommingsregels,
        # wel na de laatste. Zonder dat onderscheid staat de brief opgepropt.
        regels = self.brief.secties["prijs"]
        opsommingen = [a for a in regels if a.stijl == "opsomming"]
        self.assertGreater(len(opsommingen), 2)
        for alinea in opsommingen[:-1]:
            self.assertFalse(alinea.witregel_erna, alinea.tekst)
        self.assertTrue(opsommingen[-1].witregel_erna)

    def test_de_werkzaamhedenlijst_staat_als_een_blok(self):
        """Opsommingsregels tegen elkaar aan; alleen na een kop een witregel.

        Zowel de kop van "inclusief" als die van "exclusief" krijgt een lege
        regel eronder; tussen de twee koppen (het laatste "inclusief"-streepje
        en de kop "Niet tot onze werkzaamheden behoren:") komt er geen. Pas na
        de allerlaatste regel van "exclusief" komt er weer een. Op verzoek van
        Lars (17 september 2026); wijkt af van de bronbrieven, die hier
        nergens een lege regel zetten.
        """
        inclusief = self.brief.secties["werkzaamheden_inclusief"]
        exclusief = self.brief.secties["werkzaamheden_exclusief"]
        self.assertTrue(inclusief[0].witregel_erna, inclusief[0].tekst)
        self.assertTrue(all(not a.witregel_erna for a in inclusief[1:]),
                        [a.tekst for a in inclusief[1:] if a.witregel_erna])
        self.assertTrue(exclusief[0].witregel_erna, exclusief[0].tekst)
        self.assertTrue(all(not a.witregel_erna for a in exclusief[1:-1]))
        self.assertTrue(exclusief[-1].witregel_erna)

    def test_de_twee_punten_van_de_aansprakelijkheid_staan_los(self):
        # Anders dan de andere opsommingen: in de bronbrieven staat hier wel
        # een lege regel tussen.
        regels = self.brief.secties["aansprakelijkheid"]
        opsommingen = [a for a in regels if a.stijl == "opsomming"]
        self.assertEqual(len(opsommingen), 2)
        self.assertTrue(all(a.witregel_erna for a in opsommingen))

    def test_de_garantie_staat_boven_de_aansprakelijkheid(self):
        # Zoals in alle sjablonen: Algemene voorwaarden, Garantietermijn,
        # Aansprakelijkheid.
        secties = list(self.brief.secties)
        self.assertLess(secties.index("garantie"), secties.index("aansprakelijkheid"))
        self.assertLess(secties.index("voorwaarden"), secties.index("garantie"))

    def test_witregel_na_elke_gewone_alinea(self):
        prijs = [a for a in self.brief.secties["prijs"] if a.stijl == "tekst"]
        for alinea in prijs:
            self.assertTrue(alinea.witregel_erna, alinea.tekst)

    def test_kop_gevolgd_door_witregel(self):
        # Behalve de koppen van de werkzaamhedenlijst: die staan in de
        # bronbrieven direct boven hun opsomming.
        koppen = [a for a in self.brief.alle_alineas
                  if a.stijl == "kop" and not a.tekst.startswith(
                      ("De installatie is aangeboden", "Niet tot onze"))]
        self.assertGreater(len(koppen), 3)
        for kop in koppen:
            self.assertTrue(kop.witregel_erna, kop.tekst)

    def test_uitgelijnde_vervolgregel_hoort_bij_de_regel_erboven(self):
        # De factureringstermijnen zijn met tabs uitgelijnd; tussen een regel en
        # zijn vervolgregel hoort geen witregel.
        regels = self.brief.secties["facturering"]
        vervolg = [n for n, a in enumerate(regels) if a.uitgelijnd]
        self.assertTrue(vervolg, "geen uitgelijnde vervolgregels gevonden")
        for nummer in vervolg:
            self.assertFalse(regels[nummer - 1].witregel_erna)

    def test_streepje_in_een_uitgelijnde_regel_is_geen_opsomming(self):
        # "\t\t- laatste termijn" begint na strippen met "- ", maar is een
        # uitgelijnde vervolgregel en geen opsommingsregel.
        for alinea in self.brief.secties["facturering"]:
            if alinea.uitgelijnd:
                self.assertEqual(alinea.stijl, "tekst")
                self.assertIn("- laatste termijn", alinea.tekst)
                self.assertTrue(alinea.tekst.startswith("\t"))

    def test_streepje_aan_het_begin_wordt_wel_een_opsomming(self):
        # De uitgangspunten bij de prijsvorming staan met "- " in teksten.yaml.
        uitgangspunten = [a for a in self.brief.secties["prijs"]
                          if "goed bereikbaar" in a.tekst]
        self.assertEqual(len(uitgangspunten), 1)
        self.assertEqual(uitgangspunten[0].stijl, "opsomming")
        self.assertFalse(uitgangspunten[0].tekst.startswith("-"))


class TestAdresblok(unittest.TestCase):
    """Nagemeten in de uitgewerkte brieven."""

    def test_zonder_organisatie_geen_tav(self):
        # "De heer K. ten Broek", niet "T.a.v. de heer ...".
        brief = stel_samen(voorbeeld("particulier-wand-enkelvoud.yaml"), laad(WORTEL))
        eerste = brief.regels("geadresseerde")[0]
        self.assertFalse(eerste.startswith("T.a.v."), eerste)
        self.assertTrue(eerste.startswith("De heer"), eerste)

    def test_met_organisatie_wel_tav(self):
        brief = stel_samen(voorbeeld("zakelijk-cassette-meervoud.yaml"), laad(WORTEL))
        self.assertTrue(brief.regels("geadresseerde")[1].startswith("T.a.v."))

    def test_particulier_met_blijven_staan_organisatie_geen_tav(self):
        # T.a.v. is voor bedrijven. Zet iemand een offerte om van zakelijk naar
        # particulier, dan blijft het organisatieveld in de tool op de
        # achtergrond gevuld staan (het veld verdwijnt alleen uit beeld) --
        # zonder de klanttype-eis in de voorwaarde lekte die oude bedrijfsnaam
        # dan alsnog een T.a.v.-regel in de brief. Op verzoek van Lars
        # (17 september 2026).
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        offerte["organisatie"] = "Oud Bedrijf B.V."
        brief = stel_samen(offerte, laad(WORTEL))
        eerste = brief.regels("geadresseerde")[0]
        self.assertFalse(eerste.startswith("T.a.v."), eerste)
        self.assertTrue(eerste.startswith("De heer"), eerste)

    def test_maar_een_van_de_twee_adresregels(self):
        for naam in ("particulier-wand-enkelvoud.yaml", "zakelijk-cassette-meervoud.yaml"):
            with self.subTest(naam):
                regels = stel_samen(voorbeeld(naam), laad(WORTEL)).regels("geadresseerde")
                self.assertEqual(sum(1 for r in regels if "heer" in r), 1, regels)

    def test_tussenvoegsel_krijgt_hoofdletter_in_de_aanhef(self):
        # "De heer J. ten Broek" in het adres, "Geachte heer Ten Broek," in de
        # aanhef. Zonder voorletters: zo staat het in alle bronbrieven.
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        offerte["achternaam"] = "ten Broek"
        brief = stel_samen(offerte, laad(WORTEL))
        self.assertEqual(brief.regels("geadresseerde")[0], "De heer J. ten Broek")
        self.assertEqual(brief.regels("aanhef")[0], "Geachte heer Ten Broek,")

    def test_geen_voorletters_in_de_aanhef(self):
        # Bevestigd door Lars op 28 augustus 2026: de aanhef noemt alleen de
        # achternaam, zoals in de bronbrieven.
        brief = stel_samen(voorbeeld("particulier-wand-enkelvoud.yaml"), laad(WORTEL))
        self.assertEqual(brief.regels("aanhef")[0], "Geachte heer Jansen,")

    def test_emailadres_onderaan_indien_bekend(self):
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        offerte["email_klant"] = "voorbeeld@example.nl"
        regels = stel_samen(offerte, laad(WORTEL)).regels("geadresseerde")
        self.assertEqual(regels[-1], "voorbeeld@example.nl")

    def test_geen_lege_regel_zonder_emailadres(self):
        regels = stel_samen(voorbeeld("particulier-wand-enkelvoud.yaml"),
                            laad(WORTEL)).regels("geadresseerde")
        self.assertTrue(all(r.strip() for r in regels))


class TestVettePrijs(unittest.TestCase):
    """In de bronbrieven staat het bedrag vet en de aanloopzin niet."""

    @classmethod
    def setUpClass(cls):
        cls.brief = stel_samen(voorbeeld("zakelijk-cassette-meervoud.yaml"), laad(WORTEL))

    def prijsregels(self):
        return [a for a in self.brief.secties["prijs"] if a.stijl == "prijs"]

    def test_bedrag_staat_apart_van_de_aanloopzin(self):
        regels = self.prijsregels()
        self.assertTrue(regels, "geen prijsregels gevonden")
        for alinea in regels:
            self.assertTrue(alinea.nadruk.startswith("€"), alinea.nadruk)
            self.assertTrue(alinea.nadruk.rstrip().endswith("netto."), alinea.nadruk)
            self.assertNotIn("€", alinea.tekst)

    def test_totaalprijs_en_meerprijzen_zijn_prijsregels(self):
        teksten = [a.tekst for a in self.prijsregels()]
        self.assertTrue(any("De totaalprijs" in t for t in teksten))
        self.assertTrue(any("De meerprijs voor het coaten" in t for t in teksten))

    def test_condenswaterpomp_is_geen_prijsregel(self):
        # Die regel eindigt op "per stuk" en staat in de bronbrieven niet vet.
        for alinea in self.brief.secties["prijs"]:
            if "condenswater" in alinea.tekst:
                self.assertEqual(alinea.stijl, "tekst")
                self.assertEqual(alinea.nadruk, "")
                return
        self.fail("de condenswaterpompregel is niet gevonden")

    def test_btw_regel_is_geen_prijsregel(self):
        for alinea in self.brief.secties["prijs"]:
            if "btw" in alinea.tekst:
                self.assertEqual(alinea.stijl, "tekst")

    def test_regel_zonder_bedrag_blijft_heel(self):
        from brieventool.samenstellen import _splits_bedrag
        self.assertEqual(_splits_bedrag("Geen bedrag hier."), ("Geen bedrag hier.", ""))


class TestOpstellingBuitenunit(unittest.TestCase):
    """De opstelling kan per brief of per installatie; zie vragen.md vraag 24."""

    @classmethod
    def setUpClass(cls):
        cls.bib = laad(WORTEL)
        cls.basis = voorbeeld("particulier-wand-enkelvoud.yaml")

    def regels(self, installaties=None):
        offerte = dict(self.basis)
        if installaties is not None:
            offerte["installaties"] = installaties
        return stel_samen(offerte, self.bib).regels("buitenunit")

    def twee_installaties(self, **extra_tweede):
        eerste = dict(self.basis["installaties"][0], ruimte="de keuken", **extra_tweede)
        tweede = dict(self.basis["installaties"][0],
                      ruimte="de slaapkamer op de begane grond", **extra_tweede)
        return [eerste, tweede]

    def test_zonder_opstelling_per_installatie_verandert_er_niets(self):
        regels = self.regels()
        self.assertTrue(any("De buitenunit wordt geplaatst op steunen" in r for r in regels))
        self.assertFalse(any(" voor " in r for r in regels))

    def test_opstelling_per_installatie_noemt_de_ruimte(self):
        regels = self.regels([
            dict(self.basis["installaties"][0], ruimte="de keuken",
                 opstelling_buitenunit="muursteun"),
            dict(self.basis["installaties"][0], ruimte="de slaapkamer op de begane grond",
                 opstelling_buitenunit="grond"),
        ])
        self.assertIn("De buitenunit voor de keuken wordt geplaatst op steunen met "
                      "trillingsdempers tegen de buitengevel.", regels)
        self.assertIn("De buitenunit voor de slaapkamer op de begane grond wordt geplaatst "
                      "op geluiddempende rubberen opstelbalken op de grond.", regels)

    def test_de_briefbrede_regel_vervalt_dan(self):
        regels = self.regels([
            dict(self.basis["installaties"][0], ruimte="de keuken",
                 opstelling_buitenunit="muursteun"),
        ])
        zonder_ruimte = [r for r in regels if r.startswith("De buitenunit wordt geplaatst")]
        self.assertEqual(zonder_ruimte, [], "de keuze voor de hele brief staat er nog bij")

    def test_de_vaste_alineas_blijven_eenmalig(self):
        regels = self.regels([
            dict(self.basis["installaties"][0], ruimte="de keuken",
                 opstelling_buitenunit="muursteun"),
            dict(self.basis["installaties"][0], ruimte="de slaapkamer",
                 opstelling_buitenunit="grond"),
        ])
        geruisarm = [r for r in regels if "geruisarm" in r]
        self.assertEqual(len(geruisarm), 1, geruisarm)


class TestKeuzegroepen(unittest.TestCase):
    """Binnen een keuzegroep hoort precies één blok in de brief te komen."""

    def test_betreft_is_altijd_precies_een_regel(self):
        bib = laad(WORTEL)
        for naam in ("particulier-wand-enkelvoud.yaml", "zakelijk-cassette-meervoud.yaml"):
            with self.subTest(naam):
                self.assertEqual(len(stel_samen(voorbeeld(naam), bib).regels("betreft")), 1)

    def test_eerste_woord_volgt_het_installatietype(self):
        offerte = voorbeeld("zakelijk-cassette-meervoud.yaml")
        offerte["installatietype"] = "koelmachine"
        betreft = stel_samen(offerte, laad(WORTEL)).regels("betreft")
        self.assertEqual(len(betreft), 1)
        self.assertIn("Koelmachine t.b.v.", betreft[0])

    def test_aanleiding_is_altijd_precies_een_alinea(self):
        bib = laad(WORTEL)
        for naam in ("particulier-wand-enkelvoud.yaml", "zakelijk-cassette-meervoud.yaml"):
            with self.subTest(naam):
                self.assertEqual(len(stel_samen(voorbeeld(naam), bib).regels("aanleiding")), 1)


class TestBriefkop(unittest.TestCase):
    """In de briefkop zit de witruimte tussen de secties, niet tussen de regels.

    Nagemeten in het Word-bestand dat de tool zelf maakt: het adresblok staat
    aaneengesloten, na "Meerkerk <datum>" komt een lege regel, en project no. en
    Ref. staan daar weer tegen elkaar aan. De voorvertoning tekent die
    witregels, dus als dit verschuift loopt het scherm uit de pas met Word.
    """

    def setUp(self):
        self.brief = stel_samen(voorbeeld("particulier-wand-enkelvoud.yaml"), laad(WORTEL))

    def test_adresblok_staat_aaneengesloten(self):
        adres = self.brief.secties["geadresseerde"]
        self.assertGreater(len(adres), 2)
        self.assertTrue(all(not a.witregel_erna for a in adres))

    def test_kenmerken_alleen_na_de_eerste_regel_een_witregel(self):
        kenmerken = self.brief.secties["kenmerken"]
        self.assertEqual([a.witregel_erna for a in kenmerken],
                         [True] + [False] * (len(kenmerken) - 1))

    def test_betreft_en_aanhef_laten_de_witruimte_aan_het_sjabloon(self):
        for sectie in ("betreft", "aanhef"):
            with self.subTest(sectie):
                self.assertTrue(all(not a.witregel_erna for a in self.brief.secties[sectie]))


class TestAantalUnits(unittest.TestCase):
    """Het enkelvoud/meervoud in de brief volgt het werkelijke aantal units.

    Een splitsysteem is een binnendeel op een buitendeel; een multi-split of VRF
    heeft er meer. Een blijven staan `aantal_binnendelen` van een eerder gekozen
    multi-split mag bij een splitsysteem niet meetellen -- dat gaf "De
    binnenunits zijn" bij een enkele unit.
    """

    def tel(self, *installaties):
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        kaal = dict(offerte["installaties"][0])
        offerte["installaties"] = [dict(kaal, **regel) for regel in installaties]
        brief = stel_samen(offerte, laad(WORTEL))
        return brief.context["aantal_binnenunits"], brief.context["aantal_buitenunits"]

    def test_een_splitsysteem(self):
        self.assertEqual(self.tel({"systeemsoort": "splitsystem"}), (1, 1))

    def test_blijven_staan_aantal_bij_een_splitsysteem_telt_niet_mee(self):
        self.assertEqual(self.tel({"systeemsoort": "splitsystem", "aantal_binnendelen": 5}), (1, 1))

    def test_twee_splitsystemen(self):
        self.assertEqual(self.tel({"systeemsoort": "splitsystem"},
                                  {"systeemsoort": "splitsystem"}), (2, 2))

    def test_multisplit_telt_de_binnendelen(self):
        self.assertEqual(self.tel({"systeemsoort": "multi-splitsystem",
                                   "aantal_binnendelen": 5, "aantal_buitendelen": 1}), (5, 1))

    def test_vrf_met_twee_buitendelen(self):
        self.assertEqual(self.tel({"systeemsoort": "vrf",
                                   "aantal_binnendelen": 8, "aantal_buitendelen": 2}), (8, 2))

    def test_meerdere_systemen_op_een_regel(self):
        self.assertEqual(self.tel({"systeemsoort": "splitsystem", "aantal_systemen": 3}), (3, 3))

    def test_de_zinnen_volgen_de_telling(self):
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        offerte["installaties"] = [dict(offerte["installaties"][0],
                                        systeemsoort="vrf", aantal_binnendelen=8,
                                        aantal_buitendelen=2, type_buitendeel="PUMY")]
        regels = stel_samen(offerte, laad(WORTEL)).regels("buitenunit")
        self.assertTrue(any(r.startswith("De buitenunits worden geplaatst") for r in regels), regels)


class TestOpdrachtbevestiging(unittest.TestCase):
    """Een opdrachtbevestiging begint met de bevestiging van de opdracht."""

    def aanleiding(self, **wijziging):
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        offerte.update(wijziging)
        return stel_samen(offerte, laad(WORTEL)).regels("aanleiding")

    def test_de_bevestigingszin_komt_in_de_brief(self):
        regels = self.aanleiding(documentsoort="opdrachtbevestiging",
                                 aanleiding="opdrachtbevestiging",
                                 opdrachtnummer="123456", datum_aanleiding="3 maart")
        self.assertEqual(len(regels), 1)
        self.assertIn("uw schriftelijke opdrachtnr. 123456 d.d. 3 maart jl.", regels[0])

    def test_een_andere_aanleiding_wint_niet_meer(self):
        # De zin hing eerder aan documentsoort en verloor het binnen de
        # keuzegroep altijd van de aanleiding erboven.
        regels = self.aanleiding(documentsoort="opdrachtbevestiging",
                                 aanleiding="opdrachtbevestiging", opdrachtnummer="123456")
        self.assertTrue(regels[0].startswith("Onder dankzegging"), regels)


class TestFactureringEnBetaling(unittest.TestCase):
    """Precies een factureringsafspraak en precies een betalingsafspraak.

    Het particuliere blok ging eerder op klanttype af in plaats van op de
    gekozen termijn; koos je daarnaast een factureringstermijn, dan stond
    "Facturering:" twee keer in de brief.
    """

    def regels(self, **wijziging):
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        offerte.update(wijziging)
        brief = stel_samen(offerte, laad(WORTEL))
        return [a.tekst for sectie in ("facturering", "betaling")
                for a in brief.secties[sectie] if a.tekst.strip()]

    def test_een_facturering_en_een_betaling(self):
        for facturering, betaling in [("vijftig_vijftig", "termijnen_particulier"),
                                      ("dertig_zeventig", "dertig_dagen"),
                                      ("overleg", "aflevering"),
                                      ("vijf_termijnen", "dertig_dagen")]:
            with self.subTest(facturering=facturering, betaling=betaling):
                regels = self.regels(facturering=facturering, betaling=betaling)
                self.assertEqual(sum(1 for r in regels if r.startswith("Facturering:")), 1, regels)
                self.assertEqual(sum(1 for r in regels if r.startswith("Betaling:")), 1, regels)

    def test_de_particuliere_termijnen_zijn_gewone_keuzes(self):
        # Ook een zakelijke klant kan ze kiezen; het hangt niet meer aan klanttype.
        regels = self.regels(klanttype="zakelijk", organisatie="Voorbeeld B.V.",
                             facturering="vijftig_vijftig", betaling="termijnen_particulier")
        self.assertTrue(any("50% voorafgaande uitvoering" in r for r in regels))
        self.assertEqual(sum(1 for r in regels if r.startswith("Facturering:")), 1)


class TestOndertekening(unittest.TestCase):
    """De ondertekening staat zoals in alle sjablonen: naam en functie tegen
    elkaar aan, bedrijfsnaam en MEERKERK tegen elkaar aan, en twee lege regels
    ertussen als ruimte voor de handtekening."""

    def afsluiting(self, ondertekenaar):
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        offerte["ondertekenaar"] = ondertekenaar
        alineas = stel_samen(offerte, laad(WORTEL)).secties["afsluiting"]
        eerste = next(n for n, a in enumerate(alineas)
                      if a.tekst.startswith("Vertrouwende"))
        return alineas[eerste:]

    def test_witruimte_staat_waar_de_sjablonen_hem_zetten(self):
        for ondertekenaar, naam, functie in [
            ("nick_vervoorn", "Nick Vervoorn", "Technisch Commercieel Adviseur"),
            ("robert_hartman", "Robert Hartman", "Business Unit General Manager"),
        ]:
            with self.subTest(ondertekenaar):
                regels = [a.tekst for a in self.afsluiting(ondertekenaar)]
                self.assertEqual(regels[1:], [
                    "", "Business Unit Schilt Airconditioning", "MEERKERK",
                    "", "", naam, functie])

    def test_geen_extra_witregel_tussen_die_regels(self):
        # De witregels zitten in de tekst zelf; de motor mag er geen bij zetten.
        alineas = self.afsluiting("nick_vervoorn")
        for alinea in alineas[:-1]:
            self.assertFalse(alinea.witregel_erna, alinea.tekst)
        self.assertTrue(alineas[-1].witregel_erna)


class TestWaarschuwingen(unittest.TestCase):
    def test_verkeerde_keuze_geeft_waarschuwing(self):
        offerte = voorbeeld("zakelijk-cassette-meervoud.yaml")
        # Particuliere factureringsregel op een zakelijke offerte.
        offerte["gekozen_blokken"] = ["facturering_vijftig_vijftig"]
        brief = stel_samen(offerte, laad(WORTEL))
        self.assertTrue(any("facturering_vijftig_vijftig" in w for w in brief.waarschuwingen))

    def test_onbekende_ondertekenaar_geeft_duidelijke_fout(self):
        from brieventool.samenstellen import SamenstelFout
        offerte = voorbeeld("particulier-wand-enkelvoud.yaml")
        offerte["ondertekenaar"] = "piet_pietersen"
        with self.assertRaises(SamenstelFout) as gevangen:
            stel_samen(offerte, laad(WORTEL))
        self.assertIn("piet_pietersen", str(gevangen.exception))


if __name__ == "__main__":
    unittest.main()
