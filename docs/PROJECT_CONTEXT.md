AstroPilot

Official Product Name : AstroPilot

Vision

Créer une application mobile Android/iOS destinée aux astrophotographes permettant de
recommander automatiquement les meilleures nuits et les meilleurs objets à photographier selon la
météo, la Lune, la qualité du ciel, le matériel utilisé et la position GPS.

Architecture cible
AstroPilot Engine (Python) → FastAPI → Android / iOS
État actuel
- Prévisions météo Open-Meteo
- Calcul des heures de nuit
- Lever/coucher de la Lune
- Phase lunaire
- Séparation lune-cible
- SQM estimé
- Score météo
- Score objet
- Score nuit
Profils matériels
- redcat51_2600
- evostar72_533
- c8_hyperstar_2600
- rc8_294
Système de cadrage
Basé sur le type d'objet, sa taille apparente et le champ couvert par l'instrument.
Outils de développement
- VS Code
- Python
- Git
- GitHub
Dépôt GitHub
https://github.com/touchthebitum/astropilot.git

Priorités court terme
1. Stabiliser astro_score.py
2. Étendre le catalogue d'objets
3. Ajouter des tests automatiques
4. Améliorer le score de cadrage
5. Préparer une API FastAPI
6. 
Priorités moyen terme
1. API REST
2. Gestion GPS
3. Détection automatique du fuseau horaire
4. Support multilingue
5. Gestion utilisateurs
6. 
Priorités long terme

Application Android/iOS avec GPS automatique, recommandations, favoris, notifications et
synchronisation cloud.

Question centrale
« Que puis-je photographier ce soir avec MON matériel depuis MA position ? »


Nom officiel : AstroPilot

Domaine officiel :
https://astropilot.io

Dépôt GitHub :
https://github.com/touchthebitum/astropilot





Nom officiel du projet : AstroPilot

Objectif final :
Application mobile Android/iOS permettant de recommander automatiquement les meilleures cibles astrophotographiques en fonction :

- du lieu d'observation
- du matériel
- de la météo
- de la lune
- de la saison
- de la qualité du ciel

Le moteur Python constitue le cœur du produit.

L'application mobile constitue l'interface utilisateur principale.

# Sprint – Intelligence Layer : SeasonAnalysis

## Objectif
Création de la première couche d'intelligence indépendante capable d'analyser un aspect d'une mission et de produire un résultat structuré.

## Nouveaux composants

### AnalysisResult
Structure commune utilisée par tous les moteurs d'analyse.

Contient :
- analysis_name
- conclusion
- confidence
- data

### AnalysisContext
Contexte partagé entre les analyses.

Premiers champs :
- target
- weather
- productivity
- risk

Tous les futurs moteurs utiliseront cette structure.

### SeasonAnalysis
Premier moteur d'analyse implémenté.

Il :
- interroge SeasonEngine
- calcule un niveau de confiance
- génère une conclusion textuelle
- retourne un AnalysisResult

## Intégration

NightMission contient désormais :

- season_analysis

MissionAssembler construit désormais un véritable AnalysisContext avant d'appeler les moteurs d'intelligence.

MissionPresenter affiche directement les résultats de SeasonAnalysis.

## Architecture actuelle

SeasonEngine
↓
SeasonAnalysis
↓
AnalysisResult
↓
NightMission
↓
MissionPresenter

## Limitation actuelle

SeasonEngine repose encore sur une table statique
(SEASON_WINDOWS).

Les objets absents de cette table retournent actuellement
UNKNOWN.

## Prochaine évolution

Supprimer complètement SEASON_WINDOWS.

Calculer automatiquement la saison d'un objet à partir :

- RA
- DEC
- latitude observateur
- date
- durée de nuit
- altitude utile

Toutes les cibles du catalogue deviendront ainsi compatibles sans maintenance manuelle.

