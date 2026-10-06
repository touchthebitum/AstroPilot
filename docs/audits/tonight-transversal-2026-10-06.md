# Audit transversal Tonight — 6 octobre 2026

## Baseline et périmètre

Dépôt actif : `/Users/cabinetdosteopathiefranckperruchoud/Documents/Codex/2026-08-23/referenced-chatgpt-conversation-this-is-an/AstroPilot`.
Remote : `https://github.com/touchthebitum/AstroPilot.git`.
Avant synchronisation : branche main ; HEAD = main = origin/main local =
`c6c41771045ef39b2c5fb7321142ef5ca3d51d75`.
GitHub confirme #316 mergée le 2026-10-06 à 16:45:40 UTC (18:45:40 Zurich),
commit `958c46eca87e5233f784bce27d8cf8272cee251f`.
Après fetch et fast-forward : HEAD = main = origin/main = ce commit.
Aucune modification suivie ; deux éléments non suivis préexistants :
`.DS_Store`, `astropilot.egg-info/`. Le working tree n'est donc pas entièrement
vide, mais les fichiers suivis sont propres.
Stash critique avant/après : `stash@{0}`, SHA
`223ec1f5904131d726b694655f137670c0ddeb0b`,
`On refactor-project-completion-estimator: safety backup: superseded project completion estimator work`.
Aucune commande pop/apply/drop et aucune écriture sur ce stash.

Travail dans une copie locale isolée à partir du nouveau main, sous le dossier
`work/AstroPilot` de ce chat, branche `fix/tonight-mission-provenance`.
Field Lab exclu des changements. Aucun merge automatique.

## Carte des frontières et sources de vérité

| Concept / frontière | Autorité et transformation | Validation / persistance / limite |
| --- | --- | --- |
| Project / état global | Profil projects ; project_state dérive progress et remaining de hours/target_hours | None projet absent ; cible <=0 donne remaining=0 ; le legacy reste encore le plafond de MissionInput |
| Progrès moderne | acquisition_intent_targets + acquisition_intent_progress validés + crédits identifiés ; derive_acquisition_intent_remaining_progress | Progress absent reste inconnu ; pas d'assimilation des heures globales à une intention ; complétion retire les intents terminés |
| CelestialObject / ImagingField / Project | Définitions production distinctes ; project.imaging_field_id est une référence explicite | Résolveurs vérifient composants et intents ; aucune inférence du field depuis le nom de catalogue |
| Candidate | ProjectSelectionEngine transporte field, sélection, assessments et progrès ; provenance project/discovery | Candidate vérifie cohérence selected/viable/status/assessments ; scores et priorité restent distincts |
| AcquisitionIntent | Définition au sein de son ImagingField ; autorité du filter_type | Appartenance, cible projet, capacité setup, actionability et météo contrôlées ; pas de préférence inventée en cas d'ambiguïté |
| FilterOpticalProfile | Références explicites du setup, résolveur typé | RESOLVED / UNAVAILABLE / AMBIGUOUS ; aucune identité déduite de la largeur de bande SelectedFilter |
| SelectedFilter | Inventaire matériel ; réconciliation explicite sur type requis par l'intent | Compatible conservé exactement, sinon matériel compatible, sinon None ; mismatch rejeté à assemblage, acceptation et nouvelle écriture |
| Preuve météo | Snapshot fournisseur + fraîcheur + localisation ; météo de fenêtre dérivée des lignes horaires | Couverture temporelle et trust évalués ; DecisionForecastEvidence persiste points, unités, fournisseur, lieux, instants |
| Preuve lunaire | IntentNightEvidenceBuilder : géométrie du field, site, fenêtre actionable ; temps de référence au milieu | LunarContaminationEstimator + profile puis comparaison ; preuve et profile exacts restent locaux à composition et sont perdus après sélection |
| Productivité / actionability | ProductiveWindowAssessment, timeline à pas de 15 min ; session_availability_windowing choisit un seul intervalle | >=60 min continues ; bornes UTC, min(plafond mission, disponibilité), aucune addition de fenêtres ; preuve absente => insufficient_evidence |
| Sélection | Pareto des préférences précomputées ; UserSelection valide le choix autorisé | Pas de départage arbitraire ; IDs field/intent et tri lexical sans sens de préférence ; source sélection distincte de status |
| MissionInput | build_mission_input dérive durée globale, gain, météo et pénalité lunaire normalisée /35 ; transporte intent/field/filter | Refait depuis evaluation au preview et à l'acceptation ; progrès moderne non utilisé pour plafond/gain |
| MissionAssembler / NightMission | Recalcule assessment, sélectionne intervalle sous disponibilité, prorate gain puis transporte identité | Gate de cohérence sur temps, productivité et gain ; identité/provenance validée ; productivité transportée décrit la nuit analysée, pas seulement la durée mission |
| Persistance | Acceptance lineage v9 ; aggregate decision/selection/mission ; writes valident filtre et identité | Lectures v1–v9 compatibles, notamment anciennes contradictions non réparées ; aucune nouvelle garantie hardware pour legacy |
| API / UI | TonightResponse et modèles API ; accepted mission issue de NightMission persistée | Correctif : source du filtre et ID intent acceptée recopiés ; UI distingue type requis et matériel renseigné ; wording inchangé |

