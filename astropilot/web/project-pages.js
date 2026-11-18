"use strict";
(() => {
 const $=s=>document.querySelector(s),root=document.documentElement,fields=$('#project-create-fields');
 let page='duration',key='', priorSignature='', reviewed='', draft=null;
 const selectedRows=()=>[...document.querySelectorAll('#project-new-intents fieldset[data-new-intent-id]')].filter(row=>row.querySelector('input[type="checkbox"]').checked);
 const signature=()=>JSON.stringify([key,selectedRows().map(row=>[row.dataset.newIntentId,row.querySelector('[data-target-hours]').value])]);
 const title=document.createElement('h3');title.id='project-choice-title';title.tabIndex=-1;fields.prepend(title);
 const target=document.createElement('p');target.id='project-current-target';target.className='field-note';title.after(target);
 const note=document.createElement('p');note.textContent='Sur une ou plusieurs nuits. Vous pourrez modifier cet objectif plus tard.';title.after(note);
 const next=document.createElement('button');next.id='project-duration-next';next.type='button';next.className='primary-button';next.textContent='Continuer';$('#project-add').before(next);
 const back=document.createElement('button');back.id='project-duration-back';back.type='button';back.className='secondary-button';back.textContent='Retour à la durée';$('#project-add').before(back);
 const existing=document.createElement('button');existing.type='button';existing.id='project-existing-images';existing.className='secondary-button';existing.textContent='Oui, j’ai déjà des images';$('#project-new-empty').closest('label').after(existing);
 const prior=document.createElement('section');prior.id='project-initial-images';prior.hidden=true;existing.after(prior);
 const priorNote=document.createElement('p');priorNote.textContent='Indiquez uniquement les clichés conservés de cette cible, avec ce filtre, avant de commencer ce suivi. Ne reprenez pas des poses déjà comptées dans un autre profil : utilisez alors sa sauvegarde.';prior.append(priorNote);
 const priorRows=document.createElement('div');prior.append(priorRows);
 const reviewButton=document.createElement('button');reviewButton.type='button';reviewButton.className='primary-button';reviewButton.textContent='Vérifier mes images';prior.append(reviewButton);
 const summary=document.createElement('section');summary.id='project-initial-review';summary.hidden=true;prior.after(summary);
 const reviewText=document.createElement('p');summary.append(reviewText);
 const consentLabel=document.createElement('label');const consent=document.createElement('input');consent.type='checkbox';consent.id='project-initial-confirm';consentLabel.append(consent,document.createTextNode(' J’ai vérifié ces images antérieures et je confirme leur ajout au projet.'));summary.append(consentLabel);
 const edit=document.createElement('button');edit.type='button';edit.className='secondary-button';edit.textContent='Corriger mes images';summary.append(edit);
 function clearPrior(){priorRows.replaceChildren();priorSignature='';reviewed='';consent.checked=false;}
 function preparePrior(){
  const sig=signature();if(sig===priorSignature)return;clearPrior();priorSignature=sig;
  for(const row of selectedRows()){
   const group=document.createElement('fieldset');group.dataset.initialIntentId=row.dataset.newIntentId;
   const legend=document.createElement('legend');legend.textContent=row.querySelector('legend').textContent;group.append(legend);
   for(const [name,label] of [['frames','Nombre de clichés conservés'],['seconds','Durée de chaque cliché (secondes)']]){
    const wrap=document.createElement('label');wrap.className='field';wrap.textContent=label;const input=document.createElement('input');input.type='number';input.min=name==='frames'?'1':'0.000001';input.step=name==='frames'?'1':'any';input.dataset.initialField=name;wrap.append(input);group.append(wrap);
   }priorRows.append(group);
  }
 }
 function readPrior(){return [...priorRows.querySelectorAll('fieldset')].map(row=>{
  const frames=Number(row.querySelector('[data-initial-field="frames"]').value),seconds=Number(row.querySelector('[data-initial-field="seconds"]').value);
  if(!Number.isSafeInteger(frames)||frames<1||!Number.isFinite(seconds)||seconds<=0||!Number.isFinite(frames*seconds)||frames*seconds>Number.MAX_SAFE_INTEGER/1000000)throw new Error('Indiquez un nombre entier de clichés et leur durée positive en secondes.');
  return {acquisition_intent_id:row.dataset.initialIntentId,acquired_frames:frames,exposure_seconds:seconds};
 });}
 function fail(error){const feedback=$('#project-create-feedback');feedback.classList.add('error');feedback.textContent=error.message;}
 window.readInitialProjectImages=()=>{
  if(page!=='review')return null;
  const progress=readPrior();if(!consent.checked||reviewed!==JSON.stringify(progress)||priorSignature!==signature()||draft!==(typeof state==='undefined'?null:state.configurationDraft))throw new Error('Vérifiez le récapitulatif et confirmez vos images antérieures.');
  return {confirmed:true,progress};
 };
 reviewButton.addEventListener('click',()=>{try{
  const progress=readPrior();if(!progress.length)throw new Error('Indiquez vos clichés conservés.');
  reviewed=JSON.stringify(progress);consent.checked=false;
  const seconds=progress.reduce((sum,item)=>sum+item.acquired_frames*item.exposure_seconds,0);const hours=selectedRows().reduce((sum,row)=>sum+Number(row.querySelector('[data-target-hours]').value),0);
  reviewText.textContent=progress.map((item,index)=>priorRows.children[index].querySelector('legend').textContent+' : '+item.acquired_frames+' clichés × '+item.exposure_seconds+' s').join(' ; ')+'. Total antérieur : '+progressDuration(seconds)+'. Objectif total : '+hours+' h. Reste à acquérir : '+progressDuration(Math.max(0,hours*3600-seconds))+'. Aucune séance photo ne sera créée.';
  page='review';$('#project-create-feedback').textContent='';render();title.focus();
 }catch(error){fail(error);}});
 edit.addEventListener('click',()=>{consent.checked=false;page='prior';render();title.focus();});
 const cancel=document.createElement('button');cancel.id='project-choice-cancel';cancel.type='button';cancel.className='secondary-button';cancel.textContent='Retour à mes projets';$('#project-add').after(cancel);cancel.addEventListener('click',()=>{clearPrior();page='duration';$('#project-create').open=false;render();$('#projects-title').focus();});
 const style=document.createElement('style');style.textContent=`
 html[data-ui-mode="simple"][data-project-page="duration"] #simple-projects,
 html[data-ui-mode="simple"][data-project-page="images"] #simple-projects,
 html[data-ui-mode="simple"][data-project-page="target"] #simple-projects,
 html[data-ui-mode="simple"][data-project-page="duration"] #projects-step>.discovery-entry,
 html[data-ui-mode="simple"][data-project-page="images"] #projects-step>.discovery-entry,
 html[data-ui-mode="simple"][data-project-page="target"] #projects-step>.discovery-entry{display:none!important}
 html[data-ui-mode="simple"][data-project-page="duration"] #projects-title,
 html[data-ui-mode="simple"][data-project-page="images"] #projects-title,
 html[data-ui-mode="simple"][data-project-page="duration"] #projects-step>.step-intro,
 html[data-ui-mode="simple"][data-project-page="images"] #projects-step>.step-intro,
 html[data-ui-mode="simple"][data-project-page="duration"] #discover-from-projects,
 html[data-ui-mode="simple"][data-project-page="images"] #discover-from-projects,
 html[data-ui-mode="simple"][data-project-page="duration"] #discover-from-projects+p,
 html[data-ui-mode="simple"][data-project-page="images"] #discover-from-projects+p,
 html[data-ui-mode="simple"][data-project-page="duration"] #beginner-manual-project,
 html[data-ui-mode="simple"][data-project-page="images"] #beginner-manual-project,
 html[data-ui-mode="simple"] #project-create>summary,
 html[data-ui-mode="simple"] #project-create>p:not(.error),
 html[data-ui-mode="simple"] #project-create>.equipment-filter-help,
 html[data-ui-mode="simple"] #project-target-guidance,
 html[data-ui-mode="simple"] #project-new-intents fieldset>p,
 html[data-ui-mode="simple"] #project-new-intents fieldset>details{display:none!important}
 html[data-ui-mode="simple"][data-project-page="duration"] #project-new-empty-wrap,
 html[data-ui-mode="simple"][data-project-page="duration"] #project-existing-images,
 html[data-ui-mode="simple"][data-project-page="duration"] #project-existing-note,
 html[data-ui-mode="simple"][data-project-page="duration"] #project-add,
 html[data-ui-mode="simple"][data-project-page="duration"] #project-duration-back{display:none!important}
 html[data-ui-mode="simple"][data-project-page="images"] #project-new-intents,
 html[data-ui-mode="simple"][data-project-page="images"] #project-duration-next{display:none!important}
 html[data-ui-mode="simple"] #project-create-fields>label[for="project-template"],
 html[data-ui-mode="simple"] #project-create-fields>#project-template{display:none!important}
 html[data-ui-mode="simple"][data-project-page="target"] #project-create-fields>label[for="project-template"],
 html[data-ui-mode="simple"][data-project-page="target"] #project-template{display:block!important}
 html[data-ui-mode="simple"][data-project-page="target"] #project-new-intents,
 html[data-ui-mode="simple"][data-project-page="target"] #project-new-empty-wrap,
 html[data-ui-mode="simple"][data-project-page="target"] #project-existing-images,
 html[data-ui-mode="simple"][data-project-page="target"] #project-add{display:none!important}
 html[data-ui-mode="pro"] #project-choice-cancel,html[data-ui-mode="pro"] #project-current-target,html[data-ui-mode="pro"] #project-choice-title,html[data-ui-mode="pro"] #project-choice-title+p,
 html[data-ui-mode="pro"] #project-duration-next,html[data-ui-mode="pro"] #project-duration-back,
 html[data-ui-mode="pro"] #project-existing-images,html[data-ui-mode="pro"] #project-existing-note{display:none!important}
 `;
 style.textContent+=`html[data-ui-mode="pro"] #project-initial-images,html[data-ui-mode="pro"] #project-initial-review{display:none!important}`;
 style.textContent+=`html[data-ui-mode="simple"][data-project-page="prior"] #simple-projects,html[data-ui-mode="simple"][data-project-page="prior"] #projects-step>.discovery-entry,html[data-ui-mode="simple"][data-project-page="prior"] #projects-title,html[data-ui-mode="simple"][data-project-page="prior"] #projects-step>.step-intro,html[data-ui-mode="simple"][data-project-page="prior"] #project-new-intents,html[data-ui-mode="simple"][data-project-page="prior"] #project-duration-next{display:none!important}`;
 style.textContent+=`html[data-ui-mode="simple"][data-project-page="prior"] #project-new-empty-wrap,html[data-ui-mode="simple"][data-project-page="prior"] #project-existing-images,html[data-ui-mode="simple"][data-project-page="prior"] #project-add{display:none!important}`;
 style.textContent+=`html[data-ui-mode="simple"][data-project-page="review"] #simple-projects,html[data-ui-mode="simple"][data-project-page="review"] #projects-step>.discovery-entry,html[data-ui-mode="simple"][data-project-page="review"] #projects-title,html[data-ui-mode="simple"][data-project-page="review"] #projects-step>.step-intro,html[data-ui-mode="simple"][data-project-page="review"] #project-new-intents,html[data-ui-mode="simple"][data-project-page="review"] #project-duration-next,html[data-ui-mode="simple"][data-project-page="review"] #project-new-empty-wrap,html[data-ui-mode="simple"][data-project-page="review"] #project-existing-images{display:none!important}`;
 document.head.append(style);
 $('#project-new-empty').closest('label').id='project-new-empty-wrap';
 function render(){
  const simple=root.dataset.uiMode==='simple';const current=$('#project-template').value;
  const currentDraft=typeof state==='undefined'?null:state.configurationDraft;if(draft!==currentDraft){draft=currentDraft;clearPrior();page='duration';}
  if(current!==key){key=current;page=current?'duration':'target';clearPrior();}
  root.dataset.projectPage=simple && $('#project-create').open && !fields.hidden?(current?page:'target'):'';
  const text=page==='prior'?'Quelles images avez-vous déjà ?':page==='review'?'Vérifiez vos images avant de confirmer':page==='images'?'Avez-vous déjà des images ?':(current?'Combien de temps souhaitez-vous accumuler ?':'Quelle cible souhaitez-vous photographier ?');
  if(title.textContent!==text)title.textContent=text;
  const select=$('#project-template');const label=select.selectedOptions?.[0]?.textContent||current;
  const targetText=current?'Cible choisie : '+label:'';if(target.textContent!==targetText)target.textContent=targetText;target.hidden=!simple||!current;
  note.hidden=!simple||page!=='duration'||!current;
  prior.hidden=!simple||page!=='prior';summary.hidden=!simple||page!=='review';
  next.hidden=!simple||page!=='duration';back.hidden=!simple||!['images','prior','review'].includes(page);existing.hidden=!simple||page!=='images';
 }
 next.addEventListener('click',()=>{
  const rows=[...document.querySelectorAll('#project-new-intents fieldset[data-new-intent-id]')];
  const selected=rows.filter(row=>row.querySelector('input[type="checkbox"]').checked);
  if(!$('#project-template').value||!selected.length){$('#project-create-feedback').classList.add('error');$('#project-create-feedback').textContent='Choisissez votre cible et confirmez le filtre que vous possédez.';return;}
  if(selected.some(row=>{const n=Number(row.querySelector('[data-target-hours]').value);return !Number.isFinite(n)||n<1;})){$('#project-create-feedback').classList.add('error');$('#project-create-feedback').textContent='Indiquez au moins 1 heure pour chaque filtre choisi.';return;}
  page='images';clearPrior();$('#project-create-feedback').textContent='';render();title.focus();
 });
 back.addEventListener('click',()=>{page='duration';render();title.focus();});
 existing.addEventListener('click',()=>{$('#project-new-empty').checked=false;preparePrior();page='prior';render();title.focus();});
 $('#project-new-empty').addEventListener('change',()=>{clearPrior();});
 new MutationObserver(render).observe(fields,{attributes:true,attributeFilter:['hidden']});
 new MutationObserver(render).observe($('#project-new-intents'),{childList:true});
 $('#project-template').addEventListener('change',render);
 $('#project-create').addEventListener('toggle',render);
 new MutationObserver(render).observe(root,{attributes:true,attributeFilter:['data-ui-mode','data-guided-view']});
 render();
})();
