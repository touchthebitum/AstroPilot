"""Sourced imaging extents and conservative equipment matching.

This is an imaging catalogue, not an astrometric catalogue. No coordinates,
exposure goals, ownership, guiding limits or transmission curves are inferred.
Legacy project keys and historical mission geometry remain unchanged.
"""
from dataclasses import asdict, dataclass
from copy import deepcopy
from math import atan, degrees, isfinite

from astropilot.user_profile import resolve_equipment_definition

CATALOGUE_VERSION = "2026-10-21.3"
SOURCES = {
    "ngc2000": {"title": "NGC 2000.0 · Sinnott 1988 · CDS VII/118",
        "url": "https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/118?format=html&tex=true",
        "data_url": "https://cdsarc.cds.unistra.fr/ftp/VII/118/ngc2000.dat",
        "quantity": "Largest dimension (arcmin), bytes 34–38; not an image field of view."},
    "sharpless": {"title": "Catalogue of H II Regions · Sharpless 1959 · CDS VII/20",
        "url": "https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/20?format=html&tex=true",
        "data_url": "https://cdsarc.cds.unistra.fr/ftp/VII/20/catalog.dat.gz",
        "quantity": "Maximum H II region diameter (arcmin), bytes 49–52; old-epoch coordinates are not used directly as ICRS."},
    "veil": {"title": "NASA · Cygnus Loop, about three degrees across",
        "url": "https://science.nasa.gov/solar-system/skywatching/night-sky-network/summer-triangle-corner-deneb/"},
    "ou4": {"title": "Corradi et al. 2014 · Gas physical conditions and kinematics of the giant outflow Ou4",
        "url": "https://arxiv.org/abs/1407.4617",
        "quantity": "More than one degree; a lower bound, not a measured enclosing diameter."},
    "pleiades": {"title": "ESO · The Pleiades, stars and reflection nebulosity",
        "url": "https://www.eso.org/public/images/b11/"},
    "rosette": {"title": "SDSS-V LVM: A Spatially Resolved Study of the Rosette Nebula · 2025",
        "url": "https://arxiv.org/abs/2509.10665"},
    "ic1396": {"title": "ING · IC 1396 in hydrogen-alpha · IPHAS",
        "url": "https://www.ing.iac.es/PR/press/ic1396.html"},
    "heart_soul": {"title": "NASA/JPL · Heart and Soul (infrared reference, not a visible-light preview)",
        "url": "https://science.nasa.gov/photojournal/heart-and-soul/"},
    "asi183": {"title": "ZWO · ASI183 manual v1.4",
        "url": "https://i.zwoastro.com/zwo-website/manuals/ASI183_Manual_EN_V1.4.pdf"},
    "samyang135": {"title": "Samyang · 135 mm f/2 nominal",
        "url": "https://samyangus.com/collections/samyang-lenses/products/135mm-f2-0-full-frame-telephoto"},
    "baader": {"title": "Baader · f/2 Highspeed 6.5 nm, working range f/1.8–f/3.4",
        "url": "https://www.baader-planetarium.co.uk/2022/05/13/preshift-and-further-information-concerning-baader-cmos-filters-new-f-3-filter-category/"},
    "astronomik_type2c": {"title": "Astronomik · L-RGB Type 2c",
        "url": "https://www.astronomik.com/en/RGB-Filters/L-RGB-Typ-2c/",
        "product_url": "https://www.astronomik.com/en/Astronomik-L-RGB-Type-2c-Filterset-1-25-M28-5/10220125"},
}

# A documented product family is NOT an optical transmission model or an owned
# filter. No guessed Gaussian passbands are added to the production profiles.
REFERENCE_FILTER_FAMILIES = ({
    "id": "astronomik_lrgb_type2c_125", "manufacturer": "Astronomik",
    "name": 'L-RGB Type 2c 1,25″ (M28,5)', "manufacturer_product_id": "10220125",
    "filter_types": ["L", "R", "G", "B"], "glass_thickness_mm": 1,
    "uv_ir_blocking": True, "manufacturer_focal_ratio_claim": "all_focal_ratios",
    "source_id": "astronomik_type2c", "ownership": "not_confirmed_by_this_catalogue",
    "transmission_model": None, "mission_profile_available": False,
},)