## Invariants vérifiés

- Intention autoritaire pour le type ; Ha/OIII symétriques ; métadonnées compatibles
  et source conservées ; pas de filtre fictif si inventaire absent.
- Project, champ et objet céleste distincts ; références explicites et appartenance
  de l'intent validées ; discovery ne récupère pas un field projet artificiel.
- Selected / viable / status / raisons d'éligibilité cohérents ; inconnu,
  non-éligible et absence de préférence restent distincts.
- Profile optique absent ou ambigu : exclusion de l'éligibilité, sans choix arbitraire.
- Préférence lunaire compare les indices avec profile explicite ; un seul intent
  éligible n'a pas besoin d'une comparaison lunaire et ne prouve pas une comparaison.
- Une seule fenêtre réelle >=60 min, intersections utilisateur et plafond global ;
  fenêtres disjointes non additionnées ; calcul en temps écoulé UTC, y compris DST.
- Gain nul sans fenêtre ; proration après restriction ; aucun accroissement lorsque
  durée finale dépasse la référence productive du gain.
- Confiance recommandation, confiance mission, complétude AQI, fraction productive,
  trust météo, statut cible et priorité séparés dans le transport. L'alias legacy
  productivity.confidence désigne la fraction productive et est déprécié dans API.
- Identités decision/selection/mission/field/intent contrôlées à acceptation et
  persistance ; lectures historiques fidèles ; writes contradictoires rejetés.
- Les réponses preview et mission acceptée exposent maintenant la même source
  exacte du matériel. Les anciens champs absents restent None ; aucun nouveau
  score, status ou niveau de garantie n'est déduit.

Ce sont les invariants vérifiés dans les suites citées et le code examiné ; cela
ne constitue pas une preuve exhaustive de tous les jeux de données réels.

## Findings confirmés

### F1 — P1 : état moderne et plafond legacy restent deux autorités concurrentes

Preuve : `astro_score.evaluate_object` calcule remaining_hours via
`project_remaining_hours`, `build_mission_input` s'en sert pour le plafond et
`session_portfolio_gain` reste global. En parallèle, recommend_project_for_night
ne rejette plus la complétion globale lorsque project_targets existe ; il dérive
la complétion par intention. Le reste de cette intention ne rejoint pas MissionInput.

Reproduction déterministe ajoutée à test_mission_assembler_invariants : cible Ha
2h, progrès manuel 5400s => reste Ha 0.5h ; fenêtre de nuit 2h et fenêtre productive
continue simulée 1.5h. Avec reste global 4h : mission 1.5h. Avec reste global 0h :
aucune mission, bien que l'intent ne soit pas terminé. Aucun mauvais type de filtre
n'est nécessaire à cette divergence. L'assemblage et le builder d'input sont réels ;
les moteurs secondaires sont isolés par la fixture existante.

Surface : projet moderne -> evaluation -> eligibility/actionability -> mission/gain.
Le refus dépendant d'un état global legacy est confirmé ; la règle exacte de
plafond par intent doit être formalisée avant correction. La suracquisition de
l'intent est confirmée numériquement, mais son traitement métier (arrêt à la cible,
minimum 60 min, choix d'un autre intent) demande une décision de contrat.

Non corrigé : changement de source de vérité et propagation transversale.
Incrément recommandé : définir un état/capacité projet autoritaire pour projets
modernes, garder la lecture legacy, transporter un plafond explicite identifié,
valider actionability après ce plafond et recalculer le gain sur la même base.
Ne pas remplacer un reste inconnu par zéro ni par une capacité illimitée.

### F2 — P2 : preuve exacte de la préférence lunaire perdue après composition

Preuve : resolved_profile_ids, IntentNightEvidence et estimates sont des variables
locales de compose_acquisition_intent_selection. AcquisitionIntentSelection puis
Candidate ne transportent que IDs/status/raisons d'éligibilité et la sélection.
MissionInput et NightMission n'ont pas ces preuves ; la persistence forecast
est météo et ne les remplace pas.

Test ajouté : deux jeux d'estimates réels avec indices multipliés par deux
conduisent à des sélections strictement égales. Une explication identique ne permet
pas de retrouver les indices ni le profile exact utilisés. Cela n'établit pas que
le vainqueur est faux ; cela confirme une perte de traçabilité/reproductibilité.

Surface : composition -> candidate -> acceptance lineage -> API/UI historique.
Non corrigé : nécessite snapshot de preuve versionné (profile, géométrie, fenêtre,
référence, algorithme, indices), transport et migration de lecture. Pour legacy,
absence de preuve doit rester explicite ; pas de recalcul a posteriori présenté
comme preuve historique.

