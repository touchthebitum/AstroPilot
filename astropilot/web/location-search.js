"use strict";
(() => {
  const query=document.querySelector('#location-query'), button=document.querySelector('#location-search');
  const status=document.querySelector('#location-status'), results=document.querySelector('#location-results');
  let sequence=0;
  query.addEventListener('input',()=>{sequence++;results.replaceChildren();status.textContent='';button.disabled=false;});
  async function search(){
    const name=query.value.trim(), request=++sequence;results.replaceChildren();
    if(name.length<2){status.textContent='Saisissez au moins deux caractères.';return;}
    button.disabled=true;status.textContent='Recherche de la localité…';
    try{
      const response=await fetch('/v1/locations?name='+encodeURIComponent(name),{cache:'no-store'});
      if(!response.ok)throw Error('unavailable');const data=await response.json();if(request!==sequence)return;
      status.textContent=data.results.length?'Choisissez le lieu correspondant :':'Aucun lieu trouvé. Précisez le pays ou saisissez les coordonnées manuellement.';
      for(const place of data.results){
        const choice=document.createElement('button');choice.type='button';choice.className='secondary-button';choice.textContent=place.label;
        choice.addEventListener('click',()=>{
          document.querySelector('#site-latitude').value=place.latitude;
          document.querySelector('#site-longitude').value=place.longitude;
          renderSiteSummary();results.replaceChildren();status.textContent='Lieu choisi : '+place.label+'. Coordonnées approximatives ajoutées ; vous pouvez les corriger manuellement.';
        });results.append(choice);
      }
    }catch(error){if(request===sequence)status.textContent='Recherche indisponible. Réessayez ou saisissez les coordonnées manuellement.';}
    finally{if(request===sequence)button.disabled=false;}
  }
  button.addEventListener('click',search);
  query.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();search();}});
})();
