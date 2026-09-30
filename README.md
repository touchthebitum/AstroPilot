# AstroPilot

AI-powered astrophotography planning platform.

Local release candidate: **1.0.0-beta.7** (canonical version `1.0.0b7`).
This preparation does not build, tag, publish, or push beta.7. After the
versioning commit, macOS and Windows must both be built and validated from that
same commit. The future tag is `v1.0.0-beta.7`.

The historical `v1.0.0-beta.6` tag is the comparison baseline. See the
[beta.7 release notes](docs/release_notes_beta7.md) and
[remaining release gates](docs/release_checklist.md).

## Product and technical identity for beta.7

**NightMerit is the user-visible application name.** To preserve upgrades and
existing beta profiles, the distributed and technical identity remains
**AstroPilot** for beta.7. In particular, beta.7 keeps `AstroPilot.app`,
`AstroPilot.exe`, the AstroPilot installer, the existing bundle ID, existing
data and log paths, and the Python package name `astropilot`. These technical
artifacts and paths must not be renamed as part of beta.7.

Published historical baseline: **v1.0.0-beta.4** (canonical version `1.0.0b4`).

Published historical baseline: **v1.0.0-beta.3** (canonical version `1.0.0b3`).
Current beta targets: macOS Apple Silicon and Windows x86_64. Linux, Android,
iOS, and Windows ARM are outside this beta.

Historical beta.3 validation record (recorded before publication):

Both beta.3 artifacts use source commit
`c8566443c1caf612d122a8d217fe05884ac6aace`. macOS signing, notarization,
stapling, Gatekeeper, and ZIP extraction checks are validated. Windows native
installation, launch, update, uninstall, reinstall, and data preservation are
validated. The beta.3 clean-machine test on the Mac mini, native Windows user
path with spaces/accented characters, and Windows Start Menu launch have passed.
Full suites were validated on macOS and Windows for beta.3. This is a historical
validation record, not a validation of beta.7.

See [closed-beta status and artifact SHA-256 values](docs/closed_beta.md),
[release gates](docs/release_checklist.md), and
[Windows installer documentation](docs/WINDOWS_INSTALLER.md).

Features:
- Sky quality analysis
- Object recommendation engine
- Weather integration
- Moon impact analysis
- SQM prediction
- GPS-based location detection
- Astrophotography session planning

## Prerequisites

