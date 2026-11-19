# Parcours débutant — intégration privée

Quatre étapes stables : Préparer, Choisir, Photographier, Ajouter. Les présentations sont nommées Débutant et Avancé ; les valeurs internes simple/pro restent compatibles.

Le module beginner.js adapte la présentation et réutilise les commandes existantes : recherche, sélection explicite du projet, fermeture de séance et ajout des photos. Il ne crée aucune écriture ni règle scientifique parallèle. Les champs de confirmation des filtres restent explicites. Une séance terminée peut être transmise explicitement à l’ajout de photos, après filtrage par projet ; aucune sélection implicite parmi plusieurs séances.

Les aides sont accessibles au survol, au clavier et au toucher. La consultation Mon suivi réutilise les écrans de lecture existants. Les éléments détaillés restent accessibles en Avancé. Le guide représente l’étape courante, sans prétendre enregistrer un nouvel état de progression.

Validation : tests photo/session/crédit existants ; tests navigateur beginner_conductor_browser.cjs et beginner_session_browser.cjs sur serveur local avec profil fictif, sans prévision météo ni matériel réel. Le redémarrage est un arrêt/relancement du serveur, puis relecture sans nouvel ajout. Le kit doit encore être validé sous Windows ; aucune publication autorisée.

Corrections après essai utilisateur du 3 novembre : une seule liste sélectionne soit le projet, soit l’aide au choix ; aucune seconde validation « Continuer mon projet ». Le conteneur Historique complet est masqué en Débutant, conservé en Avancé. Les séances ayant la même date affichée et le même filtre reçoivent un numéro stable dans ce groupe, et le crédit déjà compté apparaît avec sa durée. Les identifiants d’exécution et les données ne sont ni fusionnés ni modifiés par cette distinction. Les scénarios fictifs successifs de démonstration utilisent des horaires différents ; un test dédié vérifie néanmoins la collision exacte.
