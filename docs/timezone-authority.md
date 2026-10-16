# Autorité des fuseaux

Le paquet `tzdata` verrouillé dans `uv.lock` est la source commune de règles IANA.
Il est une dépendance d’exécution, même sur macOS. À l’import initial de `decision`,
le chemin système de `zoneinfo` est désactivé et son cache préexistant est vidé une fois.
Les objets `ZoneInfo` restent ceux de la bibliothèque standard ; aucune base du système
ou du navigateur ne décide des conversions du site.

`/ui/timezone-data.js` transmet les transitions TZif du même paquet, avec les règles
POSIX de fin de fichier pour les années futures. L’adaptateur de l’interface calcule
les décalages avec ces données ; `Intl` en UTC sert uniquement au formatage linguistique.
Les liens IANA partageant un fichier sont dédupliqués. Les formats non pris en charge
échouent explicitement. Les missions existantes conservent leurs instants et leur fuseau
historique ; ce changement ne migre ni ne réécrit aucun enregistrement.

L’empreinte du contenu accompagne chaque appel `/v1/` de l’interface. Le serveur refuse
une empreinte différente avant d’exécuter le traitement. Une écriture de navigateur
(Origin présent, hors renouvellement Guardian) doit présenter cette empreinte. Les
clients sans Origin gardent leur contrat API. Une page périmée ou privée de son jeu de
règles demande un rechargement ; aucun repli sur les règles locales n’est autorisé.
Ce mécanisme évite qu’une page restée ouverte travaille après un changement de paquet.

La PR conserve tzdata 2026.3 de main. La montée à 2026.5 reste dans #260. La qualification
intégrée doit prouver séparément les deux versions : Winnipeg le 2 novembre 2026 à
12:00 UTC vaut 06:00 (UTC−6) avec 2026.3 et 07:00 (UTC−5) avec 2026.5 ; Zurich reste
indépendante de cette modification. Une version plus récente ne doit pas réintroduire
une divergence entre Python et l’interface.

Les tests comparent chaque fichier TZif distinct de la distribution à Python avant,
pendant et après toutes ses transitions, puis à des dates futures jusqu’en 9998.
Ils vérifient aussi Winnipeg, Zurich, les heures ambiguës/inexistantes, les écritures
périmées et l’indisponibilité des règles. La matrice native Windows/Mac les exécute en
répertoires temporaires, avec les parcours navigateur existants Hα/OIII et changement
de site. Les tests UI extraits chargent les mêmes données et le même adaptateur ; Node
les reçoit via stdin pour éviter la limite de commande Windows.
