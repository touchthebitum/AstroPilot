# Manufacturer equipment references

`astropilot/catalogue_data/equipment_references_v1.json` is an offline identification
catalogue, exposed read-only at `/v1/equipment-references`. It is separate from
`equipment_catalog.py` presets and from production setup/filter capabilities.
Its initial scope is 9 optical configurations, 8 cameras and 5 filter sets.
This is a curated starting catalogue, not comprehensive hardware coverage.

## Adding or correcting a reference

1. Verify the exact model and variant on a manufacturer product page or manual.
   Record its HTTPS URL, title and the date of the actual verification. Retailer
   text, model-name similarity and remembered specifications are insufficient.
2. Give each materially different configuration its own stable ID: native versus
   reduced focal length, MM versus MC, P25 versus older Pro, filter size and SKU.
   Include common names/types in aliases without suggesting equivalence.
3. Store only sourced facts in `specs`. Do not derive a missing aperture, filter
   bandwidth or sensor dimension by borrowing another model's values. Notes must
   explain missing/contradictory facts. The Quattro 200P USA aperture is deliberately
   absent because its product name and stated diameter need disambiguation.
4. Add the manufacturer/domain to the validator if necessary. Run schema/API tests
   and the browser equipment harness. Both PyInstaller specs and wheel package data
   already include `catalogue_data/*`; no runtime network scraping is performed.

## Authority boundaries

Every entry has `mission_compatibility: not_verified`. The schema rejects attempts
to turn a reference into an operational capability. Complete optics/camera records
may fill only their own fields in the local custom editor after the user's exact
variant confirmation. Normal configuration validation and explicit save still apply.
No preset is inferred from that selection. Custom equipment does not acquire the
verified filter capabilities of a similar preset.

Filters are identification-only here: no ownership checkbox, activation or inferred
filter profile. A Type 2c LRGB set has no fabricated narrowband FWHM. Baader filter
sets are not treated as interchangeable individual production filter profiles.
Extending actual mission support requires separate setup/filter capability work,
optical assumptions and validation; adding a reference cannot perform that work.

The existing preset scientific values are unchanged. A copied factory configuration
describes full native pixels, no camera ROI/binning, and the stated optical variant.
The user must check their actual reducer, corrector and operating configuration.
