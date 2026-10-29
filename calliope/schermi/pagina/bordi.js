// Calliope · i bordi di una pagina fotografata (29/10/2026, passo 4.2 dello Studio, issue #281,
// decisione 0035). Un rilevatore scritto a mano, senza OpenCV.js né altre librerie: lo stesso
// algoritmo di calliope/studio/pagine.py, che sul server lo ripete e vale il suo esito.
// Sul fotogramma ridotto (lato lungo LATO, 320 px) in grigi: due sfocature 3×3, la soglia di Otsu,
// il fondo scuro collegato al bordo della foto che si allarga solo fra i pixel senza un bordo forte
// (Sobel oltre MURO: così non entra nella pagina in ombra), il pezzo chiaro più grande che resta,
// i quattro punti estremi (x+y, x−y). La forma è plausibile se è convessa, prende fra il 15 % e il
// 99,5 % della foto, ha gli angoli fra 40° e 140° e i lati opposti non troppo diversi, e se la
// pagina chiara copre almeno l'85 % del quadrilatero. La nitidezza: varianza del laplaciano a lato
// 1000 col contrasto portato a 0–255 fra l'1° e il 99° percentile.
// Niente DOM: gira anche con node (prove/prova_studio_pagine.py lo confronta col Python).
"use strict";