@dataclass(frozen=True)
class ImagingTarget:
    key: str
    name: str
    aliases: tuple[str, ...]
    kind: str
    extent_arcmin: float | None
    extent_source: str
    source_row: str
    scope: str
    filter_types: tuple[str, ...]
    difficulty: str
    advice: str
    extent_bound: str = "approximate"
    supporting_sources: tuple[str, ...] = ()


# Only selected numerical catalogue measurements are transcribed. A diameter is
# wavelength/depth dependent. It must never be sold as the boundary of all halos.
TARGETS = (
    ImagingTarget("M31", "Galaxie d’Andromède", ("NGC224",), "galaxy", 178, "ngc2000", "224",
        "Galaxie, dimension principale cataloguée ; halos non garantis.", ("L", "R", "G", "B"), "Pour progresser",
        "Grand champ intéressant ; le noyau brillant et les extensions demandent un traitement adapté."),
    ImagingTarget("M33", "Galaxie du Triangle", ("NGC598",), "galaxy", 62, "ngc2000", "598",
        "Disque catalogué, pas l’ensemble de ses extensions faibles.", ("L", "R", "G", "B"), "Exigeant",
        "Faible contraste ; Hα seul ne remplace pas l’acquisition de la galaxie en large bande."),
    ImagingTarget("M51", "Galaxie du Tourbillon", ("NGC5194",), "galaxy", 11, "ngc2000", "5194",
        "NGC 5194 ; cette mesure ne décrit pas tout le couple avec NGC 5195.", ("L", "R", "G", "B"), "Exigeant",
        "Une focale courte donne une petite galaxie ; ne pas attendre les détails d’une longue focale."),
    ImagingTarget("M81", "Galaxie de Bode", ("NGC3031",), "galaxy", 25.7, "ngc2000", "3031",
        "M81 seule ; le groupe M81/M82 demanderait un autre champ.", ("L", "R", "G", "B"), "Pour progresser",
        "La galaxie reste petite à 135 mm ; cadrer un groupe n’est pas équivalent à détailler M81."),
    ImagingTarget("M101", "Galaxie du Moulinet", ("NGC5457",), "galaxy", 26.9, "ngc2000", "5457",
        "Disque catalogué.", ("L", "R", "G", "B"), "Exigeant",
        "Faible contraste ; une grande taille apparente ne signifie pas une cible facile."),
    ImagingTarget("M42", "Nébuleuse d’Orion", ("NGC1976",), "hii_region", 66, "ngc2000", "1976",
        "M42 cataloguée ; ni toute la boucle de Barnard, ni le complexe d’Orion.", ("Ha",), "Pour commencer avec précautions",
        "Le cœur sature facilement. Hα donne une image monochrome et ne représente pas toutes les composantes du complexe."),
    ImagingTarget("NorthAmerica", "North America · NGC 7000", ("NGC7000",), "hii_region", 120, "ngc2000", "7000",
        "NGC 7000 seule ; Sh2-117 englobe une région plus large, incluant le Pélican.", ("Ha",), "Pour progresser",
        "Grande nébuleuse en Hα ; ne pas confondre sa taille avec le champ de la photographie de référence."),
    ImagingTarget("Rosette", "Nébuleuse de la Rosette", ("Sh2-275",), "hii_region", 100, "sharpless", "275",
        "Région HII de Sharpless ; les enveloppes faibles peuvent dépasser deux degrés.", ("Ha",), "Pour progresser",
        "La couronne de gaz convient au grand champ ; laisser de la place autour des limites cataloguées.",
        supporting_sources=("rosette",)),
    ImagingTarget("IC1396", "Région IC 1396 · avec la Trompe d’Éléphant", ("Sh2-131",), "hii_region", 170, "sharpless", "131",
        "Région HII entière ; la Trompe IC 1396A n’en est qu’un petit détail.", ("Ha",), "Exigeant",
        "Un objectif court photographie la grande région, pas une vue détaillée de la Trompe.", supporting_sources=("ic1396",)),
    ImagingTarget("IC1805", "Nébuleuse du Cœur", ("Heart", "Sh2-190"), "hii_region", 150, "sharpless", "190",
        "Sh2-190, région du Cœur ; pas seulement l’amas IC 1805.", ("Ha",), "Pour progresser",
        "Grande région d’hydrogène ; un filtre adapté ne garantit pas le contraste sous un mauvais ciel.", supporting_sources=("heart_soul",)),
    ImagingTarget("IC1848", "Nébuleuse de l’Âme", ("Soul", "Sh2-199"), "hii_region", 120, "sharpless", "199",
        "Sh2-199, région de l’Âme ; pas seulement l’amas IC 1848.", ("Ha",), "Pour progresser",
        "Photographier la région entière demande un autre cadrage qu’un détail de ses piliers.", supporting_sources=("heart_soul",)),
    ImagingTarget("M16", "Nébuleuse de l’Aigle", ("NGC6611", "Sh2-49"), "hii_region", 90, "sharpless", "49",
        "Région HII Sh2-49 ; les 35 minutes de NGC 6611 ne décrivent pas la même étendue.", ("Ha",), "Pour progresser",
        "À courte focale, les Piliers de la Création restent un petit détail. Vérifier surtout la hauteur au-dessus de l’horizon."),
    ImagingTarget("M17", "Nébuleuse Oméga", ("NGC6618", "Sh2-45"), "hii_region", 60, "sharpless", "45",
        "Région HII Sh2-45 ; enveloppe différente de l’entrée NGC 6618.", ("Ha",), "Pour progresser",
        "La visibilité dépend fortement de la hauteur de cette cible dans le ciel."),
    ImagingTarget("Sh2-129", "Chauve-souris · Sh2-129", (), "hii_region", 140, "sharpless", "129",
        "Région HII Sh2-129 ; Ou4 est une cible distincte à l’intérieur du même champ.", ("Ha",), "Exigeant",
        "Commencer en Hα dans ce champ ; ne pas assimiler la présence d’Ou4 à sa détection."),
    ImagingTarget("Ou4", "Calamar · Ou4", (), "bipolar_outflow", 60, "ou4", "abstract",
        "Extension supérieure à un degré ; borne inférieure, insuffisante pour garantir le cadrage.", ("OIII",), "Très difficile",
        "Cible extrêmement faible, à réserver pour plus tard si vous débutez.", extent_bound="lower_limit"),
    ImagingTarget("Veil", "Dentelles du Cygne · ensemble", ("CygnusLoop",), "supernova_remnant", 180, "veil", "Cygnus Loop",
        "Ensemble des Dentelles ; ni NGC 6960 ni NGC 6992 isolément.", ("Ha", "OIII"), "Exigeant",
        "Hα et OIII isolent des émissions différentes ; une seule acquisition ne constitue pas une image couleur."),
    ImagingTarget("M13", "Grand amas d’Hercule", ("NGC6205",), "globular_cluster", 16.6, "ngc2000", "6205",
        "Amas catalogué.", ("L", "R", "G", "B"), "Pour progresser",
        "Le détail des étoiles demande une échelle adaptée ; les filtres SHO ne sont pas le premier choix."),
    ImagingTarget("M27", "Nébuleuse Dumbbell", ("NGC6853",), "planetary_nebula", 15.2, "ngc2000", "6853",
        "Dimension cataloguée, incluant des extensions plus larges que le cœur brillant.", ("Ha", "OIII"), "Pour progresser",
        "Petite à courte focale ; les halos faibles ne sont pas aussi accessibles que le cœur."),
    ImagingTarget("M57", "Nébuleuse de l’Anneau", ("NGC6720",), "planetary_nebula", 2.5, "ngc2000", "6720",
        "Dimension cataloguée ; l’anneau brillant est plus petit.", ("Ha", "OIII"), "Exigeant à courte focale",
        "Très petite avec un 135 mm ; tenir dans le champ ne signifie pas pouvoir la détailler."),
    ImagingTarget("M45", "Pléiades et nébulosités par réflexion", ("Pleiades",), "reflection_and_cluster", None, "pleiades", "",
        "Limite photographique des poussières non documentée ici ; aucune taille inventée.", ("L", "R", "G", "B"), "Pour progresser",
        "Les poussières diffusent la lumière des étoiles : SHO n’est pas le premier choix pour cette image."),
)

