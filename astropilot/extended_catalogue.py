"""Offline, pinned OpenNGC reference catalogue; never a mission authority.

The bundled database and derived OpenNGC records are CC-BY-SA-4.0. Source
classifications, J2000 coordinates and dimensions retain their own provenance.
Curated whole imaging regions are not conflated with small NGC/IC components.
"""
import csv
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from functools import lru_cache
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
from types import SimpleNamespace
import unicodedata

from astropilot.target_catalogue import SOURCES, TARGETS, framing_match, sensor_geometry
from astropilot.user_profile import resolve_equipment_definition

DATA = Path(__file__).with_name("catalogue_data")
KINDS = {
    "G": ("galaxy", "Galaxie"), "GPair": ("galaxy_group", "Paire de galaxies"),
    "GTrpl": ("galaxy_group", "Triplet de galaxies"), "GGroup": ("galaxy_group", "Groupe de galaxies"),
    "OCl": ("open_cluster", "Amas ouvert"), "GCl": ("globular_cluster", "Amas globulaire"),
    "Cl+N": ("cluster_nebula", "Amas et nébulosité : étendue de la source à vérifier"),
    "PN": ("planetary_nebula", "Nébuleuse planétaire"), "HII": ("hii_region", "Région HII"),
    "EmN": ("emission_nebula", "Nébuleuse en émission"), "RfN": ("reflection_nebula", "Nébuleuse par réflexion"),
    "DrkN": ("dark_nebula", "Nébuleuse sombre"), "Neb": ("nebula", "Nébuleuse : nature à préciser"),
    "SNR": ("supernova_remnant", "Rémanent de supernova"), "*Ass": ("association", "Association d’étoiles"),
    "*": ("star", "Étoile : référence, pas une nébuleuse"), "**": ("double_star", "Étoile double"),
    "Nova": ("nova", "Nova : état actuel non vérifié"), "Other": ("unknown", "Classification à confirmer"),
}
# Only these associations refer to the same principal object. Whole HII regions
# (IC1396, Heart, Soul, M16, M17, Rosette, Veil) deliberately remain separate.
CURATED_ASSOCIATIONS = {"M31": "NGC0224", "M33": "NGC0598", "M51": "NGC5194",
    "M81": "NGC3031", "M101": "NGC5457", "M42": "NGC1976", "NorthAmerica": "NGC7000",
    "M13": "NGC6205", "M27": "NGC6853", "M57": "NGC6720", "M45": "Mel022"}


def _normalise(text):
    text = "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "", text)
    return re.sub(r"(?<=[a-z])0+(?=[1-9])", "", text)


def _number(value, *, positive=False):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) and (not positive or result > 0) else None


def _coordinate(text, *, ra):
    try:
        first, minute, second = map(float, text.split(":"))
        if ra and (first < 0 or text.startswith("-")):
            return None
        value = (abs(first) + minute / 60 + second / 3600) * (15 if ra else 1)
        if not ra and text.startswith("-"):
            value = -value
        if not (0 <= minute < 60 and 0 <= second < 60 and isfinite(value)):
            return None
        return value if (0 <= value < 360 if ra else -90 <= value <= 90) else None
    except (ValueError, AttributeError):
        return None


