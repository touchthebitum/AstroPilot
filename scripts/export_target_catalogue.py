"""Export a self-contained, read-only reference browser for an explicit preset.

No user profile or weather is loaded. OpenNGC-derived data remain CC-BY-SA-4.0;
the complete licence and credit accompany every export.
"""
import argparse
from copy import deepcopy
from html import escape
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from astropilot.equipment_catalog import EQUIPMENT_PROFILES
from astropilot.extended_catalogue import DATA, _load, search_catalogue
from astropilot.target_catalogue import framing_match


def export_catalogue(equipment_id, output):
    payload = search_catalogue(profile={}, equipment_id=equipment_id, limit=1)
    records, _, _ = _load()
    payload["results"] = [{**deepcopy({key: value for key, value in record.items() if not key.startswith("_")}),
        "search_text": record["_search"],
        "framing": framing_match(SimpleNamespace(extent_arcmin=record["extent_arcmin"],
            extent_bound=record["extent_bound"]), payload["geometry"])} for record in records]
    payload["total"] = len(records)
    web = ROOT / "astropilot/web"
    document = (web / "catalogue.html").read_text()
    document = document.replace('<link rel="stylesheet" href="/ui/catalogue.css">', '<style>' + (web / 'catalogue.css').read_text() + '</style>')
    document = document.replace('<script src="/ui/catalogue.js" defer></script>', '')
    document = document.replace('<a href="/">← Retour à NightMerit</a>', '<p>NightMerit · Catalogue autonome hors ligne · Matériel de référence, sans profil personnel</p>')
    document = document.replace('<a href="/ui/catalogue-license.txt">Licence CC BY-SA 4.0</a>', '<a href="https://creativecommons.org/licenses/by-sa/4.0/">Licence CC BY-SA 4.0</a>')
    license_text = '<details><summary>Texte intégral de la licence des données OpenNGC</summary><pre style="white-space:pre-wrap">' + escape((DATA/'CC-BY-SA-4.0.txt').read_text()) + '</pre></details>'
    license_text += '<details><summary>Attribution originale OpenNGC</summary><pre style="white-space:pre-wrap">' + escape((DATA/'UPSTREAM-COPYRIGHT.txt').read_text()) + '</pre></details>'
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    document = document.replace('</main>', license_text + '</main>')
    document = document.replace('</body>', '<script>window.NIGHTMERIT_OFFLINE_CATALOGUE=' + encoded + ';</script><script>' + (web/'catalogue.js').read_text() + '</script></body>')
    Path(output).write_text(document)
    return len(records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--equipment', choices=sorted(EQUIPMENT_PROFILES), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(f'{export_catalogue(args.equipment, args.output)} records exported to {args.output}')
