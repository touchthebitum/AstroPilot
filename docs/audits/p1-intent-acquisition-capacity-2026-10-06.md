# P1 — capacité d'acquisition et gain Tonight par intent

## Baseline et périmètre

PR #317 mergée le 6 octobre 2026 à 16:58:23 UTC.
Baseline `main == origin/main == d76e5139c543340c2b8ebaca7fea6aeeb3e85633`.
Checkout d'audit propre avant modification. Le dépôt principal portant le stash
est également avancé en fast-forward sur cette baseline ; ses seuls éléments
non suivis restent `.DS_Store` et `astropilot.egg-info/`.
Stash critique observé avant et après :
`223ec1f5904131d726b694655f137670c0ddeb0b`. Aucun pop/apply/drop.

Field Lab, UI, persistance et preuve lunaire F2 hors périmètre du diff.

## Cause racine et carte des sources

| Source / frontière | Avant | Contrat après correction |
| --- | --- | --- |
| `project_state` / `project_remaining_hours` | Reste global `target_hours - hours`, arrondi à 0,1 h | Fonction historique inchangée ; lecture et fallback pour projets sans targets modernes |
| `acquisition_intent_targets` | Cibles explicites validées contre l'imaging field | Autorité de la cible de chaque intent ; cible sans identité valide rejetée |
| `acquisition_intent_progress` | Source complète frames/exposition ou durée manuelle, validée | Absence = inconnue ; source partielle/malformée rejetée, jamais remplacée par le global |
| Crédits d'exécution identifiés | Ledger validé, durée en microsecondes par projet/intent | Même lecture via `credit_totals`, ajout une fois par `derive_acquisition_intent_remaining_progress` ; aucune écriture |
| `derive_acquisition_intent_remaining_progress` | Dérivait déjà cible, acquis, reste et complétion | Unique dérivation de la capacité moderne, sans nouvelle formule concurrente |
| `evaluate_object` | Transport du `remaining_hours` historique | Transport historique inchangé ; ce champ n'autorise plus la capacité d'un projet moderne dans `build_mission_input` |
| Préselection dans `recommend_project_for_night` | Fenêtre évaluée avec plafond global legacy | Fenêtre physique via input `evidence_only`, interdite à l'assembleur ; éligibilité plafonnée individuellement au reste intent |
| ROI / marginalité / fermeture / opportunité future Tonight | Globals legacy | Progression/capacité du seul intent choisi ; inconnue = pas de bonus de progression et pas de fallback du moteur futur |
| `session_portfolio_gain` | Gain basé sur reste et cible global legacy | Fonction historique inchangée ; le chemin moderne utilise `acquisition_intent_session_gain` |
| `MissionInput` | Durée/gain global ; identité intent sans capacité | `acquisition_capacity: AcquisitionIntentRemainingProgress`, identité vérifiée et durée <= reste connu |
| `CandidateAssessment.build` | Réévaluation shortlist sans intent choisi | Transporte l'identité choisie de son propre candidat, sans mutation de l'évaluation historique |
| `ProductiveWindowAssessment` / assembleur | Proratisation d'un gain global | Transporte la même capacité ; sélection continue existante ; gain calculé sur la durée finale et cette cible |

Exemple initial : cible Ha 2 h, acquis 1,5 h, reste 0,5 h. Le global à 4 h
permettait une mission de 1,5 h ; le global à zéro empêchait aussi une mission
quand le reste intent aurait été exploitable. La complétion moderne et la
capacité finale utilisaient donc deux autorités incompatibles.

## Contrat retenu

Projet moderne dans ce chemin : imaging field explicitement résolu et targets
intent non vides validés. Imaging field seul / targets vides : fallback legacy
conservé. Aucun choix d'intent n'est inventé.

- Cible et progrès explicites connus : reste du seul intent sélectionné autoritaire.
- Mission finale >= 60 minutes continues, <= une fenêtre productive, <= disponibilité
  utilisateur et <= reste intent. Aucune addition de fenêtres disjointes.
- Reste connu < 60 minutes : intent non éligible ; la sélection existante peut
  retenir un autre intent déjà éligible. Sinon aucune mission. Intent terminé : refus.
