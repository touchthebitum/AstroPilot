"use strict";

// Shared editorial source. Stable section ids are also future contextual-link targets.
const NIGHTMERIT_GUIDES = Object.freeze({
  start: {
    title: "Bien démarrer", intro: "Votre première nuit en 2–3 minutes.", sections: [
      ["purpose", "Si, quoi et quand imager", "NightMerit vous aide à décider si les conditions sont suffisantes pour imager, quelle cible et quel filtre choisir, et quand commencer. Vous gardez la décision finale."],
      ["first-night", "Préparer votre première nuit", "Suivez Site → Matériel → Disponibilité → Préparer ma nuit. Vérifiez le lieu d’observation, choisissez votre matériel et les filtres disponibles, puis indiquez votre créneau. Relisez ces informations avant de lancer la préparation."],
      ["read-recommendation", "Lire la recommandation", "Repérez la cible, le filtre et le créneau proposé. Lisez la qualité attendue et les risques : le temps disponible ne correspond pas toujours au temps réellement utile pour imager. Vérifiez que le plan convient à votre installation."],
      ["no-recommendation", "Si rien n’est recommandé", "Ce n’est pas une erreur. NightMerit préfère s’abstenir plutôt que proposer une recommandation fragile. Lisez la raison affichée, vérifiez votre configuration et votre disponibilité, puis revenez lorsque les conditions ou les prévisions évoluent."],
      ["after-night", "Après la nuit", "Vous pouvez ajouter une observation terrain pour décrire les conditions réellement rencontrées. Consultez ensuite votre historique et les comparaisons disponibles pour confronter la prévision à votre expérience."],
      ["presentation", "Simple ou Pro", "Le même moteur produit les mêmes décisions dans les deux modes. Simple met les actions essentielles en avant ; Pro affiche davantage de détails. Changer de présentation ne change pas votre recommandation."],
    ],
  },
  understand: {
    title: "Comprendre NightMerit", intro: "La fiabilité avant la richesse fonctionnelle.", sections: [
      ["reliability", "Recommander seulement si les conditions sont suffisantes", "NightMerit ne cherche pas à toujours produire une réponse positive. Une abstention expliquée est plus utile qu’un plan séduisant mais fragile. « Non recommandé » vaut mieux qu’une fausse précision."],
      ["three-levels", "Prévision, décision et réalité", "La prévision météo décrit des conditions attendues. La décision NightMerit évalue ce que ces conditions permettent avec votre configuration. L’observation réelle décrit ce qui s’est passé sur le terrain. Ces trois niveaux peuvent différer et doivent rester distincts."],
      ["context", "Une recommandation dépend du contexte", "Le site, le matériel, le filtre, la cible, la fenêtre productive et les risques contribuent à la recommandation. La fenêtre productive est la partie du créneau réellement utile pour cette acquisition. Un ciel acceptable ne suffit pas si la cible ou le matériel ne conviennent pas."],
      ["nuance", "Des conditions à lire ensemble", "La Lune, l’humidité et les nuages ne se résument pas à une règle unique. Leur effet dépend notamment de la cible, du filtre et du créneau. NightMerit utilise une logique plus nuancée lorsque les données disponibles le permettent, sans supprimer l’incertitude."],
      ["validation", "Apprendre des observations terrain", "Les observations terrain servent à valider la qualité des recommandations et à comparer les conditions prévues et observées. Un seul cas ne déclenche pas de recalibrage automatique. Une comparaison isolée ne prouve pas la fiabilité globale du produit."],
      ["modes", "Deux profondeurs de lecture", "Simple et Pro partagent le même moteur, les mêmes décisions et les mêmes guides. Seule la profondeur d’affichage et la hiérarchie des accès changent. Les détails techniques sont disponibles pour comprendre une décision, sans être nécessaires pour commencer."],
      ["uncertainty", "Des limites explicites", "La météo reste une prévision. Certaines données peuvent être inconnues ou devenir moins représentatives au fil de la nuit. Lisez les limites et les risques affichés, vérifiez les conditions sur place et adaptez votre plan si nécessaire."],
    ],
  },
  complete: {
    title: "Guide complet", intro: "Première référence structurée. Les procédures avancées seront enrichies progressivement.", sections: [
      ["installation", "Installation / premier lancement", "Lancez l’application NightMerit installée sur votre ordinateur. Au premier lancement, renseignez votre configuration. Pour l’installation propre à votre système et à votre version, consultez les instructions fournies avec la distribution."],
      ["site", "Configuration du site", "Choisissez le lieu réel d’observation et vérifiez ses coordonnées, son fuseau horaire et les informations de ciel demandées. Une erreur de site peut affecter les horaires et la visibilité des cibles. Utilisez Modifier ma configuration pour corriger les valeurs."],
      ["equipment", "Matériel et presets", "Choisissez un preset adapté ou renseignez votre matériel. Vérifiez les filtres effectivement disponibles. Un preset est un point de départ : il doit correspondre à votre installation réelle."],
      ["availability", "Disponibilité", "Définissez votre début et votre fin de disponibilité dans le fuseau du site. NightMerit cherche une fenêtre productive à l’intérieur de ce créneau ; il ne suppose pas que toute la nuit est exploitable."],
      ["tonight", "Tonight / recommandations", "Dans Ce soir, utilisez Préparer ma nuit après avoir vérifié la configuration. Lisez la cible, le filtre, le créneau, la qualité et les risques. Consultez les raisons d’une abstention. Une nouvelle préparation peut donner un résultat différent si le contexte ou les prévisions ont changé."],
      ["missions", "Missions et sessions", "Lorsque la recommandation vous convient, utilisez l’action d’acceptation proposée pour préparer une mission. Une mission décrit le plan retenu ; une session décrit son exécution. Vérifiez les informations affichées avant d’enregistrer votre progression."],
      ["observations", "Observations terrain", "Ajoutez les conditions observées après ou pendant la nuit, en les reliant au contexte proposé. Ne renseignez pas une mesure inconnue comme si elle avait été observée. Relisez les valeurs avant publication ; les champs avancés restent facultatifs selon le contexte."],
      ["history", "Comparaisons et historique", "Ouvrez Mon historique pour retrouver les validations disponibles. Vérifiez le site et les filtres actifs avant d’interpréter les comparaisons. Les écarts entre prévu et observé décrivent ces cas, sans conclure à eux seuls à la qualité globale des prévisions."],
      ["modes", "Mode Simple / Pro", "Le sélecteur Présentation change la profondeur d’affichage. Simple privilégie Bien démarrer ; Pro rend les trois guides immédiatement visibles. La recommandation scientifique et les données saisies restent les mêmes."],
      ["weather-trace", "Traçabilité météo / détails techniques", "En Pro, consultez les détails techniques disponibles pour examiner le contexte météo et les informations associées à une décision ou à une validation. Une donnée absente reste inconnue : elle ne doit pas être interprétée comme une condition favorable."],
      ["recovery", "Recovery / erreurs / publication incertaine", "Lisez le message affiché avant de réessayer. Si la publication d’une observation est incertaine, utilisez les actions de vérification ou de reprise proposées ; évitez de créer immédiatement une nouvelle observation identique. Conservez votre brouillon tant que l’enregistrement n’est pas confirmé. Une réinitialisation doit rester un choix explicite après lecture de ses conséquences."],
      ["limits", "Limites connues et bonnes pratiques", "Vérifiez le lieu, le matériel et les horaires avant chaque nuit. Les prévisions évoluent et ne garantissent pas le résultat d’une acquisition. Contrôlez les conditions sur place. Une abstention ou une donnée inconnue est préférable à une précision artificielle."],
      ["glossary", "Glossaire", "Recommandation : proposition conditionnelle pour votre nuit. Fenêtre productive : partie utile du créneau pour imager. Preset : configuration de matériel préremplie. Observation terrain : description des conditions réellement rencontrées. Incertitude : ce que les données ne permettent pas d’affirmer. AQI : indicateur de qualité d’acquisition présenté par NightMerit ; ce n’est pas une garantie de résultat."],
    ],
  },
});

