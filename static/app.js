document.addEventListener('DOMContentLoaded',()=>{
  const drawer=document.getElementById('sidebar'), toggle=document.getElementById('menu-toggle');
  function closeDrawer(){document.body.classList.remove('drawer-open');toggle?.setAttribute('aria-expanded','false');}
  function toggleDrawer(){const open=document.body.classList.toggle('drawer-open');toggle?.setAttribute('aria-expanded',String(open));}
  toggle?.addEventListener('click',toggleDrawer);
  document.getElementById('mobile-more')?.addEventListener('click',toggleDrawer);
  document.getElementById('drawer-shade')?.addEventListener('click',closeDrawer);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDrawer();if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){const search=document.getElementById('global-search');if(search&&getComputedStyle(search.parentElement).display!=='none'){e.preventDefault();search.focus();}}});
  drawer?.querySelectorAll('a').forEach(a=>a.addEventListener('click',closeDrawer));
  document.querySelector('[data-theme-toggle]')?.addEventListener('click',()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=theme;try{localStorage.setItem('tr-theme',theme);}catch(e){}});
  document.querySelector('[data-password-toggle]')?.addEventListener('click',e=>{const inp=document.getElementById('password'), shown=inp.type==='password';inp.type=shown?'text':'password';e.currentTarget.setAttribute('aria-label',shown?'Ocultar senha':'Mostrar senha');});
  document.querySelectorAll('form[data-confirm]').forEach(form=>form.addEventListener('submit',e=>{
    if(form.dataset.confirmed==='yes')return;
    e.preventDefault();const d=document.createElement('dialog'),title=document.createElement('h3'),p=document.createElement('p'),buttons=document.createElement('div'),cancel=document.createElement('button'),confirm=document.createElement('button');
    title.textContent='Confirmar exclusão';p.textContent=form.dataset.confirm;buttons.className='form-actions';cancel.className='btn secondary';cancel.type='button';cancel.textContent='Cancelar';confirm.className='btn';confirm.type='button';confirm.textContent='Sim, excluir';buttons.append(cancel,confirm);d.append(title,p,buttons);document.body.append(d);d.showModal();cancel.focus();cancel.onclick=()=>d.close();confirm.onclick=()=>{form.dataset.confirmed='yes';d.close();form.requestSubmit();};d.addEventListener('close',()=>d.remove());
  }));
});
