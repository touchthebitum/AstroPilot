AstroPilot Architecture
Vision
AstroPilot est un assistant décisionnel destiné aux astrophotographes.

Sa mission est d'optimiser simultanément :

le ciel disponible,
le temps de l'utilisateur,
son matériel,
et son portefeuille de projets.
Chaque nuit claire est une ressource rare.

AstroPilot existe pour aider l'utilisateur à en tirer le meilleur parti.

AstroPilot ne répond pas à la question :

Quel objet est observable ?

Il répond à la question :

Quelle est la meilleure décision à prendre ce soir avec mon matériel afin de maximiser mon rendement astrophotographique ?

AstroPilot ne cherche pas à remplacer l'astrophotographe.

Il cherche à lui permettre de prendre de meilleures décisions, plus rapidement et avec davantage de confiance.

Les cinq moteurs
🌌 Sky Engine
Détermine ce que permet réellement le ciel.

Entrées :

météo
seeing
transparence
vent
humidité
lune
SQM
Bortle
Sortie :

SkyScore

📷 Setup Engine
Détermine quel setup est le plus adapté.

Un setup est un ensemble cohérent :

monture
tube
caméra
filtres
accessoires
automatisation
Sortie :

SetupScore

🎯 Project Engine
Détermine quel projet mérite d'être poursuivi.

Critères :

ROI
progression
urgence
saison
coût du report
compatibilité setup
Sortie :

ProjectScore

📂 Portfolio Engine
Optimise le portefeuille complet.

Critères :

diversification
équilibre
roadmap
progression
charge restante
Sortie :

PortfolioScore

🧠 Decision Engine
Fusionne les quatre moteurs précédents.

DecisionScore = SkyScore + SetupScore + ProjectScore + PortfolioScore

Puis explique la recommandation.

Principes
Chaque fonctionnalité appartient à un seul moteur.
Les moteurs sont indépendants.
Le Decision Engine est le seul autorisé à agréger les résultats.
Aucun algorithme ne dépend d'un matériel particulier.
AstroPilot recommande.
L'utilisateur décide.


