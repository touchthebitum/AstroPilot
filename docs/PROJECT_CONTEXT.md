PROJECT_CONTEXT - AstroPilot
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
Priorités moyen terme
1. API REST
2. Gestion GPS
3. Détection automatique du fuseau horaire
4. Support multilingue
5. Gestion utilisateurs
Priorités long terme
Application Android/iOS avec GPS automatique, recommandations, favoris, notifications et
synchronisation cloud.

Question centrale
« Que puis-je photographier ce soir avec MON matériel depuis MA position ? »