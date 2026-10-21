# Curated Hα expansion, 2026-10-21

The operational discovery registry expands from 5 to 13 regions. New entries:
M16 / whole Sh2-49, M17 / whole Sh2-45, NGC1499 (California), IC5070
(Pelican), IC434 (the emitting background behind the Horsehead), Sh2-296
(whole Seagull), NGC3372 (Carina), and IC4628 (Prawn).

This is an Hα expansion for exact confirmed Baader Highspeed 6.5 nm profiles
and compatible declared mono equipment. It does not activate LRGB ownership,
create optical models, promise a result, or assign integration goals. At most
three physically viable suggestions are shown. Northern and southern sites
use identical altitude, weather, framing, filter and productive-window gates.
A southern catalogue entry is not an offer to observe it from Switzerland.

## Scientific provenance and identity

NGC/IC centres (ICRS) and major axes are transcribed from the unchanged pinned
OpenNGC NGC.csv, revision be3cd6c5498806a2fbb2f7e0452ef802dbb02be0.
See packaged catalogue_data/manifest.json, AUTHORS and CC-BY-SA-4.0.txt for
Mattia Verga and contributors, file hashes, licence and source attribution.
OpenNGC B magnitudes are deliberately not copied as visual magnitudes.
New scoring entries use the existing unknown-magnitude heuristic, not an
invented measurement. Difficulty and practical advice are editorial.

Whole-region maximum diameters from Sharpless/CDS VII/20 are M16/Sh2-49
90′, M17/Sh2-45 60′ and Sh2-296 200′. M16 and M17 retain their historical
keys and planning centres, but equipment scoring now uses those documented
whole-region diameters consistently with the curated framing check. No saved
project, mission geometry or acquisition duration is rewritten.

For Sh2-296, the CDS FK4 B1950 centre (105.8625°, −11.141388888888889°)
is transformed with Astropy FK4(equinox=B1950.0).icrs to
(106.4502139544189°, −11.218845849756823°). The small IC2177 reflection
component is not silently substituted for this HII region. NGC1499 is 160′;
the much larger whole Sh2-220 complex is 320′ and is not offered as this field.

Sources:
- https://github.com/mattiaverga/OpenNGC
- https://cdsarc.cds.unistra.fr/ftp/VII/20/ReadMe
- https://cdsarc.cds.unistra.fr/ftp/VII/20/catalog.dat.gz

The reference inventory now contains 26 curated material studies. The offline
search still has 13,372 original OpenNGC records after exclusions, plus ten
explicitly separate imaging regions: 13,382 searchable records in total.
Five new studies attach to existing exact-object records; Sh2-296 remains
separate. Raw pinned data and their hashes are unchanged.

## Photographs

Original JPEG bytes are packaged unchanged. Source, full credit, licence,
SHA256 and scope are retained in web/target-expansion-credits.txt and shown
on the discovery cards. Nico Carver grants CC BY-SA 4.0 on the linked source
pages; ESO's default image licence is CC BY 4.0, with full credit required.
See https://www.eso.org/public/copyright/ . No endorsement is implied.

The M16/M17 photograph shows both regions. The Pelican photograph also shows
North America. Carina and the Horsehead are close views, explicitly identified
as such; they do not simulate a 135 mm image. The Seagull reference is an Hα
image. Colour references can combine several filters. Neither source
integration time nor camera framing is copied into a user's project.

## Verification

Seasonal API tests use explicitly synthetic weather and the actual sky,
material, window and intent evaluators. Each new field is isolated in the
registry for coverage, without replacing its sky evaluation or forcing a
positive score. Positive cases cover northern and southern sites; refusal
cases cover insufficient altitude from Buttes. Configuration, explicit
selection, cross-intent rejection and mission acceptance are exercised with
zero acquired progress and no automatic execution creation. Existing tests
retain cloud, unconfirmed-filter, framing and selection-continuity refusals.
Synthetic results are not observing evidence or Windows operator validation.