from decision.definitions.production_extended_targets import EXTENDED_HA_TARGETS
SOURCES["openngc"] = {"title": "OpenNGC · pinned NGC.csv, ICRS centres and major axes",
    "url": "https://github.com/mattiaverga/OpenNGC/blob/be3cd6c5498806a2fbb2f7e0452ef802dbb02be0/database_files/NGC.csv", "quantity": "MajAx in arcminutes; not a photograph field or B-band magnitude."}
TARGETS += tuple(ImagingTarget(t["key"], t["name"], (), "hii_region", t["extent"],
    t["extent_source"], t["source_row"], t["advice"], ("Ha",), t["difficulty"], t["advice"])
    for t in EXTENDED_HA_TARGETS if t["key"] not in {item.key for item in TARGETS})


def canonical_target(key: str) -> ImagingTarget | None:
    return next((target for target in TARGETS if key == target.key or key in target.aliases), None)


def _positive(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and isfinite(value) and value > 0)


def sensor_geometry(equipment: dict | None) -> dict:
    """Nominal full-frame, bin-1 geometry. No guessed sensor, ROI or reducer."""
    if not isinstance(equipment, dict) or not _positive(equipment.get("focal_length_mm")):
        return {"status": "unknown", "reason": "Focale non renseignée ou invalide."}
    fields = ("sensor_width_px", "sensor_height_px", "pixel_size_um")
    if not all(_positive(equipment.get(key)) for key in fields):
        return {"status": "unknown", "reason": "Dimensions du capteur ou taille des pixels manquantes."}
    if any(not float(equipment[key]).is_integer() for key in fields[:2]):
        return {"status": "unknown", "reason": "Dimensions en pixels invalides."}
    pitch = equipment["pixel_size_um"]
    width, height = (equipment[key] * pitch / 1000 for key in fields[:2])
    if not all(_positive(value) for value in (width, height)):
        return {"status": "unknown", "reason": "Dimensions calculées du capteur invalides."}
    for key, derived in (("sensor_width_mm", width), ("sensor_height_mm", height)):
        supplied = equipment.get(key)
        # 1% tolerates manufacturer rounding (13.2 x 8.8 vs pixel-array size),
        # but does not silently accept an unrelated sensor description.
        if supplied is not None and (not _positive(supplied) or abs(supplied / derived - 1) > .01):
            return {"status": "inconsistent", "reason": "Dimensions du capteur et taille des pixels incohérentes."}
    focal = equipment["focal_length_mm"]
    return {"status": "nominal", "sensor_width_mm": width, "sensor_height_mm": height,
        "field_width_deg": degrees(2 * atan(width / (2 * focal))),
        "field_height_deg": degrees(2 * atan(height / (2 * focal))),
        "sampling_arcsec_per_pixel": degrees(2 * atan(pitch / 1000 / (2 * focal))) * 3600,
        "assumptions": "Capteur entier, pixels natifs, focale déclarée ; sans recadrage, binning ni réducteur ajouté. À vérifier par résolution astrométrique."}


