"use strict";
// Inventory is explicitly declared, never detected from or sent to hardware.
async function loadFilterInventoryForDiscovery(equipment) {
  const status=document.querySelector('#wheel-inventory-summary');
  try {
    const response=await fetch('/v1/filter-inventory',{cache:'no-store'});
    if(!response.ok)throw Error('load');
    const data=await response.json(),inventory=data.inventories[equipment];
    window.nightMeritInstalledFilters={equipment,noFilter:inventory?.wheel_name==='Aucun filtre' && inventory.slots.length===0,ids:inventory?inventory.slots.filter(s=>s.filter_profile_id).map(s=>s.filter_profile_id):null};
    if(status)status.textContent=window.nightMeritInstalledFilters.noFilter?'Vous avez choisi « Aucun filtre ». La recherche nécessite un filtre compatible. Vous pouvez en déclarer un avec « Déclarer ou modifier mes filtres ».':inventory?`${inventory.wheel_name} : ${inventory.slots.length} filtre(s) déclaré(s). Seuls les filtres compatibles proposés ci-dessous peuvent servir à la recherche. La découverte couvre les nébuleuses Hα prises en charge et la Rosette en OIII/SII.`:'Vous pouvez déclarer vos filtres pour les retrouver lors des prochaines recherches.';
  } catch(error) {
    window.nightMeritInstalledFilters={equipment,ids:[]};
    if(status)status.textContent='Impossible de lire les filtres enregistrés. Réessayez avant de rechercher une cible.';
  }
}
(() => {
  const fieldset=document.querySelector('#discovery-filters');
  const summary=document.createElement('p');summary.id='wheel-inventory-summary';
  const open=document.createElement('button');open.type='button';open.className='secondary-button';open.textContent='Déclarer ou modifier mes filtres';
  fieldset.insertBefore(open,fieldset.querySelector('#discovery-filter-choices'));open.after(summary);
  const menu=open.cloneNode(true);menu.textContent='Ma roue et mes filtres';document.querySelector('.header-options-content').append(menu);
  const dialog=document.createElement('dialog');dialog.className='wheel-inventory-dialog';dialog.setAttribute('aria-label','Mes filtres');document.body.append(dialog);
  const el=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e;};
  const field=(text,input)=>{const label=el('label',text);label.className='field';label.append(input);return label;};
  let busy=false;
  async function show({initial=false}={}){
    if(busy)return;
    if(!state.configuration?.configured || !configurationDraftMatchesSaved()){
      alert('Enregistrez d’abord votre site et votre matériel. Les filtres seront associés à ce matériel.');return;
    }
    busy=true;open.disabled=menu.disabled=true;
    try {
      const response=await fetch('/v1/filter-inventory',{cache:'no-store'});if(!response.ok)throw Error('read');
      const data=await response.json(),equipment=state.configuration.active_equipment_id;
      const original=data.inventories[equipment];
      const mountOf=inventory=>inventory?.wheel_name==='Filtre monté seul'?'single':inventory?.wheel_name==='Aucun filtre'?'none':'wheel';
      const variants={...(data.mount_inventories?.[equipment]||{})};
      if(original)variants[mountOf(original)]=original;
      dialog.replaceChildren();
      const storedSingle=original?.wheel_name==='Filtre monté seul';
      const title=el('h2',initial?'Comment utilisez-vous vos filtres ?':storedSingle?'Mon filtre monté seul':original?.wheel_name==='Aucun filtre'?'Déclarer mes filtres':'Les filtres de ma roue');
      dialog.append(title,el('p','Indiquez les filtres installés pour ce matériel. NightMerit mémorise votre déclaration, sans détecter ni commander le matériel.'));
      const material=(state.configuration.available_equipment||[]).find(e=>e.id===equipment);
      dialog.append(el('p',`Matériel concerné : ${material?.name||equipment}`));
      const wheel=el('input');wheel.value=original?.wheel_name||'Ma roue à filtres';wheel.maxLength=120;wheel.placeholder='Ex. ZWO EFW 7 × 36 mm';
      const number=el('input');number.type='number';number.min='1';number.max='20';number.value=String(original?.slot_count||7);
      const wheelField=field('Nom ou modèle de la roue',wheel), countField=field('Nombre d’emplacements',number);
      dialog.append(wheelField,countField);
      let slotPage=1, paged=false;
      let mounting=storedSingle?'single':original?.wheel_name==='Aucun filtre'?'none':'wheel';
      const rows=el('div');dialog.append(rows);
      const error=el('p');error.setAttribute('role','alert');
      let values=new Map((original?.slots||[]).map(slot=>[slot.position,slot]));
      const controls=[];
      function capture(){for(const c of controls){if(c.select.value==='')values.delete(c.position);else {const ref=data.references.find(r=>r.id===c.select.value);values.set(c.position,ref?{position:c.position,label:ref.label,filter_type:ref.filter_type,bandwidth_nm:ref.bandwidth_nm,filter_profile_id:ref.id}:{position:c.position,label:c.name.value.trim(),filter_type:c.type.value,...(c.width.value?{bandwidth_nm:Number(c.width.value)}:{})});}}}
      function render(){
        capture();const count=Number(number.value);
        if(!Number.isInteger(count)||count<1||count>20){error.textContent='Indiquez entre 1 et 20 emplacements.';return;}
        if([...values.keys()].some(p=>p>count)){error.textContent='Un filtre est déclaré au-delà de ce nombre. Videz cet emplacement avant de réduire la roue.';return;}
        error.textContent='';rows.replaceChildren();controls.length=0;
        for(let position=1;position<=count;position++){
          const old=values.get(position),group=el('fieldset'),legend=el('legend',mounting==='single'?'Mon filtre':`Emplacement ${position}`);group.append(legend);
          const select=el('select');select.append(new Option('Vide / aucun filtre déclaré',''));
          for(const ref of data.references)select.append(new Option(ref.label,ref.id));
          select.append(new Option('Autre référence / non prise en charge','other'));select.value=old?.filter_profile_id||(old?'other':'');
          group.append(field(mounting==='single'?'Référence du filtre':`Filtre de l’emplacement ${position}`,select));
          const custom=el('div'),name=el('input'),type=el('select'),width=el('input');name.maxLength=120;name.value=old?.label||'';
          for(const [v,label] of [['Ha','Hα'],['OIII','OIII'],['SII','SII'],['L','Luminance'],['R','Rouge'],['G','Vert'],['B','Bleu'],['dual_band','Double bande'],['other','Autre / inconnu']])type.append(new Option(label,v));
          type.value=old?.filter_type||'other';width.type='number';width.min='.001';width.max='1000';width.step='any';width.value=old?.bandwidth_nm?String(old.bandwidth_nm):'';
          custom.append(field(mounting==='single'?'Marque et modèle':`Marque et modèle — emplacement ${position}`,name),field(mounting==='single'?'Type':`Type — emplacement ${position}`,type),field(mounting==='single'?'Largeur en nm, si connue':`Largeur en nm, si connue — emplacement ${position}`,width),el('p','Ce filtre sera mémorisé, mais ne sera pas utilisé dans les calculs tant que cette référence n’est pas prise en charge. Ne choisissez pas une référence ressemblante.'));
          custom.hidden=select.value!=='other';select.addEventListener('change',()=>custom.hidden=select.value!=='other');group.append(custom);rows.append(group);controls.push({position,select,name,type,width});
        }
      }
      const pager=el('div');pager.className='wheel-slot-pager';
      const previous=el('button','Emplacement précédent'),progress=el('p'),following=el('button','Emplacement suivant');
      previous.type=following.type='button';previous.className=following.className='secondary-button';
      pager.append(progress,previous,following);pager.hidden=true;dialog.append(pager);
      function updatePage(){
        if(!paged)return;
        const count=Number(number.value);slotPage=Math.max(1,Math.min(slotPage,count));
        [...rows.children].forEach((row,i)=>row.hidden=i+1!==slotPage);
        wheelField.hidden=countField.hidden=slotPage!==1;
        progress.textContent=`Filtre de la roue · emplacement ${slotPage} sur ${count}`;
        previous.hidden=slotPage===1;following.hidden=slotPage===count;
        save.hidden=slotPage!==count;
      }
      function moveSlot(delta){capture();slotPage+=delta;updatePage();progress.tabIndex=-1;progress.focus();dialog.scrollTop=0;}
      previous.addEventListener('click',()=>moveSlot(-1));following.addEventListener('click',()=>moveSlot(1));
      number.addEventListener('change',()=>{render();updatePage();});render();
      dialog.append(el('p','Les filtres déclarés sont mémorisés pour ce matériel. Pour chercher automatiquement une cible, cette bêta utilise les références compatibles Hα, ainsi que OIII et SII pour la Rosette uniquement. L, R, G et B restent mémorisés dans votre inventaire sans être utilisés pour la découverte. NightMerit ne détecte ni ne commande la roue.'),error);
      const save=el('button',storedSingle?'Enregistrer mon filtre':'Enregistrer les filtres de cette roue');save.type='button';save.className='primary-button';
      const cancel=el('button','Fermer sans enregistrer');cancel.type='button';cancel.className='secondary-button';cancel.addEventListener('click',()=>{dialog.close();});
      save.addEventListener('click',async()=>{
        capture();const count=Number(number.value),slots=[...values.values()].sort((a,b)=>a.position-b.position);
        if(initial&&mounting!=='none'&&!slots.length){error.textContent='Déclarez au moins un filtre, ou revenez au montage pour choisir Aucun filtre.';return;}
        if(!wheel.value.trim()||!Number.isInteger(count)||count<1||count>20||slots.some(s=>s.position>count||!s.label||s.bandwidth_nm!==undefined&&(!Number.isFinite(s.bandwidth_nm)||s.bandwidth_nm<=0||s.bandwidth_nm>1000))){error.textContent='Vérifiez le nom de la roue, les emplacements et les références renseignées.';return;}
        if(equipment!==state.configuration.active_equipment_id){error.textContent='Le matériel a changé. Fermez puis rouvrez cet écran.';return;}
        save.disabled=true;
        try{
          const result=await fetch('/v1/filter-inventory',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:data.profile_revision,equipment_id:equipment,inventory:{wheel_name:wheel.value.trim(),slot_count:count,slots}})});
          const saved=await result.json();if(!result.ok){error.textContent=result.status===409?'Le profil a changé dans une autre fenêtre. Fermez, actualisez puis rouvrez cet écran. Aucun changement de filtres enregistré.':'Les filtres n’ont pas pu être enregistrés. Vérifiez les informations.';return;}
          // Only advance a matching local revision; never bless unrelated stale drafts.
          if(state.configuration.profile_revision===data.profile_revision)state.configuration.profile_revision=saved.profile_revision;
          dialog.close();if(initial){if(renderProjects())setView('projects');return;}if(state.discoveryMode)await setDiscoveryMode(true);else await loadFilterInventoryForDiscovery(equipment);
        }catch(error2){error.textContent='Réponse interrompue. Fermez puis rouvrez cet écran pour vérifier si les filtres ont été enregistrés.';}finally{save.disabled=false;}
      });
      dialog.append(save,cancel);
      if(initial){
        dialog.classList.add('initial-filter-setup');
        const instructions=dialog.querySelector('h2+p');
        instructions.textContent='Choisissez votre montage. Vous indiquerez les filtres sur la page suivante.';
        const choices=el('div'), next=el('button','Continuer vers les filtres disponibles');next.type='button';next.className='primary-button';
        for(const [value,label] of [['wheel','Une roue à filtres'],['single','Un filtre monté seul'],['none','Aucun filtre']]){
          const radio=el('input');radio.type='radio';radio.name='initial-filter-mounting';radio.value=value;radio.checked=!!original&&mounting===value;
          radio.addEventListener('change',()=>{mounting=value;next.disabled=false;});const option=el('label');option.className='filter-mounting-choice';option.append(radio,el('span',label));choices.append(option);
        }
        next.disabled=!original;
        const details=[wheelField,countField,rows,pager,error,save,cancel,...[...dialog.children].filter(e=>e.tagName==='P')];
        for(const node of details)node.hidden=true;
        instructions.hidden=false;dialog.append(choices,next);
        next.addEventListener('click',()=>{
          choices.hidden=next.hidden=true;
          for(const node of details)node.hidden=false;
          title.textContent=mounting==='wheel'?'Quels filtres sont installés dans votre roue ?':mounting==='single'?'Quel filtre utilisez-vous ?':'Continuer sans filtre';
          instructions.textContent=mounting==='none'?'Aucun filtre ne sera déclaré pour ce matériel. La découverte de cette bêta nécessite un filtre compatible.':'Choisissez uniquement les références installées. Une référence inconnue peut être mémorisée sans être utilisée dans les calculs.';
          const restored=variants[mounting];
          values=new Map((restored?.slots||[]).map(slot=>[slot.position,slot]));controls.length=0;
          number.value=String(restored?.slot_count||(mounting==='wheel'?7:1));
          wheel.value=restored?.wheel_name||(mounting==='single'?'Filtre monté seul':mounting==='none'?'Aucun filtre':'Ma roue à filtres');
          render();wheelField.hidden=countField.hidden=mounting!=='wheel';rows.hidden=mounting==='none';
          paged=mounting==='wheel';slotPage=1;pager.hidden=!paged;updatePage();
          save.textContent='Enregistrer et continuer vers le choix de cible';
          const back=el('button','Retour au montage');back.type='button';back.className='secondary-button';dialog.append(back);
          back.addEventListener('click',()=>{capture();variants[mounting]={wheel_name:wheel.value,slot_count:Number(number.value),slots:[...values.values()]};paged=false;back.remove();for(const node of details)node.hidden=true;instructions.hidden=false;choices.hidden=next.hidden=false;title.textContent='Comment utilisez-vous vos filtres ?';});
          title.tabIndex=-1;title.focus();dialog.scrollTop=0;
        });
        cancel.textContent='Retour à la caméra';cancel.onclick=()=>{dialog.close();setView('equipment');simpleEquipmentPhase='camera';renderSimpleEquipment();};
        dialog.oncancel=event=>{event.preventDefault();cancel.click();};
      } else {dialog.classList.remove('initial-filter-setup');dialog.oncancel=null;if(storedSingle){wheelField.hidden=countField.hidden=true;}}
      dialog.showModal();
    }catch(error){alert('Impossible de charger les filtres. Aucun changement effectué.');}
    finally{busy=false;open.disabled=menu.disabled=false;}
  }
  open.addEventListener('click',()=>show());menu.addEventListener('click',()=>show());
  window.configureInitialFilters=()=>show({initial:true});
  const css=el('style');css.textContent='.wheel-inventory-dialog{max-width:720px;width:90vw;max-height:85vh;overflow:auto;background:#0d1e27;color:#e0eeee;border:1px solid #56727b;border-radius:12px;padding:1.5rem}.wheel-inventory-dialog fieldset{margin:1rem 0;padding:1rem}.wheel-inventory-dialog input,.wheel-inventory-dialog select{width:100%;box-sizing:border-box}body.layout-nightline .wheel-inventory-dialog .filter-mounting-choice,.wheel-inventory-dialog .filter-mounting-choice{display:flex;align-items:center;gap:12px;padding:14px;margin:10px 0;border:1px solid #56727b;border-radius:9px;cursor:pointer;min-height:48px;box-sizing:border-box}.wheel-inventory-dialog .filter-mounting-choice:has(input:checked){background:#173d3b;border-color:#83d8cc}body.layout-nightline .wheel-inventory-dialog .filter-mounting-choice>input[type=radio],.wheel-inventory-dialog .filter-mounting-choice>input[type=radio]{appearance:auto;display:block;flex:0 0 22px;width:22px;height:22px;min-width:22px;min-height:22px;max-width:22px;max-height:22px;padding:0;margin:0;accent-color:#83d8cc}.wheel-inventory-dialog .filter-mounting-choice>span{line-height:1.4}.wheel-inventory-dialog.initial-filter-setup{max-width:720px}.wheel-inventory-dialog button{margin:.5rem .5rem .5rem 0}';document.head.append(css);
})();