### F3 — P2 : acquisition_intent_id omis de la mission acceptée publique

NightMission contient et persiste l'ID ; AcceptedMissionResponse et son adaptateur
l'omettaient. La sélection externe pouvait encore l'exposer, mais la mission seule
perdait son identité acquisition. Test de transport reproduit avant correction.

Corrigé localement : champ optionnel + copie exacte depuis la mission ; legacy None.
Surface : acceptation, lecture mission courante, clients/UI recevant la mission.

### F4 — P2 : source du SelectedFilter perdue à la frontière API

Le domaine et la persistance conservent source (notamment user_default), mais
TonightFilterResponse, TonightFilterModel et AcceptedMissionFilterResponse
ne la transportaient pas. Trois sources distinctes donnaient la même réponse.

Corrigé localement : champ source optionnel dans les trois modèles et copie exacte
aux deux adaptateurs. Aucun défaut « selection » inventé par le transport pour
les anciens payloads. Les tests font maintenant persistence -> domaine -> DTO ->
modèle public, ainsi que mission acceptée, avec conservation de toutes métadonnées.
L'UI n'affiche pas encore cette source ; le correctif la rend disponible sans
changer son wording ni promettre une vérification physique.

Aucun P0 confirmé. Pas de P3 distinct nécessaire.

## Risques et limites — non assimilés à des bugs de production prouvés

- ProductiveWindowAssessment et MissionAssembler substituent notamment 20% nuages,
  60% humidité, 5 km/h vent, seeing 1.5, moon_penalty 0.2 et 6h si les entrées
  correspondantes sont absentes. NightConditionsProvider prolonge la dernière
  valeur si un tableau est court. Ces chemins sont observables dans le code,
  mais les validations ingress/couverture peuvent empêcher l'accès depuis Tonight.
  Pas de reproduction HTTP d'une amélioration artificielle établie ici.
- L'actionability est recalculée pour assessment, sélection et assemblage ; le
  sélecteur de fenêtre est commun, donc aucune divergence numérique générale n'est
  démontrée. Un snapshot partagé réduirait néanmoins le risque de dérive ultérieure.
- La fenêtre lunaire de comparaison est déterminée avant assemblage. Il faut couvrir
  un déplacement de fenêtre dû à un plafond moderne ou à une future évaluation
  spécifique au filtre ; ce risque est renforcé par F1/F2, pas un bug supplémentaire
  prouvé dans le comportement actuellement couvert.
- Gain attendu : le code utilise des heures productives pondérées puis une proration
  sur la durée finale. Les tests existants verrouillent une limite de gain conservatrice.
  Ne pas modifier cette sémantique sans préciser si « gain » signifie heures murales
  ou équivalent productif ; aucune surestimation reproduite dans cet audit.
- productivité/fenêtres API décrivent la nuit analysée ; recommended_hours décrit la
  mission finale. Ne pas présenter le premier comme la durée de mission.

## Tests et correction limitée

Nouveaux cas : 4 tests provenance (3 sources + legacy), 2 cas de caractère global /
reste intent, 1 cas perte des estimates lunaires. Total : 7 nouveaux cas.
Les deux tests de caractérisation documentent l'état actuel de F1/F2 ; ils ne
constituent pas le contrat désiré ni un correctif pour ces findings.

Avant correction API : 4/4 tests provenance échouaient (source absente / ID absent).
Après correction : 233 tests réponse/API/provenance passent ; 52 tests ciblés
assemblage/composition/provenance passent. Tests complémentaires après ajout du
round-trip persistence et amélioration de la preuve F2 : 17 passent.

Suite élargie finale : **3829 passed in 16.66s**, aucun échec, aucun skip.
Périmètre : tests/architecture, tests/services, tests/models, Tonight API/E2E/UI,
test_intent_choice_ui. Node disponible et loopback autorisé.
Premier passage : 3808 passent, 20 skips, 1 échec bind loopback PermissionError.
Les skips incluaient le moteur JavaScript absent du PATH ; relance avec Node fourni
et permission sockets locales. Aucun accès réseau externe autorisé par les tests.

`git diff --check` vérifié. Seuls deux fichiers de production sont modifiés :
`astropilot/app.py`, `decision/services/tonight_response.py`, avec ajouts de transport.
Autres modifications : tests et ce rapport. Aucun fichier Field Lab modifié.

## Prochaine priorité

F1 en premier : unifier la capacité/progression moderne jusqu'à la durée finale et
au gain, avec cas global terminé mais intent incomplet, intent <60 min, état
inconnu, plusieurs intents et disponibilité utilisateur. F2 ensuite pour conserver
la preuve utilisée. Puis audit des fallbacks/fail-closed : inventaire par champ,
classification REJECT / DEGRADE / NEUTRAL_DEFAULT / USER_DEFAULT, tests de
reachability depuis API, interdiction des défauts favorables non autorisés.
