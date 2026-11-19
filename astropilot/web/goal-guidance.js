"use strict";
// Convert an explicitly entered exposure duration; never choose it for the user.
function goalFrameCount(hours, seconds) {
  if (!Number.isFinite(hours) || hours <= 0 || !Number.isFinite(seconds) || seconds <= 0) return null;
  const count = Math.ceil(hours * 3600 / seconds);
  return Number.isSafeInteger(count) && count > 0 ? count : null;
}
function addProjectGoalGuidance(row, intent, goal, input) {
  const advice = intent.exposure_guidance;
  const box = document.createElement('section');box.className='goal-advice';
  const intro = document.createElement('p');
  const supported = advice && advice.filter_type === intent.filter_type && advice.basis === 'editorial_starting_point'
    && Number.isFinite(advice.min_hours) && advice.min_hours >= 1 && Number.isFinite(advice.max_hours) && advice.max_hours >= advice.min_hours
    && Number.isFinite(advice.suggested_hours) && advice.suggested_hours >= advice.min_hours && advice.suggested_hours <= advice.max_hours;
  if (!supported) {
    intro.textContent='Pas encore de repère documenté pour cette cible et ce filtre. Choisissez un premier objectif, puis ajustez-le après vos premières images.';
    box.append(intro);row.insertBefore(box,goal);return;
  }
  intro.textContent=`Repère indicatif pour commencer : ${advice.min_hours} à ${advice.max_hours} h avec ce filtre, sur une ou plusieurs nuits. Le résultat n’est pas garanti.`;
  const use=document.createElement('button');use.type='button';use.className='primary-button';use.textContent=`Utiliser cet objectif conseillé : ${advice.suggested_hours} h`;
  const manual=document.createElement('button');manual.type='button';manual.className='secondary-button';manual.textContent='Choisir une autre durée';
  const status=document.createElement('p');status.setAttribute('aria-live','polite');
  row.dataset.goalChoice=input.value?'chosen':'pending';
  const choose=()=>{row.dataset.goalChoice='chosen';status.textContent=input.value?`Objectif choisi : ${input.value} h. Vous pourrez le modifier plus tard.`:'';};
  use.addEventListener('click',()=>{input.value=String(advice.suggested_hours);choose();input.dispatchEvent(new Event('input',{bubbles:true}));});
  manual.addEventListener('click',()=>{row.dataset.goalChoice='chosen';input.focus();});
  input.addEventListener('input',choose);
  const details=document.createElement('details');details.className='goal-photo-count';const heading=document.createElement('summary');heading.textContent='Combien de photos prévoir ?';details.append(heading);
  const sourcesDetails=document.createElement('details');sourcesDetails.className='goal-sources';const sourcesHeading=document.createElement('summary');sourcesHeading.textContent='D’où vient ce conseil ?';sourcesDetails.append(sourcesHeading);
  const exposureLabel=document.createElement('label');exposureLabel.className='field';exposureLabel.textContent='Durée prévue d’un cliché (secondes)';
  const exposure=document.createElement('input');exposure.type='number';exposure.min='0.000001';exposure.step='any';exposure.placeholder='Ex. 300';exposureLabel.append(exposure);
  const counts=document.createElement('p');counts.setAttribute('aria-live','polite');
  const update=()=>{
    const seconds=Number(exposure.value),low=goalFrameCount(advice.min_hours,seconds),high=goalFrameCount(advice.max_hours,seconds),chosen=goalFrameCount(Number(input.value),seconds);
    counts.textContent=low===null||high===null?'Indiquez votre durée de pose pour calculer le nombre de clichés conservés. Ce champ ne règle pas votre appareil.':`Repère : ${low} à ${high} clichés conservés de ${seconds} s.`+(chosen===null?'':` Pour votre objectif de ${input.value} h : ${chosen} clichés au total.`)+' Seules les images conservées après le tri comptent ; hors flats, darks et bias.';
  };
  exposure.addEventListener('input',update);input.addEventListener('input',update);update();
  const note=document.createElement('p');note.textContent=advice.note;
  details.append(exposureLabel,counts);sourcesDetails.append(note);
  for(const source of advice.sources||[]){
    if(!/^https:\/\/(www\.)?(hellanebula\.com|starrywonders\.com|astronewton\.com)\//.test(source.url))continue;
    const p=document.createElement('p'),link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.label;p.append(link);sourcesDetails.append(p);
  }
  box.append(intro,use,manual,status,details,sourcesDetails);row.insertBefore(box,goal);
}
(() => {
 const style=document.createElement('style');style.textContent=`
 html[data-ui-mode="pro"] .goal-advice{display:none!important}
 html[data-ui-mode="simple"] fieldset[data-goal-choice="pending"]>.new-intent-goal{display:none!important}
 .goal-photo-count>summary{display:block;padding:1rem;border:2px solid var(--accent,#84d9ca);border-radius:8px;color:var(--accent,#84d9ca);font-weight:700;cursor:pointer;margin:.75rem 0}.goal-photo-count>summary::before{content:"＋ ";}.goal-photo-count[open]>summary::before{content:"− ";}.goal-sources{margin-top:1rem}.goal-advice{margin:1rem 0}.goal-advice button{margin:0 .5rem .5rem 0}
 `;document.head.append(style);
})();
