"""Dubbelklikbare opstarter voor Windows zonder zwart consolevenster.

Windows koppelt .pyw-bestanden standaard aan pythonw.exe (de Python-voor-
Windows-installer regelt dat), dat script draait zonder consolevenster --
anders dan start.bat. Voor foutmeldingen (ontbrekende pakketten, een server
die niet start) is er dus geen console om iets op te printen; die gaan
daarom via een systeem-dialoogvenster (tkinter, in elke Python-installatie
aanwezig).

Wil je juist wel de servermeldingen live zien (voor het uitzoeken van een
probleem), gebruik dan start.bat.
"""
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
os.chdir(HIER)


def meld_fout(titel, tekst):
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(titel, tekst)
        root.destroy()
    except Exception:
        pass  # geen tkinter beschikbaar; zonder console valt er niets beters te tonen


try:
    import yaml  # noqa: F401
    import jinja2  # noqa: F401
except ImportError:
    meld_fout(
        "Ontbrekende Python-pakketten",
        "Open een opdrachtprompt in deze map en draai:\n\npip install -r requirements.txt",
    )
    sys.exit(1)

try:
    import server
    sys.exit(server.main())
except Exception as fout:
    meld_fout("Calcu-Brief-tool kon niet starten", str(fout))
    sys.exit(1)
