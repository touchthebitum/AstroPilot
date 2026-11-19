"use strict";
globalThis.NightMeritPresentation = {
  demoEnabled: false,
  simulatedWeather(trust) {
    return trust?.provider === "NightMerit — météo simulée (démonstration)";
  },
  explanation: "La météo est simulée : ciel dégagé, humidité 50 %, vent 3 km/h, pluie nulle. La visibilité des cibles, la nuit, la Lune, vos horaires et votre matériel restent calculés. Une cible ou un créneau ne sont donc pas garantis. Ces résultats ne permettent pas de juger la fiabilité de prévisions réelles.",
  discoveryCopy(hasSuggestions) {
    return (hasSuggestions ? "Créneaux calculés avec la météo simulée. Confirmez votre projet, puis relancez l’analyse. " : "Aucune cible ne satisfait les contraintes calculées avec cette météo simulée. Vérifiez vos horaires, votre matériel et les cibles prises en charge. ") + "Aucune prévision réelle ni temps de pose ajouté.";
  }
};
