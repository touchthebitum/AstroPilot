# AstroPilot Decision Architecture v1

Version : 0.1
Statut : Draft

---

# Mission

AstroPilot est un système expert qui transforme des données
astronomiques en décisions d'investissement astrophotographique
optimales, explicables et personnalisées.

Il ne cherche pas uniquement à répondre :

"Quel est le meilleur objet ?"

mais :

"Où dois-je investir mon prochain temps
d'acquisition pour maximiser la valeur
de mon portefeuille astrophotographique ?"

---

# Principe fondamental

Toutes les décisions doivent être :

- explicables
- justifiables
- traçables
- reproductibles

Aucun moteur ne peut produire une recommandation
qu'il est incapable d'expliquer.

# Principes fondateurs

## 1. Une donnée possède une seule source de vérité

Chaque information est calculée une seule fois.

Exemples :

- Productivité → NightSliceEvaluator
- Météo → NightConditionsProvider
- Risque → RiskEngine
- Saison → SeasonAnalysis

Les autres modules ne doivent jamais recalculer ces informations.

---

## 2. Les moteurs produisent des analyses

Un moteur ne retourne pas uniquement un score.

Il retourne une analyse complète.

Une analyse comprend :

- une conclusion
- un niveau de confiance
- les preuves
- les métriques utilisées

---

## 3. Les décisions sont explicables

Chaque recommandation doit pouvoir répondre :

Pourquoi ?

La justification fait partie intégrante du résultat.

---

## 4. Le Decision Engine n'est pas un calculateur

Son rôle est de combiner plusieurs analyses.

Il ne doit pas recalculer les informations produites
par les autres moteurs.

---

## 5. AstroPilot optimise un investissement

Le moteur ne cherche pas uniquement le meilleur objet.

Il cherche le meilleur investissement
de temps astrophotographique.

# Le raisonnement d'AstroPilot

AstroPilot ne prend jamais une décision directement.

Il suit systématiquement les étapes suivantes.

---

## Étape 1 : Observer

Le moteur collecte les données disponibles.

Exemples :

- météo
- seeing
- transparence
- humidité
- vent
- Lune
- matériel
- objets
- portefeuille
- historique
- disponibilité de l'utilisateur

Aucune décision n'est prise à cette étape.

---

## Étape 2 : Analyser

Chaque domaine est étudié indépendamment.

Exemples :

- Astro Analysis
- Equipment Analysis
- Project Analysis
- Season Analysis
- Risk Analysis
- Opportunity Analysis

Chaque analyse possède une responsabilité unique.

Les analyses sont indépendantes les unes des autres.

---

## Étape 3 : Produire des preuves

Chaque analyse transforme ses résultats en preuves.

Une preuve contient :

- une conclusion
- un niveau de confiance
- une importance
- une justification

Les preuves sont destinées à être combinées.

---

## Étape 4 : Construire une recommandation d'investissement

Le moteur d'intelligence rassemble toutes les preuves.

Il répond à une seule question :

"Où investir le prochain temps d'acquisition ?"

Cette recommandation est toujours argumentée.

---

## Étape 5 : Prendre une décision

Le Decision Engine transforme la recommandation
en décision opérationnelle.

Exemples :

- objet conseillé
- filtre conseillé
- durée
- heure de début
- planning de la nuit
- recommandations

---

## Étape 6 : Expliquer

La décision finale doit toujours être justifiée.

L'utilisateur doit comprendre :

- pourquoi cette décision est proposée
- quels critères ont été utilisés
- quels compromis ont été effectués
- quel est le niveau de confiance

L'explication fait partie intégrante de la décision.

# Les qualités d'une bonne décision

Une recommandation AstroPilot est considérée comme excellente
uniquement si elle satisfait simultanément les critères suivants.

---

## 1. Pertinence

La décision répond au contexte réel de l'utilisateur.

Elle tient compte notamment :

- du matériel
- de la météo
- du portefeuille
- de la saison
- du temps disponible

---

## 2. Explicabilité

La recommandation est compréhensible.

Chaque conclusion peut être justifiée.

L'utilisateur peut comprendre
pourquoi AstroPilot recommande cette action.

---

## 3. Robustesse

Une légère variation des données
ne doit pas modifier totalement la recommandation.

Le moteur doit être stable.

---

## 4. Personnalisation

Deux utilisateurs différents
peuvent recevoir des recommandations différentes.

Les préférences utilisateur
font partie intégrante de la décision.

---

## 5. Anticipation

Le moteur ne raisonne pas uniquement
sur la nuit en cours.

Il tient compte :

- des nuits futures
- de la progression des projets
- de la saison
- des opportunités futures

---

## 6. Optimisation

Chaque heure disponible est considérée
comme une ressource précieuse.

Le moteur cherche à produire
la plus grande valeur astrophotographique possible.

---

## 7. Transparence

AstroPilot ne cache jamais son raisonnement.

Chaque recommandation doit pouvoir être expliquée.

Le niveau de confiance est toujours communiqué.

# Les lois d'AstroPilot

Les lois suivantes constituent les fondements permanents du moteur décisionnel.

Toute évolution future doit les respecter.

---

## Loi n°1

AstroPilot ne vend pas des données.

Il produit des décisions.

---

## Loi n°2

Une donnée possède une seule source de vérité.

Aucune duplication de logique n'est autorisée.

---

## Loi n°3

Chaque moteur possède une responsabilité unique.

Un moteur ne répond qu'à une seule question métier.

---

## Loi n°4

Une recommandation doit toujours être explicable.

Le moteur doit pouvoir justifier chaque conclusion.

---

## Loi n°5

Le niveau de confiance fait partie intégrante de la décision.

L'incertitude n'est jamais cachée.

---

## Loi n°6

Chaque heure disponible possède une valeur.

Le rôle d'AstroPilot est d'investir cette ressource de la manière la plus pertinente.

---

## Loi n°7

Le portefeuille est optimisé dans sa globalité.

Le moteur ne cherche pas uniquement
à optimiser la nuit en cours.

Il optimise l'ensemble de la saison.

---

## Loi n°8

Les décisions doivent rester stables.

Une faible variation des données
ne doit pas produire une recommandation totalement différente.

---

## Loi n°9

Les analyses sont indépendantes.

Le Decision Engine orchestre les analyses.

Les analyses ne se connaissent pas entre elles.

---

## Loi n°10

La vision produit prime toujours sur le code.

Lorsqu'un choix technique est possible,
la solution retenue est celle qui améliore
la qualité de la décision finale.
