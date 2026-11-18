"use strict";
(() => {
 const $=s=>document.querySelector(s), root=document.documentElement;
 const style=document.createElement('style');
 style.textContent=`
 html[data-ui-mode="simple"] #onboarding .eyebrow, html[data-ui-mode="simple"] #availability-step .eyebrow{display:none}
 html[data-ui-mode="simple"] #equipment-step .equipment-filter-help{display:none}
 html[data-ui-mode="simple"] #equipment-step .step-intro{max-width:42em}
 html[data-ui-mode="simple"] #equipment-step .choice-tabs label{padding:12px}
 html[data-ui-mode="simple"] #equipment-step[data-choice-page="camera"] .choice-tabs,
 html[data-ui-mode="simple"] #equipment-step[data-choice-page="camera"] #equipment-search-panel>.field,
 html[data-ui-mode="simple"] #equipment-step[data-choice-page="camera"] #equipment-search-status,
 html[data-ui-mode="simple"] #equipment-step[data-choice-page="camera"] #equipment-selection-summary{display:none}
 html[data-ui-mode="simple"] #custom-equipment>p,
 html[data-ui-mode="simple"] #custom-equipment>details{display:none}
 html[data-ui-mode="simple"][data-choice-phase="filters"] .availability-modes,
 html[data-ui-mode="simple"][data-choice-phase="filters"] .availability-fields,
 html[data-ui-mode="simple"][data-choice-phase="filters"] .availability-actions,
 html[data-ui-mode="simple"][data-choice-phase="filters"] #availability-overnight-hint,
 html[data-ui-mode="simple"][data-choice-phase="filters"] #beginner-choice,
 html[data-ui-mode="simple"][data-choice-phase="hours"] #beginner-choice,
 html[data-ui-mode="simple"][data-choice-phase="hours"] #discovery-filters{display:none!important}
 html[data-ui-mode="simple"] #availability-step .step-intro, html[data-ui-mode="simple"] #availability-intro, html[data-ui-mode="simple"] #availability-save-confirmation{display:none}
 html[data-ui-mode="simple"] #availability-step #configuration-summary{display:none}
 html[data-ui-mode="pro"] .choice-page-control{display:none!important}
 `;document.head.append(style);
 const next=document.createElement('button');next.type='button';next.className='primary-button choice-page-control';next.textContent='Continuer vers mes horaires';next.id='choice-filters-next';
 $('#discovery-filters').after(next);
 const back=document.createElement('button');back.type='button';back.className='secondary-button choice-page-control';back.textContent='Retour aux filtres';back.id='choice-hours-back';$('.availability-modes').before(back);
 let phase='filters';
 function render(){
  const active=root.dataset.uiMode==='simple' && root.dataset.guidedView==='availability';
  const filters=!$('#discovery-filters').hidden;
  root.dataset.choicePhase=active&&filters?phase:'';
  next.hidden=!(active&&filters&&phase==='filters');back.hidden=!(active&&filters&&phase==='hours');
  if(active&&filters){const title=filters&&phase==='filters'?'Quel filtre utilisez-vous ?':'Quand souhaitez-vous observer ?';if($('#availability-title').textContent!==title)$('#availability-title').textContent=title;}
  const kicker=$('.availability-heading .state-kicker');
  if(active&&filters&&kicker)kicker.textContent=phase==='filters'?'Choisir mon filtre':'Choisir mes horaires';
 }
 next.addEventListener('click',()=>{
  if(!$('#discovery-filter-choices input:checked')){$('#discovery-filter-feedback').textContent=window.nightMeritInstalledFilters?.noFilter?'Vous avez choisi de continuer sans filtre. Pour utiliser cette recherche Hα, déclarez un filtre compatible avec « Déclarer ou modifier mes filtres ».':!$('#discovery-filter-choices input')?'Aucun filtre compatible n’est disponible pour continuer. Une référence non prise en charge ne peut pas servir aux calculs. Vérifiez les références dans « Déclarer ou modifier mes filtres ».':'Sélectionnez un filtre que vous possédez parmi les références proposées pour continuer.';return;}
  phase='hours';render();$('#availability-title').focus();
 });
 back.addEventListener('click',()=>{phase='filters';render();$('#availability-title').focus();});
 new MutationObserver(records=>{if(records.some(r=>r.attributeName==='data-guided-view'))phase='filters';render();}).observe(root,{attributes:true,attributeFilter:['data-guided-view','data-ui-mode']});
 new MutationObserver(()=>{phase='filters';render();}).observe($('#discovery-filters'),{attributes:true,attributeFilter:['hidden']});
 $('#ui-mode').addEventListener('change',()=>{if(typeof renderSimpleEquipment==='function')renderSimpleEquipment();render();});
 const name=$('#site-name');name.setAttribute('aria-describedby','site-name-help');const help=document.createElement('small');help.id='site-name-help';help.textContent='Nom libre : Maison, Jardin, Site de vacances. La position est définie séparément.';name.after(help);

 render();
})();