- Progrès absent : `remaining_hours is None` conservé ; gap
  `intent_progress_evidence_insufficient`, pas de sélection de cet intent et aucune
  mission autorisée. Les zéros de durée/gain de l'input sont un refus opérationnel,
  pas une conversion du progrès en zéro. Une source partielle invalide reste une erreur.
- Gain moderne en points de pourcentage de la cible de l'intent :
  `100 * min(durée_finale, reste_intent) / cible_intent`.
  Même fonction pour l'input, le ROI et l'assemblage final ; aucun gain legacy ajouté.
  La présentation numérique du gain reste arrondie à deux décimales.
- La durée moderne finale conserve la précision réelle de la fenêtre ; pas d'arrondi
  à deux décimales susceptible de dépasser un reste ou une disponibilité fractionnaire.
- Inconnu dans le calcul futur : résultat `INCONNU`, pas de provider legacy ni de
  capacité par défaut de 10 h. Ses compteurs neutres ne représentent pas le progrès.
- Lectures/persistances historiques, valeurs globales stockées et ledger inchangés.

## Architecture et cohérence finale

Réutilisation du modèle typé existant `AcquisitionIntentRemainingProgress` plutôt
qu'un nouveau champ global détourné. `MissionInput.acquisition_capacity` est un
snapshot dérivé, identifié par l'intent ; l'imaging field est transporté dans
l'input existant. L'assembleur conserve ce snapshot via l'assessment et calcule
le gain à partir de sa durée finale réelle.

La préselection utilise la fenêtre physique car aucun intent n'est encore choisi.
Chaque intent reçoit ensuite son propre plafond pour l'actionability. L'input
physique est marqué `evidence_only` et l'assembleur le refuse explicitement.
Le chemin final recalcule le snapshot à partir du profil effectif validé, avec
la même dérivation que la sélection. Ni le global ni un autre intent ne le modifient.

La shortlist et l'acceptation utilisateur continuent à transporter le choix
explicite ; aucune modification d'UI, de choix Pareto, de preuve lunaire ou de
mécanisme multi-intent. Le patch ne change aucun lecteur/saver historique.

## Tests et limites

Les tests de contrat ont précédé l'implémentation : 11 échecs / 1 succès au premier
passage, dont suracquisition du reste 0,5 h et défaut de traitement du progrès partiel.

Couverture ajoutée/renforcée : global zéro et élevé, reste sous une heure et terminé,
absence/partialité de progrès, intent choisi parmi plusieurs, intent non choisi
inconnu, gain sur durée finale, disponibilité utilisateur, fenêtres disjointes,
durées fractionnaires, crédits identifiés, garde d'identité, préselection non
assemblable, invariance du score moderne face au global, absence de fallback futur,
transport shortlist, composition HTTP Tonight et assemblage réel.

Les fixtures d'éligibilité déclarent maintenant un progrès connu quand elles testent
les autres gates. La caractérisation P1 de #317 devient un contrat corrigé ;
la caractérisation F2 reste inchangée dans son résultat.

Limites assumées : un reste sous une heure ne peut être achevé par une nouvelle
mission Tonight avec le minimum actuel ; pas de multi-intent ni de suracquisition.
Un projet moderne sans progrès connu doit recevoir une source explicite (y compris
zéro explicite si c'est réellement l'état connu) ou les crédits identifiés acceptés
par la dérivation existante. Le classement moderne peut changer : les bonus legacy
contradictoires ne s'appliquent plus. Le gain est relatif à l'intent sélectionné,
pas à une somme de cibles d'intents. Les diagnostics modernes connus/inconnus ne
créent aucune nouvelle écriture persistée.

Validation finale : **166 tests ciblés passent en 1,43 s** ; **4653 tests élargis
passent en 29,11 s**, aucun échec ni skip. Suite élargie : architecture, services,
models, history, API Tonight/E2E, UI Tonight/intent choice, API project progress et
execution session. Node présent ; tests loopback exécutés. `git diff --check` propre.
Contrôle de périmètre : sept fichiers de production (scoring, mission, modèle
eligibility, gain, eligibility service, candidate assessment), sept fichiers de
tests et ce rapport ; aucun fichier Field Lab/UI/saver modifié.

Recommandation : fusion après checks CI verts sur le SHA de cette PR ; pas de
merge automatique. Le classement moderne différent et le refus des intents
inconnus/sous une heure sont les comportements contractuels attendus.