def framing_match(target: ImagingTarget, geometry: dict) -> dict:
    if geometry.get("status") != "nominal" or target.extent_arcmin is None or target.extent_bound != "approximate":
        return {"status": "unknown", "label": "Cadrage à vérifier : dimensions insuffisantes."}
    short, long = sorted((geometry["field_width_deg"] * 60, geometry["field_height_deg"] * 60))
    extent = target.extent_arcmin
    # Model the catalogued diameter as a circular planning envelope, independent
    # of camera rotation. This approximation cannot certify irregular boundaries,
    # faint halos, centering or distortion. Do not invent a minor axis.
    if extent * 1.10 > short:
        return {"status": "requires_framing_check",
            "label": "Cadrage à vérifier : rotation, recadrage ou mosaïque peuvent être nécessaires."}
    fraction = extent / long
    small = fraction < .15  # Editorial beginner threshold, NOT a resolution limit.
    return {"status": "small_in_field" if small else "nominal_fit",
        "label": "Cible petite dans ce champ : détails limités." if small else "Étendue cataloguée compatible avec le champ nominal, avec une marge de cadrage.",
        "extent_on_long_axis_fraction": fraction,
        "extent_pixels_approx": extent * 60 / geometry["sampling_arcsec_per_pixel"],
        "margin_factor": 1.10,
        "policy": "Marge éditoriale 10 % sur la plus grande dimension et comparaison au petit côté du champ ; petite cible si moins de 15 % du grand côté. Ce ne sont pas des seuils physiques de détection."}


