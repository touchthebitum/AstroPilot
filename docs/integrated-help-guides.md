# Documentation intégrée NightMerit — premier lot

Baseline vérifiée : `main == origin/main == 7228a582fb198b718b9d30c8ba328335c8f8aa4f`.
Audit initial en lecture seule : le header propose la présentation et les actions de configuration/disponibilité ; les dialogues mission, observation et historique sont internes. Aucun point d’entrée d’aide global existant. Choix : bouton Aide dans le header et dialogue natif partagé, sans navigation externe.

## Contenu et maintenance

`astropilot/web/help.js` centralise les trois guides et leur contrôleur indépendant de l’état métier. Le fichier est distribué par la configuration existante `web/*` et servi par `/ui/`, avec le même jeton de version que les autres assets.

- Bien démarrer : première nuit, lecture de la recommandation, abstention, retour terrain, présentation. Lecture de 2–3 minutes, sans vocabulaire technique de stockage.
- Comprendre NightMerit : fiabilité, distinction prévision/décision/réalité, contexte, risques nuancés, validation sans recalibrage automatique, limites.
- Guide complet : 13 rubriques, sommaire navigable, premiers repères pratiques et glossaire. Les procédures détaillées par système et les cas avancés restent à enrichir après validation produit.

Les identifiants de section sont stables, préfixés par `help-{guide}-{section}`. Une future aide contextuelle peut appeler `window.nightmeritHelp.open("understand", "reliability")`. Conserver ces identifiants lors des enrichissements.

## Présentation et accessibilité

Simple privilégie Bien démarrer sur une ligne entière ; Comprendre reste visible et Guide complet utilise un accès secondaire plus discret. Pro affiche les trois boutons au même niveau. Un seul contenu source ; aucun changement du moteur scientifique.

Le dialogue conserve le guide et son défilement à la fermeture et lors des changements de mode. Le sélecteur interne utilise le sélecteur global existant et sa persistance. Le contenu dispose de son propre scroll, d’un sommaire et de sections pouvant recevoir le focus. Titre accessible, focus initial sur Fermer l’aide, boucle Tab/Shift+Tab, Escape natif et retour du focus au bouton Aide.

## Validation reproductible

- Tests ciblés et harness Node : `tests/api/test_integrated_help_ui.py`, avec les tests existants Tonight, site, onboarding, Simple/Pro, observations et historique (PR306–309).
- Smoke navigateur : `python tests/browser/integrated_help_smoke.py` avec Playwright et Chrome installé. `NIGHTMERIT_BROWSER_EXECUTABLE` permet de choisir un autre navigateur compatible. Les API sont simulées en erreur ; les vrais fichiers UI et des états préremplis sont utilisés.
- Le smoke couvre 390/1280, ouverture/fermeture, modes, sections, scroll, focus/clavier, invariance métier et absence d’overflow. Il ne constitue pas une nouvelle validation scientifique ou météo.
- Syntaxe des deux fichiers JS et `git diff --check`.