- Python 3.11, 3.12, or 3.13 (`>=3.11,<3.14`)
- [uv](https://docs.astral.sh/uv/)

## Environment setup

Synchronize the locked runtime environment:

```bash
uv sync --locked
```

For development and tests, include the `test` extra:

```bash
uv sync --locked --extra test
```

Commands below use `--no-sync` and therefore assume that the corresponding
synchronization step has already completed.

## User data (source checkout and installed wheel)

For the web UI, point AstroPilot to a writable user-data directory. It can
create `user_profile.json` during initial configuration; command-line decision
usage still requires a valid profile. Set the directory before launching it:

```bash
export ASTROPILOT_DATA_DIR=/path/to/astropilot-data
```

The configured directory must already exist. A repository checkout includes
the current local profile at `data/user_profile.json`, which is used when
`ASTROPILOT_DATA_DIR` is not set. An installed wheel does not include that
local profile.

## Tests

Run tests through the synchronized project interpreter:

```bash
uv run --locked --no-sync python -m pytest -q
```

Using `python -m pytest` avoids accidentally invoking a global `pytest` tied
to a different Python environment.

## Command-line usage

Run AstroPilot from the project directory with the locked environment:

```bash
uv run --locked --no-sync astropilot --mode tonight
```

Available display modes are `tonight`, `portfolio`, `calendar`, and `full`:

```bash
uv run --locked --no-sync astropilot --mode portfolio
uv run --locked --no-sync astropilot --mode calendar
uv run --locked --no-sync astropilot --mode full
```

Compare equipment for an object or force a complete target analysis:

```bash
uv run --locked --no-sync astropilot --object M31
uv run --locked --no-sync astropilot --target-object IC1396
```

Inspect, configure, or clear a project's per-filter hour targets:

```bash
uv run --locked --no-sync astropilot --filter-targets-show IC1396
uv run --locked --no-sync astropilot --filter-targets-set IC1396 Ha=6 OIII=5 SII=4
uv run --locked --no-sync astropilot --filter-targets-clear IC1396
```

The `set` and `clear` commands update `user_profile.json` in
`ASTROPILOT_DATA_DIR` when configured, or `data/user_profile.json` in a
repository checkout otherwise. Treat that file as local user data and review
it separately before committing changes.

## API and UI

La publication des observations terrain exige l’API navigateur Web Locks :
Chrome/Chromium 69+, Edge 79+, Firefox 96+ ou Safari 15.4+. AstroPilot s’ouvre
dans le navigateur par défaut et vérifie cette capacité à l’usage ; un navigateur
plus ancien, un mode de sécurité qui désactive Web Locks ou un contexte qui la
refuse peut consulter l’application, mais la saisie et la publication terrain
sont bloquées avec un diagnostic visible. Le repli `localStorage` n’est pas
présenté comme une exclusion multi-onglets sûre.


Chaque phase réseau de publication (GET de retry, POST et GET de confirmation)
est limitée à 15 secondes (`FIELD_OBSERVATION_NETWORK_TIMEOUT_MS`), décodage de
réponse compris. Le contrôleur réseau est lié à l’annulation de l’opération ;
une échéance libère le Web Lock même si le transport ne répond pas à l’abort.
Le pending et le verrou d’origine restent conservés en cas de statut incertain.
La prochaine tentative commence par le GET canonique du même UUID.

Un agrégat dont une entrée manque ou diverge devient `inconsistent_persistence` :
le verrou global original reste intact et ses artefacts sont affichés avec
l’inventaire courant. Les actions ciblent un identifiant déterministe composé de
la source, clé, génération, UUID et contenu complet immuable (valeur brute pour
une corruption). Cet identifiant est revalidé sous Web Lock avant tout GET ou
suppression. Résoudre un artefact global ne supprime jamais son voisin divergent
portant la même clé ; les autres artefacts globaux sont conservés.

Chaque ré-inventorisation fusionne les artefacts persistants avec les artefacts
mémoire non résolus, y compris après `clear()` et un retour bfcache. Un artefact
absent reste diagnostiqué et bloquant jusqu’à résolution ciblée explicite ou
réconciliation canonique ; il n’est pas réécrit automatiquement dans le stockage.
Le journal typé IndexedDB `fieldObservationRecovery` conserve séparément les
artefacts non résolus (identité complète, UUID, pending canonique, contexte,
origine, clé, génération, statut/raison et dates de création/mise à jour).
Il survit à `localStorage.clear()` et à un rechargement complet : le démarrage
fusionne ce journal avec l’inventaire local avant d’autoriser un nouvel UUID.
Les lectures et transactions atomiques sont sérialisées sous le même Web Lock ;
la transaction de sauvegarde doit être terminée avant toute publication.
Un journal inaccessible, bloqué ou corrompu bloque toute publication, sans repli
vers la seule mémoire. Chaque résolution explicite retire son entrée du journal ;
des identités résolues empêchent une page ancienne de la réintroduire.
L’actualisation canonique lit le contexte sans mutation intermédiaire de l’UI,
puis revalide le token et la génération avant de repasser le verrou en pending.
Chaque requête de récupération (observation, mission, session et décision) utilise
la même limite de 15 secondes, décodage compris, et le signal de l’opération.
Un timeout `context_refresh_timeout` libère busy et conserve le pending.
Les erreurs IndexedDB sont classées `recovery_unavailable`, `recovery_schema`,
`recovery_transaction` ou `recovery_corrupt`, avec leur cause native si disponible.

Limite explicite : les tombstones ne sont pas compactés, car les pages anciennes
ne disposent pas d’un protocole d’epoch durable permettant une éviction sûre.
Le document sérialisé est plafonné à 512 Ki unités UTF-16 (au plus 1 Mio en UTF-16).
Un dépassement `recovery_quota` bloque toute nouvelle mutation/publication avant
écriture et conserve le journal précédent ; aucune identité résolue n’est évincée.
Cette garde borne la croissance persistée mais peut nécessiter une récupération
assistée après un grand nombre de résolutions ; ce n’est pas une compaction.

Ce stockage est propre à l’origine navigateur ; effacer aussi IndexedDB ou toutes
les données du site supprime cette preuve locale de récupération.

Les diagnostics de migration (`migration_failed`, `migration_requires_web_locks`)
s’ajoutent à cet inventaire fusionné : les entrées et corruptions mémoire restent
présentes même lorsqu’un autre pending legacy ne peut pas être migré.
La résolution mémoire cible chaque artefact indépendamment du statut global.
Sous Web Lock, elle exige son identité mémoire exacte, l’absence persistante de
sa clé et l’absence de remplacement divergent dans la persistance actuelle.
Un voisin historique uniquement mémoire de même clé et même origine ne bloque
pas la résolution : chaque `entry_id` distinct est résolu indépendamment.
La réconciliation vérifie le GET canonique du même UUID, puis revalide la cible avant son retrait ; l’abandon ou
la suppression d’une corruption exige une confirmation explicite. Seule la cible
est oubliée, puis l’inventaire restant est reconstruit (0/1/N), sans retirer les
autres pending. Un brut réapparu ou remplacé impose une ré-inventorisation bloquante.
Un `clear()` sans artefact dans la mémoire ni la persistance laisse l’éditeur libre.
Un verrou global illisible est une corruption distincte (`global_lock`, brut et
identifiant immuable), affichée à côté des pending valides. Sa suppression confirmée
revalide exactement le brut sous Web Lock et ne supprime aucun pending valide.

Le harness multi-contexte est un simulateur contrôlé de globals JavaScript
séparés, pas un navigateur réel. Les stockages localStorage et IndexedDB sont
distincts ; un vrai reload du test crée un nouveau contexte JS et conserve
uniquement ces stockages. La file Web Locks est indépendante de la file
d’événements `storage`. Les écritures identiques ne produisent aucun événement ; la livraison se fait dans une tâche ultérieure et
peut être retardée, dupliquée ou réordonnée. Les échéances réseau sont déclenchées
explicitement dans les scénarios suspendus, sans réduire la constante de production.

Start the API and bundled UI after synchronizing the runtime environment:

```bash
uv run --locked --no-sync astropilot-app
```

AstroPilot starts locally at <http://127.0.0.1:8000/> and opens that address
in the default browser. A second launch detects the existing AstroPilot
instance and reopens it. In the packaged macOS application, clicking the Dock
icon while the server is already running is handled by the native Cocoa reopen
event and opens the same local address without starting another server. The
macOS packaging extra includes PyObjC solely for this application event loop.
If another application is using port 8000,
AstroPilot stops without changing ports or terminating that application.

Launcher diagnostics are stored in `~/Library/Logs/AstroPilot/AstroPilot.log`.
Provide this log when reporting a startup problem.

## Local macOS application build

Create the isolated packaging environment and build the Apple Silicon app:

```bash
UV_PROJECT_ENVIRONMENT=.venv-packaging uv sync --locked --extra packaging
.venv-packaging/bin/python scripts/build_macos.py
```

The application bundle is written to `dist/AstroPilot.app`.

For a Developer ID release build, first store notarization credentials in the
login keychain with Apple's interactive tool (never put credentials in this
repository):

```bash
xcrun notarytool store-credentials "astropilot-notary"
```

Then run the release workflow with an existing Developer ID Application
identity and that keychain profile:

```bash
ASTROPILOT_CODESIGN_IDENTITY="Developer ID Application: Name (TEAMID)" \
  .venv-packaging/bin/python scripts/release_macos.py \
  --notary-profile "astropilot-notary"
```

The workflow verifies the signature, notarizes and staples the app, checks it
with Gatekeeper, and writes the versioned ZIP and SHA-256 sidecar under `dist/`.

The final release ZIP excludes AppleDouble (`._*`) and `__MACOSX` entries.
The workflow extracts that ZIP and rechecks the extracted application signature,
stapling, and Gatekeeper before generating its SHA-256 sidecar. These pipeline
checks are complemented by the passed native beta.3 clean-machine test.
