document.addEventListener('DOMContentLoaded',()=>{
  const raw=document.getElementById('order-data');if(!raw)return;
  const data=JSON.parse(raw.textContent), tbody=document.getElementById('order-items');
  const fmt=n=>new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(n);
  const num=v=>Math.max(0,Number(v)||0), power=n=>10n**BigInt(n);
  // Decimal exato e arredondamento HALF_UP, como no servidor.
  function decimal(v){let s=String(v||'0').replace(',','.');if(!/^\d*(\.\d*)?$/.test(s))s=num(v).toFixed(8);const [whole='0',frac='']=s.split('.');return{n:BigInt((whole||'0')+frac),s:frac.length};}
  function add(a,b){const s=Math.max(a.s,b.s);return{n:a.n*power(s-a.s)+b.n*power(s-b.s),s};}
  function multiply(a,b){return{n:a.n*b.n,s:a.s+b.s};}
  function cents(a){if(a.s<=2)return a.n*power(2-a.s);const p=power(a.s-2);return(a.n+p/2n)/p;}
  function calculate(){let parts={n:0n,s:0};tbody.querySelectorAll('tr').forEach(tr=>{const qty=decimal(tr.querySelector('[name="qty[]"]').value),price=decimal(tr.querySelector('[name="unit[]"]').value),sub=multiply(qty,price);tr.querySelector('[data-subtotal]').textContent=fmt(Number(cents(sub))/100);parts=add(parts,sub);});const labor=decimal(document.getElementById('labor').value),gross=cents(add(parts,labor)),pct=decimal(Math.min(100,num(document.getElementById('discount').value))),disc=cents({n:gross*pct.n,s:pct.s+4});for(const [key,val] of Object.entries({parts:cents(parts),labor:cents(labor),gross,discount:disc,total:gross-disc}))document.getElementById('sum-'+key).textContent=fmt(Number(val)/100);document.getElementById('item-empty').classList.toggle('hidden',tbody.children.length>0);}
  function addItem(desc='',qty=1,unit=0){
    const tr=document.createElement('tr'),descCell=document.createElement('td'),descInput=document.createElement('input');descInput.name='desc[]';descInput.className='desc-field';descInput.value=desc;descInput.placeholder='Descrição do item';descInput.required=true;descInput.setAttribute('aria-label','Descrição do item');descCell.append(descInput);tr.append(descCell);
    for(const [name,value] of [['qty[]',qty],['unit[]',unit]]){const td=document.createElement('td'),input=document.createElement('input');input.className='field';input.type='number';input.step='0.01';input.min=name==='qty[]'?'0.01':'0';input.name=name;input.value=value;input.required=true;input.setAttribute('aria-label',name==='qty[]'?'Quantidade':'Preço unitário');td.append(input);tr.append(td);}
    const sub=document.createElement('td');sub.className='right money';sub.dataset.subtotal='';tr.append(sub);const del=document.createElement('td'),button=document.createElement('button');button.type='button';button.className='remove-item';button.textContent='×';button.title='Remover item';button.setAttribute('aria-label','Remover item');button.onclick=()=>{tr.remove();calculate();};del.append(button);tr.append(del);tr.addEventListener('input',calculate);tbody.append(tr);calculate();return descInput;
  }
  for(const i of data.items)addItem(i.description,i.qty,i.unit_price);
  document.getElementById('add-manual').onclick=()=>addItem().focus();
  document.getElementById('add-stock').onclick=()=>{const inp=document.getElementById('find-stock'),selected=data.stock.find(s=>s.name+' · #'+s.id===inp.value);if(!selected){inp.setCustomValidity('Selecione uma peça da lista.');inp.reportValidity();return;}const q=document.getElementById('stock-qty');if(!q.checkValidity()){q.reportValidity();return;}addItem(selected.name,num(q.value),selected.price);inp.value='';q.value=1;};
  document.getElementById('find-stock').addEventListener('input',e=>e.target.setCustomValidity(''));
  document.getElementById('labor').addEventListener('input',calculate);document.getElementById('discount').addEventListener('input',calculate);
  const cid=document.getElementById('client-id'),clientName=document.getElementById('client-name'),clientPhone=document.getElementById('client-phone'),picker=document.getElementById('vehicle-picker');
  function fillVehicles(){picker.replaceChildren();const initial=document.createElement('option');initial.value='';initial.textContent='Selecione ou informe abaixo';picker.append(initial);for(const v of data.vehicles.filter(v=>String(v.client_id)===cid.value)){const opt=document.createElement('option');opt.value=String(v.id);opt.textContent=(v.plate||'Sem placa')+' · '+(v.model||'Sem modelo');picker.append(opt);}}
  document.getElementById('find-client').addEventListener('change',e=>{const c=data.clients.find(c=>c.name+' · #'+c.id===e.target.value);if(!c)return;cid.value=c.id;clientName.value=c.name;clientPhone.value=c.phone||'';fillVehicles();});
  document.getElementById('new-client-mode').onclick=()=>{cid.value='';document.getElementById('find-client').value='';clientName.value='';clientPhone.value='';document.getElementById('plate').value='';document.getElementById('model').value='';fillVehicles();clientName.focus();};
  picker.addEventListener('change',()=>{const v=data.vehicles.find(v=>String(v.id)===picker.value);if(v){document.getElementById('plate').value=v.plate||'';document.getElementById('model').value=v.model||'';}});
  document.getElementById('plate').addEventListener('input',e=>{const p=e.target.selectionStart;e.target.value=e.target.value.toUpperCase();if(p!==null)e.target.setSelectionRange(p,p);});
  const form=document.getElementById('order-form');form.addEventListener('submit',()=>{const b=form.querySelector('button[type="submit"]');b.disabled=true;b.textContent='Salvando…';});
  fillVehicles();calculate();
});
