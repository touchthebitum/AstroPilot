# Conserver la cible explicitement choisie

Le parcours découverte préremplissait le nouveau projet, puis l’analyse météo
reclassait l’ensemble du portefeuille. Une autre cible pouvait ainsi remplacer
le choix de l’utilisateur sans action explicite de sa part.

Le choix d’une vignette, l’ajout d’un projet et le bouton « Préparer une séance »
d’un projet transmettent désormais son identifiant exact à l’analyse. Un rappel
visible précise la cible évaluée. Rechercher explicitement une nouvelle cible
libère ce choix. Ce contexte appartient au parcours ouvert ; il ne modifie ni
le portefeuille enregistré, ni l’avancement, ni les réglages personnels.

`POST /v1/tonight` accepte `selected_project_id`, facultatif. Un projet absent
est refusé avant l’accès météo (422). Sans ce champ, la comparaison générale
reste disponible. Avec ce champ, seuls ses candidats et ses évaluations peuvent
alimenter la recommandation et le contexte durable d’acceptation. Les autres
projets restent présents dans le profil et leurs crédits sont conservés.

Les règles météo, de disponibilité, de filtre et de faisabilité restent
inchangées. Une cible devenue inexploitable n’est pas remplacée : le refus
explique que le choix est conservé et indique comment chercher une alternative.
Les autres cibles ne peuvent pas être acceptées en changeant simplement la
source de sélection dans une requête.

Validation : scénario réel de calcul sur météo synthétique d’hiver, avec M42 et
North America enregistrés simultanément. La comparaison générale choisit North
America ; la requête ciblée conserve M42, jusqu’à l’acceptation explicite. Un
ciel couvert refuse la séance sans substitution. Les tests exécutent aussi les
gestionnaires JavaScript de choix, d’ajout, de préparation et d’envoi, ainsi que
les protections contre les réponses tardives. Aucun essai photographique réel
n’est revendiqué.