(function (radice) {
  const LATO = 320;
  const LATO_NITIDEZZA = 1000;
  const MURO = 60;
  const BORDO_CHIARO = 0.6;
  const AREA_MIN = 0.15, AREA_MAX = 0.995;
  const ANGOLO_MIN = 40, ANGOLO_MAX = 140;
  const LATI_MIN = 0.4;
  const COPERTURA_MIN = 0.85;

  // RGBA (ImageData.data) → grigi interi 0–255, come pagine.grigio
  function grigio(rgba, w, h) {
    const g = new Int32Array(w * h);
    for (let i = 0, j = 0; i < g.length; i++, j += 4) {
      g[i] = Math.floor((rgba[j] * 299 + rgba[j + 1] * 587 + rgba[j + 2] * 114) / 1000);
    }
    return g;
  }

  function prendi(g, w, h, x, y) {
    x = x < 0 ? 0 : (x >= w ? w - 1 : x);
    y = y < 0 ? 0 : (y >= h ? h - 1 : y);
    return g[y * w + x];
  }

  function sfoca(g, w, h) {
    const out = new Int32Array(w * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let s = 0;
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) s += prendi(g, w, h, x + dx, y + dy);
        out[y * w + x] = Math.floor(s / 9);
      }
    }
    return out;
  }

  function sobel(g, w, h) {
    const out = new Int32Array(w * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const a = (dy, dx) => prendi(g, w, h, x + dx, y + dy);
        const gx = (a(-1, 1) + 2 * a(0, 1) + a(1, 1)) - (a(-1, -1) + 2 * a(0, -1) + a(1, -1));
        const gy = (a(1, -1) + 2 * a(1, 0) + a(1, 1)) - (a(-1, -1) + 2 * a(-1, 0) + a(-1, 1));
        out[y * w + x] = Math.abs(gx) + Math.abs(gy);
      }
    }
    return out;
  }

  function otsu(g) {
    const ist = new Float64Array(256);
    for (let i = 0; i < g.length; i++) ist[g[i]]++;
    const tot = g.length;
    let somma = 0;
    for (let t = 0; t < 256; t++) somma += t * ist[t];
    let sb = 0, wb = 0, meglio = -1, soglia = 0;
    for (let t = 0; t < 256; t++) {
      wb += ist[t];
      if (wb === 0) continue;
      const wf = tot - wb;
      if (wf === 0) break;
      sb += t * ist[t];
      const mb = sb / wb, mf = (somma - sb) / wf;
      const tra = wb * wf * (mb - mf) * (mb - mf);
      if (tra > meglio) { meglio = tra; soglia = t; }
    }
    return soglia;
  }

  // I pixel veri di m raggiunti dai semi (4-vicini); vista si condivide fra più chiamate
  function componente(m, w, h, semi, vista) {
    const coda = [];
    for (const i of semi) if (m[i] && !vista[i]) { vista[i] = 1; coda.push(i); }
    const ultima = (h - 1) * w;
    for (let k = 0; k < coda.length; k++) {
      const i = coda[k], x = i % w;
      if (x > 0 && m[i - 1] && !vista[i - 1]) { vista[i - 1] = 1; coda.push(i - 1); }
      if (x < w - 1 && m[i + 1] && !vista[i + 1]) { vista[i + 1] = 1; coda.push(i + 1); }
      if (i >= w && m[i - w] && !vista[i - w]) { vista[i - w] = 1; coda.push(i - w); }
      if (i < ultima && m[i + w] && !vista[i + w]) { vista[i + w] = 1; coda.push(i + w); }
    }
    return coda;
  }

  function bordoFoto(w, h) {
    const b = [];
    for (let i = 0; i < w; i++) b.push(i);
    for (let i = 0; i < w; i++) b.push((h - 1) * w + i);
    for (let y = 1; y < h - 1; y++) b.push(y * w);
    for (let y = 1; y < h - 1; y++) b.push(y * w + w - 1);
    return b;
  }

  // {maschera, intera}: la pagina chiara più grande, o la pagina che riempie la foto
  function pagina(g, w, h) {
    const t = otsu(g);
    const bordo = bordoFoto(w, h);
    let chiari = 0;
    for (const i of bordo) if (g[i] > t) chiari++;
    if (chiari > BORDO_CHIARO * bordo.length) return { maschera: null, intera: true };
    const s = sobel(g, w, h);
    const passa = new Uint8Array(w * h);
    for (let i = 0; i < passa.length; i++) passa[i] = g[i] <= t && s[i] <= MURO ? 1 : 0;
    const fondo = new Uint8Array(w * h);
    for (const i of componente(passa, w, h, bordo, new Uint8Array(w * h))) fondo[i] = 1;
    const resto = new Uint8Array(w * h);
    let totale = 0;
    for (let i = 0; i < resto.length; i++) { resto[i] = fondo[i] ? 0 : 1; totale += resto[i]; }
    const vista = new Uint8Array(w * h);
    let meglio = [];
    for (let i = 0; i < resto.length; i++) {
      if (!resto[i] || vista[i]) continue;
      const pezzo = componente(resto, w, h, [i], vista);
      if (pezzo.length > meglio.length) meglio = pezzo;
      if (meglio.length * 2 > totale) break;
    }
    const out = new Uint8Array(w * h);
    for (const i of meglio) out[i] = 1;
    return { maschera: out, intera: false, area: meglio.length };
  }

  // I quattro angoli (alto-sx, alto-dx, basso-dx, basso-sx) dai punti estremi, in pixel
  function estremi(m, w, h) {
    let a = null, b = null, c = null, d = null;           // min s, max dd, max s, min dd
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        if (!m[y * w + x]) continue;
        const s = x + y, dd = x - y;
        if (a === null || s < a[2]) a = [x, y, s];
        if (b === null || dd > b[2]) b = [x, y, dd];
        if (c === null || s > c[2]) c = [x, y, s];
        if (d === null || dd < d[2]) d = [x, y, dd];
      }
    }
    return [a, b, c, d].map((p) => [p[0] + 0.5, p[1] + 0.5]);
  }

  const px = (angoli, w, h) => angoli.map((a) => [a[0] * w, a[1] * h]);
  function area(p) {
    let s = 0;
    for (let i = 0; i < 4; i++) s += p[i][0] * p[(i + 1) % 4][1] - p[(i + 1) % 4][0] * p[i][1];
    return Math.abs(s) / 2;
  }
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

  // null se il quadrilatero (frazioni della foto w×h) può essere una pagina; altrimenti il motivo
  function plausibili(angoli, w, h) {
    if (!Array.isArray(angoli) || angoli.length !== 4) return "mancano";
    for (const a of angoli) for (const v of a) if (!(v >= -0.02 && v <= 1.02)) return "fuori";
    const p = px(angoli, w, h);
    const segni = [];
    for (let i = 0; i < 4; i++) {
      const a = p[i], b = p[(i + 1) % 4], c = p[(i + 2) % 4];
      segni.push((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]));
    }
    if (!(segni.every((s) => s > 0) || segni.every((s) => s < 0))) return "non_convesso";
    const ar = area(p) / (w * h);
    if (ar < AREA_MIN) return "piccolo";
    if (ar > AREA_MAX) return "tutta";
    for (let i = 0; i < 4; i++) {
      const a = p[(i + 3) % 4], b = p[i], c = p[(i + 1) % 4];
      const v1 = [a[0] - b[0], a[1] - b[1]], v2 = [c[0] - b[0], c[1] - b[1]];
      const n = Math.hypot(v1[0], v1[1]) * Math.hypot(v2[0], v2[1]);
      if (n === 0) return "angolo";
      const ang = Math.acos(Math.max(-1, Math.min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / n))) * 180 / Math.PI;
      if (ang < ANGOLO_MIN || ang > ANGOLO_MAX) return "angolo";
    }
    const lati = [0, 1, 2, 3].map((i) => dist(p[i], p[(i + 1) % 4]));
    for (const i of [0, 1]) {
      const a = lati[i], b = lati[i + 2];
      if (Math.min(a, b) < LATI_MIN * Math.max(a, b)) return "lati";
    }
    return null;
  }

  // La parte del quadrilatero (frazioni) coperta dalla maschera
  function copertura(m, w, h, angoli) {
    if (!m) return 0;
    const p = px(angoli, w, h);
    let s = 0;
    for (let i = 0; i < 4; i++) s += p[i][0] * p[(i + 1) % 4][1] - p[(i + 1) % 4][0] * p[i][1];
    const orario = s > 0;
    let n = 0, dentro = 0;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const xx = x + 0.5, yy = y + 0.5;
        let ok = true;
        for (let i = 0; i < 4 && ok; i++) {
          const a = p[i], b = p[(i + 1) % 4];
          const c = (b[0] - a[0]) * (yy - a[1]) - (b[1] - a[1]) * (xx - a[0]);
          ok = orario ? c >= 0 : c <= 0;
        }
        if (ok) { n++; if (m[y * w + x]) dentro++; }
      }
    }
    return n ? dentro / n : 0;
  }

  function vicinoAlBordo(angoli) {
    const ang = [[0, 0], [1, 0], [1, 1], [0, 1]];
    return angoli.every((a, i) => Math.abs(a[0] - ang[i][0]) <= 0.03 && Math.abs(a[1] - ang[i][1]) <= 0.03);
  }

  // Il rilevatore sul fotogramma in grigi: {angoli (frazioni) o null, intera, motivo}
  function rileva(g, w, h) {
    const b = sfoca(sfoca(g, w, h), w, h);
    const pg = pagina(b, w, h);
    if (pg.intera) return { angoli: null, intera: true, motivo: null };
    if (!pg.maschera || pg.area < AREA_MIN * w * h) return { angoli: null, intera: false, motivo: "piccolo" };
    const angoli = estremi(pg.maschera, w, h).map(([x, y]) => [x / w, y / h]);
    if (vicinoAlBordo(angoli)) return { angoli: null, intera: true, motivo: null };
    let motivo = plausibili(angoli, w, h);
    if (motivo === null && copertura(pg.maschera, w, h, angoli) < COPERTURA_MIN) motivo = "copertura";
    return { angoli: motivo === null ? angoli : null, intera: false, motivo };
  }

  // La nitidezza come pagine.nitidezza (sui grigi già a lato ≤ LATO_NITIDEZZA)
  function nitidezza(g, w, h) {
    if (w < 3 || h < 3) return 0;
    const ist = new Float64Array(256);
    for (let i = 0; i < g.length; i++) ist[g[i]]++;
    const n = g.length;
    let cum = 0, basso = 255, alto = 255, presoB = false;
    for (let v = 0; v < 256; v++) {
      cum += ist[v];
      if (!presoB && cum > 0.01 * n) { basso = v; presoB = true; }
      if (cum >= 0.99 * n) { alto = v; break; }
    }
    if (alto - basso < 1) return 0;
    const k = 255 / (alto - basso);
    const f = (i) => Math.min(255, Math.max(0, (g[i] - basso) * k));
    let s = 0, s2 = 0, m = 0;
    for (let y = 1; y < h - 1; y++) {
      for (let x = 1; x < w - 1; x++) {
        const i = y * w + x;
        const l = 4 * f(i) - f(i - w) - f(i + w) - f(i - 1) - f(i + 1);
        s += l; s2 += l * l; m++;
      }
    }
    const media = s / m;
    return s2 / m - media * media;
  }

  const api = { LATO, LATO_NITIDEZZA, MURO, grigio, sfoca, sobel, otsu, rileva, plausibili, copertura, nitidezza };
  if (typeof module === "object" && module.exports) module.exports = api;
  else radice.CalliopeBordi = api;
})(typeof self !== "undefined" ? self : this);