(() => {
  const dialog = document.querySelector("#help-dialog");
  const content = document.querySelector("#help-content");
  const opener = document.querySelector("#help-open");
  const buttons = [...dialog.querySelectorAll("[data-help-guide]")];
  const modeSelect = document.querySelector("#help-mode");
  let activeGuide = "start";
  const positions = new Map();
  function selectGuide(key, section) {
    if (!Object.hasOwn(NIGHTMERIT_GUIDES, key)) return;
    positions.set(activeGuide, content.scrollTop);
    activeGuide = key;
    const guide = NIGHTMERIT_GUIDES[key];
    content.replaceChildren();
    const heading = document.createElement("h3");
    heading.textContent = guide.title;
    const intro = document.createElement("p");
    intro.textContent = guide.intro;
    content.append(heading, intro);
    const toc = document.createElement("nav");
    toc.setAttribute("aria-label", "Sections du guide");
    for (const [id, title, text] of guide.sections) {
      const link = document.createElement("a");
      link.href = `#help-${key}-${id}`;
      link.textContent = title;
      link.addEventListener("click", event => {
        event.preventDefault();
        content.querySelector(link.getAttribute("href")).focus();
      });
      toc.append(link);
    }
    content.append(toc);
    for (const [id, title, text] of guide.sections) {
      const block = document.createElement("section");
      block.id = `help-${key}-${id}`;
      block.tabIndex = -1;
      const h = document.createElement("h4");
      h.textContent = title;
      const p = document.createElement("p");
      p.textContent = text;
      block.append(h, p);
      content.append(block);
    }
    for (const button of buttons) {
      if (button.dataset.helpGuide === key) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    }
    content.scrollTop = positions.get(key) || 0;
    if (section) document.getElementById(`help-${key}-${section}`)?.focus();
  }
  function syncMode() {
    modeSelect.value = document.documentElement.dataset.uiMode === "pro" ? "pro" : "simple";
  }
  // Public contextual entry point, independent of decisions, drafts and network requests.
  function openGuide(key = activeGuide, section) {
    if (!dialog.open) dialog.showModal();
    if (!content.childElementCount || key !== activeGuide || section) selectGuide(key, section);
    syncMode();
  }
  opener.addEventListener("click", () => openGuide());
  document.querySelector("#help-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => opener.focus());
  dialog.addEventListener("keydown", event => {
    if (event.key !== "Tab") return;
    const controls = [...dialog.querySelectorAll('button, select, a[href], [tabindex="0"]')];
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  for (const button of buttons) button.addEventListener("click", () => selectGuide(button.dataset.helpGuide));
  modeSelect.addEventListener("change", () => {
    const globalSelect = document.querySelector("#ui-mode");
    globalSelect.value = modeSelect.value;
    globalSelect.dispatchEvent(new Event("change", { bubbles: true }));
  });
  new MutationObserver(syncMode).observe(document.documentElement, { attributes: true, attributeFilter: ["data-ui-mode"] });
  window.nightmeritHelp = Object.freeze({ open: openGuide });
})();
