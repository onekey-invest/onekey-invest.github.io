// 모든 편이 함께 쓰는 스크립트. deck.html 맨 아래에서 <script src="../../tools/deck.js"></script>로 부른다.
//   deck.html          전부 세로로 늘어놓아 미리 본다
//   deck.html?s=3      3번 장만 남긴다 (그림으로 뽑을 때)
//   deck.html?check=1  장마다 문제를 찾아 <pre id="__check">에 적는다 (render.py가 읽는다)
(function () {
  const q = new URLSearchParams(location.search);
  const n = q.get('s');
  const slides = [...document.querySelectorAll('.slide')];
  if (n) {
    slides.forEach((s, i) => { if (i + 1 != n) s.remove(); });
    document.documentElement.style.background = 'transparent';
    return;
  }
  document.body.classList.add('preview');
  if (!q.get('check')) return;

  const PAD = 150;      // 장 아래 여백
  const ALLOW = 30;     // 아래 여백을 이만큼까지 넘는 것은 봐준다
  function find() {
    const out = [];
    slides.forEach((s, i) => {
      const bad = [];
      const r = s.getBoundingClientRect();
      if (s.scrollHeight > s.clientHeight + 1) bad.push('넘침 ' + (s.scrollHeight - s.clientHeight) + 'px');
      if (!s.classList.contains('pic')) {
        [...s.children].forEach(c => {
          if (getComputedStyle(c).position === 'absolute') return;
          const b = c.getBoundingClientRect();
          if (!b.height) return;
          const over = Math.round(b.bottom - (r.bottom - PAD));
          if (over > ALLOW) bad.push('아래 여백 침범 ' + over + 'px: ' + (c.className || c.tagName));
        });
      }
      s.querySelectorAll('h1,.take,.kicker,.tbl .v,.ba b,.bar b,.tick .v,.formula b').forEach(e => {
        if (e.scrollWidth > e.clientWidth + 2) bad.push('가로 넘침: ' + (e.className || e.tagName) + ' "' + e.textContent.trim().slice(0, 14) + '"');
      });
      s.querySelectorAll('h1').forEach(e => {
        const lines = Math.round(e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight));
        if (lines > 2) bad.push('제목이 ' + lines + '줄이다. 두 줄로 줄인다: "' + e.textContent.trim().slice(0, 16) + '"');
      });
      const dead = [...s.querySelectorAll('img')].filter(im => !(im.complete && im.naturalWidth > 0));
      if (dead.length) bad.push('사진 안 뜸 ' + dead.length + '장');
      if (!s.querySelector('.page')) bad.push('쪽 번호 없음');
      out.push({ n: i + 1, bad });
    });
    return out;
  }
  // 글꼴이 정말 실렸는지 본다. fonts.check()는 글꼴 정의를 못 읽었을 때도 참을 돌려줘서 쓰지 않는다
  // (클라우드 시험에서 다른 글꼴로 뽑혔는데 통과로 나왔다). 실제로 읽어 들인 글꼴만 센다.
  async function fonts() {
    for (let k = 0; k < 6; k++) {
      try { await document.fonts.ready; } catch (e) {}
      await new Promise(r => setTimeout(r, 60));
      if (document.fonts.status !== 'loading') break;
    }
    const ok = [...document.fonts].filter(f => /Pretendard/.test(f.family) && f.status === 'loaded');
    return { font: ok.length > 0, fontFrom: ok.some(f => /Local/.test(f.family)) ? 'file' : ok.length ? 'net' : '' };
  }
  async function run() {
    const f = await fonts();
    const pre = document.createElement('pre');
    pre.id = '__check';
    pre.textContent = JSON.stringify({ slides: find(), font: f.font, fontFrom: f.fontFrom, count: slides.length });
    document.body.appendChild(pre);
  }
  if (document.readyState === 'complete') run(); else window.addEventListener('load', run);
})();
