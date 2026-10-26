# Ligne de nuit — first integration

This presentation applies to the existing preparation, decision and accepted-mission
screens through `body.layout-nightline`. It changes HTML grouping and CSS only;
the scientific, persistence and acceptance handlers in `app.js` are unchanged.
No illustrative sky image or invented preparation time from the design mockups is
substituted for real evidence. The existing mission tasks remain authoritative.

The shared navigation retains preparation, projects and saved observations. Common
options are a user-controlled disclosure in both modes; technical decision details
still follow the existing Simple/Pro disclosure behavior. The Pro analysis date is
retained. Alerts remain outside closed disclosures. On mobile the primary action
precedes non-interactive explanatory copy, but never precedes a required acquisition
choice. The accepted-mission header keeps its close control visible during scrolling.

Verification: `tests/ui/nightline_browser.cjs` uses the production DOM/listeners and
synthetic DTOs with a browser timezone different from the site. It checks 320, 390,
768, 1024 and 1280 px in both modes, native date inputs, read-only API traffic,
mission closing by button/Escape, and refusal rendering. Existing compact-tonight
and Simple/Pro harnesses also run. Obsolete fixture expectations were aligned with
the current eligible-AQI contract and full saved-mission date range; comparison
facts and lineage warnings remain strict across mode switches.

These are local Chrome-on-Mac browser checks, not native Windows, Safari, iOS or
Android acceptance. This change has not yet been built into a new private kit or
applied to a personal profile. Package/review before asking testers to use it.
