"use strict";

// Presentation adapter only. All writes use the existing guarded application handlers.
(() => {
  const $ = selector => document.querySelector(selector);
  const setText = (el, value) => { if (el && el.textContent !== value) el.textContent = value; };
  const hide = (el, value) => { if (el && el.hidden !== value) el.hidden = value; };
  const simple = () => document.documentElement.dataset.uiMode === "simple";
  const make = (tag, attributes = {}, content = "") => {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, value);
    el.textContent = content;
    return el;
  };
  const action = (label, handler, primary = false) => {
    const button = make("button", {type: "button", class: primary ? "primary-button" : "secondary-button"}, label);
    button.addEventListener("click", handler);
    return button;
  };

  // Offer the two paths before exposing the manual project form.
  const discoverProject = $("#discover-from-projects");
  const projectCreation = $("#project-create");
  const discoveryEntry = discoverProject.closest(".discovery-entry");
  const manualProject = action("Je connais déjà ma cible", async () => {
    if (guardUnresolvedAcceptance() || state.savingConfiguration) return;
    projectCreation.open = true;
    manualProject.setAttribute("aria-expanded", "true");
    if (!state.projectTemplates) await loadProjectTemplates();
    else renderNewProjectIntents();
    if (state.view === "projects" && projectCreation.open) $("#project-template").focus();
  });
  manualProject.id = "beginner-manual-project";
  manualProject.setAttribute("aria-controls", "project-create");
  manualProject.setAttribute("aria-expanded", "false");
  discoveryEntry.append(manualProject);
  projectCreation.addEventListener("toggle", () => {
    manualProject.setAttribute("aria-expanded", String(projectCreation.open));
  });

  const demoBanner = make("aside", {id: "demo-banner", role: "note", hidden: ""});
  demoBanner.textContent = "ESSAI FICTIF — MÉTÉO SIMULÉE. Ces conditions ne sont pas des prévisions réelles. Les projets et les poses saisis ici sont réservés à la démonstration.";
  $("main.shell").before(demoBanner);
  fetch("/v1/demo-context", {cache: "no-store"}).then(response => {
    if (!response.ok) throw new Error("demo context unavailable");
    return response.json();
  }).then(context => {
    demoBanner.hidden = !context.enabled;
    if (globalThis.NightMeritPresentation) globalThis.NightMeritPresentation.demoEnabled = context.enabled === true;
    if (context.enabled) {
      const macTransfer = document.querySelector("#data-context-mac-transfer");
      if (macTransfer) macTransfer.textContent = "GERER-DONNEES-FICTIVES.command";
      for (const dialog of document.querySelectorAll("dialog")) {
        dialog.prepend(make("p", {class: "demo-dialog-note"}, "ESSAI FICTIF — MÉTÉO SIMULÉE. Aucune prévision réelle."));
      }
      for (const link of document.querySelectorAll('a[href*="open-meteo"]')) {
        link.textContent = "Météo simulée pour cet essai — aucune prévision réelle";
        link.removeAttribute("href");
      }
    }
  }).catch(() => {
    demoBanner.hidden = false;
    demoBanner.textContent = "Le mode météo ne peut pas être vérifié. Actualisez la page avant de poursuivre.";
  });

  const guide = make("aside", {id: "beginner-guide", "aria-label": "Les étapes de ma séance"});
  guide.append(make("p", {class: "state-kicker"}, "Ma séance, pas à pas"));
  const list = make("ol");
  const names = ["Préparer", "Choisir", "Photographier", "Ajouter"];
  const descriptions = ["Mon matériel et mes horaires", "Ma cible et son filtre", "Mon plan et mes prises de vue", "Mes photos après le tri"];
  const steps = names.map((name, i) => {
    const item = make("li");
    item.append(make("span", {class: "beginner-number", "aria-hidden": "true"}, String(i + 1)),
      make("strong", {}, name), make("small", {}, descriptions[i]));
    list.append(item);
    return item;
  });
  guide.append(list);
  $("main.shell").prepend(guide);

  // Reuse the real discovery choice. No filter is inferred or confirmed here.
  const discovery = $("#discover-targets");
  const choice = make("fieldset", {id: "beginner-choice"});
  choice.append(make("legend", {}, "Sur quel projet souhaitez-vous travailler ?"));
  const discoverValue = "__nightmerit_discover__";
  const compareValue = "__nightmerit_compare_projects__";

  const projectWrap = make("label", {id: "beginner-project-wrap"}, "Choisir une option");
  const projectSelect = make("select", {id: "beginner-project", "aria-label": "Projet pour cette séance ou aide au choix de la cible"});
  projectWrap.append(projectSelect);
  choice.append(projectWrap);
  discovery.closest("label").after(choice);
  async function selectPath(discover) {
    if (state.requestingRecommendation || state.savingConfiguration || guardUnresolvedAcceptance()) return;
    await setDiscoveryMode(discover);
    refresh();
  }
  projectSelect.addEventListener("change", () => {
    if (state.requestingRecommendation || state.savingConfiguration || guardUnresolvedAcceptance()) { refresh(); return; }
    const selected = projectSelect.value;
    if (selected === discoverValue) { void selectPath(true); return; }
    if (selected === compareValue) { void setProjectComparisonMode(); return; }
    if (!Object.hasOwn(state.configuration?.projects || {}, selected)) { refresh(); return; }
    state.selectedProjectId = selected;
    void selectPath(false);
  });
  const context = make("p", {id: "beginner-context", class: "field-note"});
  const contextEdit = action("Modifier mon site ou mon matériel", () => $("#availability-edit-configuration").click());
  const contextBlock = make("details", {id: "beginner-context-details"});
  contextBlock.append(make("summary", {}, "Mon site et mon matériel"), context, contextEdit);
  $("#availability-form").prepend(contextBlock);
  $("#availability-form").addEventListener("submit", event => {
    if (simple() && !state.discoveryMode && !state.compareProjects && !state.selectedProjectId) {
      event.preventDefault(); event.stopImmediatePropagation();
      showAvailabilityError("Choisissez un projet, « Quel projet avancer ce soir ? » ou « Aidez-moi à choisir une cible » dans la liste.");
      projectSelect.focus();
    }
  }, true);

  // Saved missions are an optional return path, not another primary form.
  const missionDetails = make("details", {id: "beginner-saved-missions"});
  missionDetails.append(make("summary", {}, "Retrouver un plan enregistré"));
  $("#saved-mission-entry").before(missionDetails);
  missionDetails.append($("#saved-mission-entry"));

  // Keep the real session control, but give the finished-session path one next action.
  const tri = make("section", {id: "beginner-tri", class: "session-next-step"});
  tri.append(make("h3", {}, "Mes prises de vue sont terminées"),
    make("p", {}, "Triez vos images et gardez uniquement les clichés utilisables. Vous pouvez le faire plus tard."));
  const add = action("Mes images sont triées : les ajouter", async () => {
    const projectId = state.acceptedMission?.selectedCatalogKey;
    const executionId = currentSession()?.execution.execution_id;
    if (state.sessionBusy || state.sessionWriteUncertain || !projectId || !executionId) return;
    ui.mission.close();
    await openPhotoAddition(projectId, {executionId});
  }, true);
  const later = action("Je le ferai plus tard", () => { ui.mission.close(); navigateGuidedProjects(); });
  tri.append(add, later);
  $("#session-evidence").before(tri);

  // A single read-only entry point; each action opens its existing consultation handler.
  const follow = make("dialog", {id: "beginner-follow", "aria-labelledby": "beginner-follow-title"});
  const heading = make("header", {class: "help-heading"});
  heading.append(make("h2", {id: "beginner-follow-title"}, "Mon suivi"), action("Fermer", () => follow.close()));
  follow.append(heading, make("p", {}, "Retrouvez vos résultats et vos relevés. Les consulter n’ajoute aucune photo."));
  const followActions = make("div", {class: "beginner-follow-actions"});
  for (const [label, selector] of [["Mes analyses météo", "[data-open-analysis-history]"], ["Mes relevés sur place", "#saved-observations-open"]]) {
    followActions.append(action(label, () => { follow.close(); $(selector)?.click(); }));
  }
  follow.append(followActions);
  document.body.append(follow);
  const followButton = action("Mon suivi", () => follow.showModal());
  followButton.id = "beginner-follow-open";
  $("#main-navigation").append(followButton);

  // Short help is available by mouse, keyboard and tap. Never replaces an essential instruction.
  const help = make("div", {id: "beginner-help", role: "tooltip", hidden: ""});
  document.body.append(help);
  let helpAnchor = null;
  let helpPinned = false;
  function closeHelp() {
    hide(help, true);
    if (helpAnchor) { helpAnchor.removeAttribute("aria-describedby"); helpAnchor.setAttribute("aria-expanded", "false"); }
    helpAnchor = null;
    helpPinned = false;
  }
  function showHelp(button, pinned = false) {
    if (helpAnchor === button && helpPinned && !pinned) return;
    closeHelp(); helpAnchor = button; helpPinned = pinned; setText(help, button.dataset.help);
    const surface = button.closest('dialog') || document.body;
    if (help.parentElement !== surface) surface.append(help);
    button.setAttribute("aria-describedby", help.id); button.setAttribute("aria-expanded", "true"); hide(help, false);
    const rect = button.getBoundingClientRect();
    const width = help.getBoundingClientRect().width;
    help.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - width - 8))}px`;
    const height = help.getBoundingClientRect().height;
    help.style.top = `${Math.max(8, Math.min(rect.bottom + 8, innerHeight - height - 8))}px`;
  }
  function addHelp(selector, description, label) {
    const anchor = $(selector);
    if (!anchor) return;
    const button = make("button", {type: "button", class: "beginner-help-button", "aria-label": label, "aria-expanded": "false"}, "?");
    button.dataset.help = description;
    if (anchor.tagName === "LEGEND") anchor.append(button); else anchor.after(button);
    button.addEventListener("click", () => helpAnchor === button && helpPinned ? closeHelp() : showHelp(button, true));
    button.addEventListener("mouseenter", () => showHelp(button));
    button.addEventListener("focus", () => showHelp(button));
    button.addEventListener("mouseleave", e => { if (!helpPinned && !help.contains(e.relatedTarget) && document.activeElement !== button) closeHelp(); });
    button.addEventListener("blur", () => { if (!helpPinned) closeHelp(); });
  }
  addHelp(".availability-modes legend", "Si la nuit a déjà commencé, seules les heures restantes sont analysées.", "Aide sur toute la nuit");
  addHelp("#photos-inputs label:last-of-type", "Le temps de pose d’une seule image. 300 secondes correspondent à 5 minutes.", "Aide sur la durée par cliché");
  addHelp(".observation-wind-qualitative legend", "Décrivez le vent ressenti. Laissez la vitesse vide si vous ne l’avez pas mesurée.", "Aide sur le vent observé");
  help.addEventListener("mouseleave", e => { if (!helpPinned && !helpAnchor?.contains(e.relatedTarget)) closeHelp(); });
  document.addEventListener("pointerdown", e => { if (!help.contains(e.target) && !helpAnchor?.contains(e.target)) closeHelp(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !help.hidden) { closeHelp(); e.stopPropagation(); } }, true);
  window.addEventListener("resize", closeHelp);
  document.addEventListener("scroll", closeHelp, true);

  let projectSignature = "";
  let previousMode = null;
  function refresh() {
    const beginner = simple();
    const stage = $("#photos-dialog").open ? 4 : ui.mission.open ? (currentSession()?.execution.status === "completed" ? 4 : 3)
      : ["discovery", "recommendation", "loading_recommendation", "unresolved_acceptance"].includes(state.view) ? 2 : 1;
    hide(guide, !beginner);
    document.body.classList.toggle("beginner-layout", beginner);
    steps.forEach((item, i) => {
      item.classList.toggle("active", i + 1 === stage);
      if (i + 1 === stage) item.setAttribute("aria-current", "step"); else item.removeAttribute("aria-current");
    });
    for (const select of document.querySelectorAll("#ui-mode, #help-mode")) {
      setText(select.querySelector('[value="simple"]'), "Débutant");
      setText(select.querySelector('[value="pro"]'), "Avancé");
    }
    hide(manualProject, !beginner);
    discoverProject.className = beginner ? "primary-button" : "secondary-button";
    setText(discoverProject, beginner ? "Aidez-moi à choisir une cible" : "Je ne sais pas quoi photographier");
    setText(discoveryEntry.querySelector("p"), beginner
      ? "Selon mon matériel, mes horaires et les conditions du ciel."
      : "NightMerit peut rechercher une cible parmi celles prises en charge, selon votre matériel et vos horaires.");
    hide(choice, !beginner);
    hide($("#compare-projects").closest("label"), beginner);
    hide(discovery.closest("label"), beginner);
    hide(contextBlock, !beginner);
    hide(followButton, !beginner);
    hide(missionDetails, $("#saved-mission-entry").hidden);
    if (previousMode !== beginner) missionDetails.open = !beginner;
    previousMode = beginner;
    const configured = Boolean(state.configuration?.configured);
    const keys = Object.keys(state.configuration?.projects || {});
    const signature = JSON.stringify(keys);
    if (signature !== projectSignature) {
      projectSignature = signature;
      projectSelect.replaceChildren(make("option", {value: ""}, "Choisir une option"),
        make("option", {value: discoverValue}, "Aidez-moi à choisir une cible"),
        ...(keys.length ? [make("option", {value: compareValue}, "Quel projet avancer ce soir ?")] : []));
      keys.forEach(key => projectSelect.append(make("option", {value: key}, readableTargetName(key))));
    }
    const busy = state.requestingRecommendation || state.savingConfiguration || hasUnresolvedAcceptance();
    projectSelect.disabled = busy;
    projectSelect.value = state.compareProjects ? compareValue : state.discoveryMode ? discoverValue : keys.includes(state.selectedProjectId) ? state.selectedProjectId : "";
    setText(context, [state.configuration?.site?.name, $("#review-equipment")?.textContent].filter(v => v && v !== "—").join(" · ") || "Votre configuration enregistrée sera utilisée.");
    if (beginner && configured && state.view === "availability") {
      setText($("#availability-title"), state.missionRecheck ? "Vérifier ma séance" : (document.documentElement.dataset.choicePhase === "filters" ? "Quel filtre utilisez-vous ?" : (document.documentElement.dataset.choicePhase === "hours" ? "Quand souhaitez-vous observer ?" : "Préparer ma séance")));
      setText($("#availability-intro"), state.missionRecheck ? "Retrouvez ci-dessous les horaires de votre plan de séance." : "Choisissez un projet, comparez vos projets en cours ou demandez une cible, puis indiquez vos horaires.");
      setText(ui.recommendationSubmit, state.compareProjects ? "Quel projet avancer ce soir ?" : state.discoveryMode ? "Chercher quoi photographier" : "Vérifier mon projet");
    }
    refreshSearchResumeAction();
    const session = currentSession();
    const finished = session?.execution.status === "completed";
    hide(tri, !beginner || !finished || Boolean(session?.credit) || noRetainedImages(session));
    add.disabled = state.sessionBusy || state.sessionWriteUncertain || !state.acceptedMission?.selectedCatalogKey;
    // Do not bypass an uncertain write or conceal the canonical error/status.
    $("#mission-dialog").classList.toggle("beginner-session", beginner);
    if (beginner) {
      setText($("#session-title"), "Ma séance photo");
      setText($("#setup-title"), "Mon matériel");
      setText($("#plan-title"), "Mon plan de nuit");
      setText($("#open-mission"), "Voir mon plan de nuit");
    } else {
      setText($("#session-title"), "Session d’imagerie");
      setText($("#setup-title"), "Préparer la configuration");
      setText($("#plan-title"), "Suivre le plan de nuit");
      setText($("#open-mission"), "Photographier cette cible");
    }
  }
  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; refresh(); });
  }
  new MutationObserver(schedule).observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ["hidden", "open"]});
  new MutationObserver(schedule).observe(document.documentElement, {attributes: true, attributeFilter: ["data-ui-mode", "data-guided-view"]});
  document.addEventListener("change", schedule);
  document.addEventListener("close", schedule, true);
  refresh();
})();
