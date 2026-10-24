# Orion in beginner target discovery

M42 is the third operational Hα discovery field, alongside North America and Rosette. The larger offline reference catalogue remains separate from operational eligibility.

The production field `m42` contains only the M42 H II region and the `m42_ha` intent. Its planning centre is the existing catalogue centre, 83.8221°, −5.3911°; the geometry definition is independent of the legacy catalogue. Its studied 66′ approximate extent comes from CDS VII/118 (NGC 1976), not the photo footprint. No historical catalogue coordinates or project keys are migrated.

Discovery retains the material framing gate, confirmed exact filter and documented focal-ratio range, physical forecast viability and availability window. Choosing a card only prefills the target and confirmed filter. The integration goal stays empty; existing images must be explicitly declared. Mission acceptance requires the saved project and a fresh decision; discovery and acceptance add no acquired exposure.

## Reference image

- ESO image [eso1723a](https://eso.org/public/images/eso1723a/), credit **ESO/G. Beccari**.
- [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) under [ESO terms](https://www.eso.org/public/outreach/copyright/), checked 2026-10-21.
- Original screen JPEG: https://cdn.eso.org/images/screen/eso1723a.jpg. The bundled bytes are unchanged; only browser display sizing is applied.
- Optical g, r, Hα, i composite; 59.95′ × 46.56′ image footprint. This is a tighter professional view of central Orion, not a full Samyang field simulation. Attribution and licence are shown next to the image, with a visible scope caveat.
- Hα imaging with a monochrome camera produces a monochrome result. Help warns of the bright core relative to the faint outer emission and asks the operator to check saturation; no fixed exposure prescription is made.

## Validation

`tests/api/test_orion_discovery.py` covers synthetic winter weather, read-only preselection, serving the real JPEG, explicit project creation, fresh decision and acceptance without acquired progress or executions. It also rejects full clouds, OIII-only confirmation and a twenty-minute window. Shared discovery, first-project, geometry and packaging tests remain applicable. This is software validation, not native-kit or real-observing attestation. Existing private kits are unchanged.
