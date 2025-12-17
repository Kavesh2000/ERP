// Minimal IndexedDB wrapper for offline outbox
(function(){
  const DB_NAME = 'water-erp-offline';
  const STORE = 'outbox';
  const VERSION = 1;
  let db;

  function openDB(){
    return new Promise((resolve, reject) => {
      if(db) return resolve(db);
      const req = indexedDB.open(DB_NAME, VERSION);
      req.onupgradeneeded = (e) => {
        const d = e.target.result;
        if(!d.objectStoreNames.contains(STORE)){
          d.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        }
      };
      req.onsuccess = (e) => { db = e.target.result; resolve(db); };
      req.onerror = (e) => reject(e.target.error);
    });
  }

  async function save(item){
    const d = await openDB();
    return new Promise((resolve,reject)=>{
      const tx = d.transaction(STORE,'readwrite');
      const s = tx.objectStore(STORE);
      const r = s.add({payload: item, created_at: new Date().toISOString()});
      r.onsuccess = ()=> resolve(r.result);
      r.onerror = ()=> reject(r.error);
    });
  }

  async function all(){
    const d = await openDB();
    return new Promise((resolve,reject)=>{
      const tx = d.transaction(STORE,'readonly');
      const s = tx.objectStore(STORE);
      const req = s.getAll();
      req.onsuccess = ()=> resolve(req.result);
      req.onerror = ()=> reject(req.error);
    });
  }

  async function remove(id){
    const d = await openDB();
    return new Promise((resolve,reject)=>{
      const tx = d.transaction(STORE,'readwrite');
      const s = tx.objectStore(STORE);
      const req = s.delete(Number(id));
      req.onsuccess = ()=> resolve(true);
      req.onerror = ()=> reject(req.error);
    });
  }

  async function clearAll(){
    const d = await openDB();
    return new Promise((resolve,reject)=>{
      const tx = d.transaction(STORE,'readwrite');
      const s = tx.objectStore(STORE);
      const req = s.clear();
      req.onsuccess = ()=> resolve(true);
      req.onerror = ()=> reject(req.error);
    });
  }

  // flush outbox by posting each payload to /api/orders; on success delete.
  async function flush(){
    try{
      const items = await all();
      if(!items || items.length === 0) return 0;
      for(const it of items){
        try{
          const resp = await fetch('/api/orders', { method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify(it.payload), credentials: 'same-origin' });
          if(resp && resp.ok){
            await remove(it.id);
            // optionally notify user; we'll dispatch a custom event
            window.dispatchEvent(new CustomEvent('outbox:flushed', { detail: { id: it.id, payload: it.payload } }));
          } else {
            // if server rejects, skip deletion and leave for manual handling
            console.warn('Failed to send outbox item', it, resp && resp.status);
          }
        }catch(e){
          console.warn('Network or fetch failed while flushing outbox', e);
          // stop trying further if network is down
          break;
        }
      }
      return true;
    }catch(e){ console.error('flush outbox failed', e); return false; }
  }

  // expose API
  window.offlineQueue = {
    save,
    all,
    remove,
    clearAll,
    flush
  };

  // auto flush when coming online
  window.addEventListener('online', async ()=>{
    try{ await flush(); window.dispatchEvent(new Event('outbox:synccomplete')); }catch(e){}
  });

  // attempt flush at startup if online
  window.addEventListener('load', ()=>{ if(navigator.onLine){ setTimeout(()=>{ flush(); }, 1000); } });
})();