def filter_match(target: ImagingTarget, equipment: dict | None, filter_profile_id: str) -> dict:
    from decision.definitions.production_filter_optical_profiles import FILTER_OPTICAL_PROFILES
    optical = next((item for item in FILTER_OPTICAL_PROFILES if item.filter_profile_id == filter_profile_id), None)
    if optical is None:
        return {"status": "unknown", "label": "Référence exacte du filtre à confirmer."}
    if optical.filter_type not in target.filter_types:
        return {"status": "not_primary_choice", "label": "Ce filtre n’est pas retenu pour l’objectif photographique décrit."}
    if not equipment or equipment.get("monochrome") is not True:
        return {"status": "unknown", "label": "Cette association n’est vérifiée ici qu’avec une caméra monochrome."}
    ratio = equipment.get("f_ratio")
    if not _positive(ratio):
        return {"status": "unknown", "label": "Ouverture de travail à confirmer."}
    verified = {"baader_ha_highspeed_6_5nm", "baader_oiii_highspeed_6_5nm", "baader_sii_highspeed_6_5nm"}
    if filter_profile_id not in verified:
        return {"status": "unknown", "label": "Plage d’ouverture de ce filtre non documentée."}
    if not 1.8 <= ratio <= 3.4:
        return {"status": "outside_documented_range", "label": "Ouverture hors de la plage f/1,8–f/3,4 documentée pour ces Baader 6,5 nm f/2 Highspeed.", "source_id": "baader"}
    return {"status": "documented_match", "label": "Émission visée et ouverture déclarée compatibles avec ce filtre documenté.", "source_id": "baader",
        "working_f_ratio": ratio,
        "limitations": "Pas de courbe de transmission mesurée, ni de garantie d’absence de vignetage. Le diamètre 1,25 pouce ne suffit pas à vérifier l’illumination du capteur."}


def equipment_catalogue(*, profile: dict, equipment_id: str, confirmed_filter_profile_ids=()) -> dict:
    """Read-only reference inventory, deliberately independent of weather/progress."""
    equipment = resolve_equipment_definition(profile, equipment_id)
    from astropilot.extended_catalogue import catalogue_summary
    geometry = sensor_geometry(equipment)
    from decision.definitions.production_imaging_fields import CELESTIAL_OBJECT_DEFINITIONS, IMAGING_FIELD_DEFINITIONS
    objects = {item.celestial_object_id: item.canonical_name for item in CELESTIAL_OBJECT_DEFINITIONS}
    targets = []
    for target in TARGETS:
        entry = asdict(target)
        entry["framing"] = framing_match(target, geometry)
        entry["confirmed_filters"] = [{"filter_profile_id": identity, **filter_match(target, equipment, identity)}
            for identity in sorted(set(confirmed_filter_profile_ids))]
        entry["project_routes"] = [{"imaging_field_id": field.imaging_field_id,
            "acquisition_intent_id": intent.acquisition_intent_id}
            for field in IMAGING_FIELD_DEFINITIONS for intent in field.acquisition_intents
            if any(objects.get(component) == target.key for component in intent.primary_component_ids)]
        entry["project_supported"] = bool(entry["project_routes"])
        entry["filter_policy"] = "Approches éditoriales pour cet objectif photographique, non une liste exhaustive de toutes les raies présentes. Les filtres ne sont pas supposés possédés."
        targets.append(entry)
    return {"version": CATALOGUE_VERSION, "verified_on": "2026-10-21", "equipment_id": equipment_id, "geometry": geometry,
        "targets": targets, "sources": deepcopy(SOURCES),
        "reference_filter_families": deepcopy(REFERENCE_FILTER_FAMILIES),
        "extended_catalogue": catalogue_summary(),
        "notice": "Correspondances documentées, pas une recommandation de sortie. La météo, la hauteur de la cible et vos horaires restent à analyser. Les entrées de référence ne créent pas de mission.",
        "limits": ["Les limites diffuses dépendent de la longueur d’onde et de la profondeur des images.",
            "Aucune durée de pose unitaire, durée totale idéale, qualité de suivi ou capacité de batterie n’est déduite de cette table.",
            "Monture, charge, guidage, espacement des filtres et ouverture réellement utilisée restent à contrôler sur le terrain.",
            "Le Samyang est un objectif f/2 nominal ; le préréglage existant utilise f/2,8 comme ouverture de travail. Il n’est pas modifié : confirmer la bague réellement utilisée.",
            "Les alias Cœur/Heart et Âme/Soul sont regroupés ; les projets et missions existants ne sont pas modifiés."]}
