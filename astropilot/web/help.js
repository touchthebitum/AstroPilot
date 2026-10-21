"use strict";

// Shared editorial source. Stable section ids are also future contextual-link targets.
const NIGHTMERIT_GUIDES = Object.freeze({
  start: {
    title: "Bien démarrer", intro: "De votre premier projet au suivi de vos images, étape par étape.", sections: [
      ["purpose", "Décider quoi photographier et quand", "NightMerit propose une cible, un filtre et un créneau selon votre matériel et les conditions prévues. Vous gardez la décision finale."],
      ["project-session", "Projet, mission ou session ?", "Un projet suit une cible et un objectif total par filtre, sur une ou plusieurs nuits. Une mission est le plan proposé pour un créneau. Une session correspond aux prises de vue réellement effectuées pour cette mission."],
      ["first-night", "Préparer votre première séance", "Suivez Site → Matériel → Projet → Disponibilité → Préparer ma nuit. Consultez « Conseils pour cette cible » et confirmez uniquement les filtres que vous possédez. L’objectif du projet est un total à accumuler ; la disponibilité indique seulement quand vous pouvez photographier."],
      ["read-recommendation", "Lire la recommandation", "Vérifiez la cible, le filtre, les horaires et les risques. Si le plan vous convient, cliquez sur « Photographier cette cible ». Dans la mission, utilisez « Démarrer une nouvelle session » lorsque vous commencez réellement les prises de vue."],
      ["no-recommendation", "Si aucune mission n’est proposée", "Lisez la raison affichée : météo, disponibilité ou configuration. NightMerit peut s’abstenir et votre projet est conservé. Si la météo est défavorable, revenez plus tard et utilisez « Actualiser les prévisions » lorsque ce bouton est proposé. Aucune session n’est nécessaire si vous ne photographiez pas."],
      ["after-night", "Trier vos clichés après la séance", "Cliquez sur « Terminer la session » après les prises de vue. Après les flats, vérifiez vos clichés, éventuellement le lendemain. Comptez uniquement les images conservées, sans les images rejetées ni les flats, darks et bias. Par exemple, 25 images utilisables de 3 minutes représentent 1 h 15. Si aucun cliché n’est utilisable, n’ajoutez aucune durée."],
      ["record-time", "Ajouter ce temps à votre projet", "Dans « Mes projets », dépliez « J’ai pris des photos : renseigner mon temps de pose », puis « Retrouver mes sessions NightMerit ». Ouvrez la mission et choisissez la session terminée. Utilisez « Enregistrer la durée utilisable », puis confirmez « Ajouter cette durée à mon avancement ». Saisissez seulement la durée de cette séance. Le total se cumule par filtre ; une durée déjà ajoutée ne doit pas être recopiée comme temps de départ."],
      ["field-notes", "Noter les conditions sur place", "Cette observation terrain décrit le ciel réellement rencontré. Elle est distincte de votre temps de pose et n’ajoute aucune durée au projet."],
      ["presentation", "Simple ou Pro", "Le même moteur produit les mêmes décisions. Simple présente les actions essentielles ; Pro donne plus de détails. Le changement conserve vos saisies."],
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
      ["tonight", "Préparer ma séance / recommandations", "Ouvrez Préparer ma séance (Ce soir en Pro), puis utilisez Préparer ma nuit après avoir vérifié la configuration et vos horaires. Lisez la cible, le filtre, le créneau et les risques. En cas d’abstention, suivez la raison affichée. Actualiser les prévisions peut changer le résultat, sans garantir un créneau favorable."],
      ["missions", "Projets, missions et sessions", "Le projet conserve votre objectif total et votre avancement par filtre sur plusieurs nuits. La mission contient le plan accepté avec Photographier cette cible. Créez et démarrez une session au début réel des prises de vue, puis terminez-la. Après le tri, enregistrez sa durée utilisable et confirmez séparément son ajout à l’avancement. Le temps de départ couvre les images antérieures au suivi : ne recopiez pas les sessions déjà ajoutées."],
      ["observations", "Noter les conditions sur place", "Cette observation terrain décrit les conditions rencontrées pendant ou après la séance ; elle n’enregistre pas de temps de pose. Ne renseignez pas une mesure inconnue comme si elle avait été observée. Relisez les valeurs avant de les enregistrer ; les champs avancés restent facultatifs selon le contexte."],
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