@lru_cache(maxsize=1)
def _load():
    manifest = json.loads((DATA / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if hashlib.sha256((DATA / name).read_bytes()).hexdigest() != digest:
            raise ValueError("catalogue_source_integrity_failed")
    records, duplicates, excluded, raw_count = [], [], Counter(), 0
    for filename in ("NGC.csv", "addendum.csv"):
        with (DATA / filename).open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream, delimiter=";"):
                raw_count += 1
                if row["Type"] in {"Dup", "NonEx"}:
                    excluded[row["Type"]] += 1
                    if row["Type"] == "Dup":
                        duplicates.append((row["Name"], row["NGC"], row["IC"]))
                    continue
                aliases = [row["Name"]]
                if row["M"]:
                    aliases.append("M" + str(int(row["M"])))
                aliases.extend(part.strip() for part in row["Identifiers"].split(",") if part.strip())
                for column, prefix in (("NGC", "NGC"), ("IC", "IC")):
                    for part in row[column].split(","):
                        if part.strip():
                            aliases.append(prefix + part.strip())
                kind, label = KINDS.get(row["Type"], ("unknown", "Classification à confirmer"))
                major, minor = _number(row["MajAx"], positive=True), _number(row["MinAx"], positive=True)
                inconsistent_axes = major is not None and minor is not None and minor > major
                field_sources = dict(part.split(":", 1) for part in row["Sources"].split("|") if ":" in part)
                infrared_scope_unverified = kind in {"galaxy", "galaxy_group"} and field_sources.get("MajAx") == "2"
                dimension_note = ""
                if infrared_scope_unverified:
                    dimension_note = "Dimensions SIMBAD : d’après OpenNGC, ces valeurs de repli peuvent provenir de mesures infrarouges 2MASS. Le périmètre visible reste à vérifier."
                elif kind in {"open_cluster", "globular_cluster", "association", "cluster_nebula"} and field_sources.get("MajAx") == "5":
                    dimension_note = "Mesure d’amas issue de MWSC ; la documentation OpenNGC se réfère à sa zone centrale. Elle ne délimite pas toute la nébulosité environnante."
                records.append({"id": "openngc:" + row["Name"], "catalogue_id": row["Name"],
                    "display_name": ("M" + str(int(row["M"])) + " · " if row["M"] else "")
                        + row["Name"] + (" · " + row["Common names"] if row["Common names"] else ""),
                    "common_names": row["Common names"], "aliases": aliases, "kind": kind, "kind_label": label,
                    "constellation": row["Const"], "source_type": row["Type"],
                    "ra_deg": _coordinate(row["RA"], ra=True), "dec_deg": _coordinate(row["Dec"], ra=False),
                    "coordinate_reference": "J2000 déclaré par OpenNGC ; pas de transformation implicite en ICRS.",
                    "major_arcmin": major, "minor_arcmin": minor,
                    "position_angle_deg": _number(row["PosAng"]),
                    "extent_arcmin": None if inconsistent_axes else major,
                    "extent_bound": "scope_unverified" if infrared_scope_unverified else "approximate",
                    "dimension_note": dimension_note, "dimensions_inconsistent": inconsistent_axes,
                    "magnitudes": {"B": _number(row["B-Mag"]), "V": _number(row["V-Mag"])},
                    "source_id": "openngc", "source_row": row["Name"], "source_file": filename,
                    "source_url": f"{manifest['upstream_url']}/blob/{manifest['revision']}/database_files/{filename}",
                    "source_fields": row["Sources"], "license": "CC-BY-SA-4.0",
                    "scope": "Étendue de cette entrée OpenNGC ; ni le champ d’une image, ni nécessairement toute la région environnante.",
                    "curated_notes": [], "identity_notes": [], "mission_enabled_by_catalogue": False})
    by_name = {record["catalogue_id"]: record for record in records}
    def identifier(value, prefix):
        return prefix + value.strip().removeprefix(prefix).zfill(4)
    # Resolve explicit duplicate chains; do not guess aliases from proximity.
    for _ in range(len(duplicates) + 1):
        unresolved = []
        for name, ngc, ic in duplicates:
            names = [identifier(v, p) for values, p in ((ngc, "NGC"), (ic, "IC")) for v in values.split(",") if v.strip()]
            masters = {by_name[n]["id"]: by_name[n] for n in names if n in by_name}
            if len(masters) == 1:
                master = next(iter(masters.values()))
                master["aliases"].append(name); by_name[name] = master
            else:
                unresolved.append((name, ngc, ic))
        if len(unresolved) == len(duplicates):
            break
        duplicates = unresolved
    for target in TARGETS:
        associated = by_name.get(CURATED_ASSOCIATIONS.get(target.key))
        if associated is not None:
            associated["curated_notes"].append(asdict(target))
            associated["aliases"].extend((target.key, *target.aliases))
        else:
            records.append({"id": "imaging-region:" + target.key, "catalogue_id": target.key,
                "display_name": target.name, "common_names": target.name,
                "aliases": [target.key, *target.aliases], "kind": target.kind,
                "kind_label": "Champ photographique documenté · " + next(
                    (label for kind, label in KINDS.values() if kind == target.kind),
                    "Écoulement bipolaire" if target.kind == "bipolar_outflow" else "Région étendue"),
                "constellation": None, "source_type": None, "ra_deg": None, "dec_deg": None,
                "coordinate_reference": "Aucune nouvelle coordonnée certifiée pour ce champ.",
                "major_arcmin": target.extent_arcmin, "minor_arcmin": None, "position_angle_deg": None,
                "extent_arcmin": target.extent_arcmin, "extent_bound": target.extent_bound,
                "dimension_note": "", "dimensions_inconsistent": False, "magnitudes": {"B": None, "V": None},
                "source_id": target.extent_source, "source_row": target.source_row,
                "source_url": SOURCES[target.extent_source]["url"],
                "license": None, "scope": target.scope, "curated_notes": [asdict(target)], "identity_notes": [],
                "mission_enabled_by_catalogue": False})
    # OpenNGC omits M102. Record the NASA Hubble association explicitly, rather
    # than silently pretending the historical identification is undisputed.
    if "NGC5866" in by_name:
        by_name["NGC5866"]["aliases"].append("M102")
        by_name["NGC5866"]["identity_notes"].append({
            "text": "M102 est associé ici à NGC 5866 suivant le catalogue Hubble de la NASA. L’identification historique est discutée ; la table Messier HEASARC l’associe à une répétition de M101.",
            "sources": ["https://science.nasa.gov/mission/hubble/science/explore-the-night-sky/hubble-messier-catalog/messier-102/",
                "https://heasarc.gsfc.nasa.gov/W3Browse/general-catalog/messier.html"]})
    for record in records:
        record["aliases"] = sorted(set(record["aliases"]))
        record["_search"] = _normalise(" ".join((record["display_name"], *record["aliases"],
            *(note["name"] for note in record["curated_notes"]))))
        record["_identifiers"] = {_normalise(alias) for alias in record["aliases"]}
    stats = {"records": len(records), "openngc_source_rows": raw_count,
        "openngc_records": sum(r["source_id"] == "openngc" for r in records),
        "additional_imaging_regions": sum(r["source_id"] != "openngc" for r in records),
        "excluded_duplicates": excluded["Dup"], "excluded_nonexistent": excluded["NonEx"],
        "unresolved_duplicate_aliases": len(duplicates),
        "with_catalogued_extent": sum(r["extent_arcmin"] is not None for r in records),
        "visible_extent_unverified": sum(r["extent_bound"] == "scope_unverified" for r in records),
        "with_coordinates": sum(r["ra_deg"] is not None and r["dec_deg"] is not None for r in records),
        "messier_designations": len({int(a[1:]) for r in records for a in r["aliases"] if re.fullmatch(r"M\d+", a)}),
        "deep_sky_classified_records": sum(r["kind"] not in {"star", "double_star", "nova", "unknown"} for r in records),
        "by_kind": dict(Counter(r["kind"] for r in records)),
        "counting_note": "Nombre de fiches : les régions et leurs composantes sont distinctes et peuvent se superposer. Les doublons explicites et objets inexistants sont exclus ; étoiles et classifications incertaines restent identifiées comme telles."}
    return records, stats, manifest


def catalogue_summary():
    _, stats, manifest = _load()
    return {**deepcopy(stats), "source_revision": manifest["revision"], "retrieved_on": manifest["retrieved_on"],
        "credit": manifest["author"], "source_url": manifest["upstream_url"],
        "license": manifest["license"], "license_url": manifest["license_url"]}


def search_catalogue(*, profile, equipment_id, query="", kind=None, framing=None, offset=0, limit=25):
    equipment = resolve_equipment_definition(profile, equipment_id)
    if equipment_id is not None and equipment is None:
        raise ValueError("catalogue_equipment_unresolved")
    geometry = sensor_geometry(equipment)
    records, stats, manifest = _load()
    needle = _normalise(query.strip())
    matches = [record for record in records if (not needle or needle in record["_search"])
               and (not kind or record["kind"] == kind)]
    # Exact designations first: M1 must not be lost behind M10...M109.
    if needle:
        matches.sort(key=lambda item: (needle not in item["_identifiers"], item["catalogue_id"]))
    def assess(record):
        return framing_match(SimpleNamespace(extent_arcmin=record["extent_arcmin"],
            extent_bound=record["extent_bound"]), geometry)
    if framing:
        matches = [record for record in matches if assess(record)["status"] == framing]
    results = [{**deepcopy({key: value for key, value in record.items() if not key.startswith("_")}),
                "framing": assess(record)} for record in matches[offset:offset + limit]]
    return {"total": len(matches), "offset": offset, "limit": limit, "results": results,
        "equipment_id": equipment_id, "equipment_name": equipment.get("name", equipment_id) if equipment else "Matériel non renseigné",
        "geometry": geometry, "catalogue": catalogue_summary(),
        "notice": "Catalogue de référence hors ligne. Un cadrage favorable ne vérifie ni la visibilité depuis votre site aux horaires choisis, ni la météo, ni le suivi, ni le filtre, ni la difficulté. Cette recherche ne crée aucune mission.",
        "filter_notice": "Aucun filtre n’est déduit automatiquement du seul type d’objet. Les conseils spécifiques restent limités aux fiches étudiées.",
        "license_notice": f"Données OpenNGC : {manifest['author']}, CC BY-SA 4.0. Sources et dimensions originales conservées ; extraction et regroupement des alias par NightMerit."}
