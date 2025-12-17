// Lightweight canvas water splash / bubbles animation
// Adds rising bubbles and click/tap splashes. Respects prefers-reduced-motion.
(function(){
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let canvas, ctx, width, height, dpr = window.devicePixelRatio || 1;
  let bubbles = [];
  let rings = [];
  let running = !reduced;
  // scale the bubble count up for a full-page background while keeping it reasonable
  const MAX_BUBBLES = 80;

  function resize(){
    if(!canvas) return;
    const rect = canvas.getBoundingClientRect();
    dpr = window.devicePixelRatio || 1;
    width = Math.max(1, Math.floor(rect.width * dpr));
    height = Math.max(1, Math.floor(rect.height * dpr));
    canvas.width = width; canvas.height = height;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    if(ctx) ctx.setTransform(dpr,0,0,dpr,0,0);
  }

  function rand(min, max){ return Math.random() * (max - min) + min; }

  function makeBubble(){
    return {
      x: rand(20, (width/dpr)-20),
      y: (height/dpr) + rand(10, 60),
      r: rand(6, 26),
      speed: rand(0.2, 1.2),
      alpha: rand(0.35, 0.95),
      drift: rand(-0.25, 0.25)
    };
  }

  function makeRing(x, y){
    return { x, y, t: 0, r: 4, life: 1.0 };
  }

  function step(dt){
    if(reduced) return;
    // update bubbles
    for(let i=bubbles.length-1;i>=0;i--){
      const b = bubbles[i];
      b.y -= b.speed * dt * 0.06;
      b.x += b.drift * dt * 0.03;
      b.r *= 0.9995;
      if(b.y + b.r < -20 || b.r < 2) bubbles.splice(i,1);
    }
    // maintain bubble count
    while(bubbles.length < MAX_BUBBLES){ bubbles.push(makeBubble()); }

    // rings
    for(let i=rings.length-1;i>=0;i--){
      const R = rings[i];
      R.t += dt * 0.01;
      R.r = 4 + R.t * 36;
      R.life = Math.max(0, 1 - R.t * 0.9);
      if(R.life <= 0) rings.splice(i,1);
    }
  }

  function draw(){
    if(!ctx) return;
    ctx.clearRect(0,0, canvas.width, canvas.height);
    // gentle bluish gradient overlay for a watery feel
    const g = ctx.createLinearGradient(0,0,0, height/dpr);
    g.addColorStop(0, 'rgba(10,148,136,0.03)');
    g.addColorStop(1, 'rgba(14,165,183,0.06)');
    ctx.fillStyle = g;
    ctx.fillRect(0,0, width/dpr, height/dpr);

    // draw rings first
    rings.forEach(R=>{
      ctx.beginPath();
      ctx.arc(R.x, R.y, R.r, 0, Math.PI*2);
      ctx.strokeStyle = `rgba(173,216,230,${0.22 * R.life})`;
      ctx.lineWidth = 2 * R.life;
      ctx.stroke();
    });

    // draw bubbles
    bubbles.forEach(b=>{
      const grad = ctx.createRadialGradient(b.x - b.r*0.3, b.y - b.r*0.3, 1, b.x, b.y, b.r);
      // bluish bubble highlight -> soft water-blue fills
      grad.addColorStop(0, `rgba(225,245,255,${0.95*b.alpha})`);
      grad.addColorStop(0.45, `rgba(180,230,255,${0.55*b.alpha})`);
      grad.addColorStop(1, `rgba(140,205,245,0.08)`);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r, 0, Math.PI*2);
      ctx.fill();
    });
  }

  let last = performance.now();
  function loop(now){
    const dt = Math.max(1, now - last);
    last = now;
    if(running){ step(dt); draw(); }
    requestAnimationFrame(loop);
  }

  function init(){
    // prefer the background canvas (full-page) if present -> fallback to existing splashCanvas
    canvas = document.getElementById('backgroundSplash') || document.getElementById('splashCanvas');
    if(!canvas) return;
    ctx = canvas.getContext('2d', {alpha:true});
    resize();
    // subtle fade-in when ready
    try{ canvas.classList.add('ready'); }catch(e){}
    // initial bubbles
    for(let i=0;i<Math.min(12, MAX_BUBBLES); i++) bubbles.push(makeBubble());

    // click to create splashes
    canvas.addEventListener('pointerdown', (ev)=>{
      const rect = canvas.getBoundingClientRect();
      const x = (ev.clientX - rect.left);
      const y = (ev.clientY - rect.top);
      // create a ring and a burst of small bubbles
      rings.push(makeRing(x, y));
      for(let i=0;i<6;i++){
        const b = makeBubble(); b.x = x + rand(-24,24); b.y = y + rand(-6,12); b.r = rand(6,16); b.speed = rand(0.6,1.8); bubbles.push(b);
      }
    });

    // pause toggle
    const btn = document.getElementById('toggleSplash');
    if(btn){
      btn.addEventListener('click', ()=>{
        running = !running; btn.textContent = running ? 'Pause' : 'Play';
      });
    }

    // responsive
    window.addEventListener('resize', resize);
    // start loop
    requestAnimationFrame(loop);
  }

  // init when DOM ready
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

  // expose a small API
  window.splashAnimation = {
    pause: ()=>{ running=false; const b=document.getElementById('toggleSplash'); if(b) b.textContent='Play'; },
    resume: ()=>{ running=true; const b=document.getElementById('toggleSplash'); if(b) b.textContent='Pause'; }
  };
})();
