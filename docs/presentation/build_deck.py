"""Build a standalone deck.html (renders the Slides-artifact format in any browser) from deck.json + slides/*.html.

    python build_deck.py <presentation_dir>

Open deck.html to page through (arrow keys); deck.html?slide=N shows slide N alone at 1920x1080 (for screenshots);
printing gives one slide per page.
"""
import json
import pathlib
import sys

d = pathlib.Path(sys.argv[1])
deck = json.loads((d / "deck.json").read_text(encoding="utf-8"))
slides = "\n".join((d / "slides" / f"{sid}.html").read_text(encoding="utf-8") for sid in deck["order"])
fonts = "\n".join(f'<link rel="stylesheet" href="{f["href"]}">' for f in deck["faces"].values() if "href" in f)

ICONS = {
    "Activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "Lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "Chart": '<path d="M3 3v18h18"/><path d="M8 17v-5"/><path d="M13 17V8"/><path d="M18 17v-9"/>',
    "Warning": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "Users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
    "Search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.4-4.4"/>',
    "Globe": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z"/>',
    "Database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.7-4 3-9 3s-9-1.3-9-3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/>',
    "Verified": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "CheckCircle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "Clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "Tool": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9l-3.8 3.8z"/>',
    "Check": '<path d="M20 6 9 17l-5-5"/>',
    "PaperPlane": '<path d="M22 2 11 13"/><path d="M22 2 15 22 11 13 2 9z"/>',
    "Play": '<circle cx="12" cy="12" r="10"/><path d="m10 8 6 4-6 4z"/>',
    "Chat": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "Lightbulb": '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/>',
}

html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{deck['title']}</title>
{fonts}
<style>
*{{box-sizing:border-box;margin:0}}
html,body{{background:#2B2F36}}
body{{font-family:Arial,sans-serif;padding:24px 0}}
#deck{{display:flex;flex-direction:column;align-items:center;gap:24px}}
.frame{{width:min(96vw,1600px);aspect-ratio:16/9;position:relative;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.4)}}
section{{position:absolute;left:0;top:0;width:1920px;height:1080px;transform-origin:0 0;overflow:hidden}}
section > *{{position:relative}}
section aside{{display:none}}
x-icon,x-shape{{display:block;flex:none}}
x-shape[kind=ellipse]{{border-radius:50%}}
x-shape[kind=arrow-right]{{clip-path:polygon(0 30%,60% 30%,60% 0,100% 50%,60% 100%,60% 70%,0 70%)}}
hr{{border:none}}
.solo body,.solo{{padding:0;background:transparent}}
.solo #deck{{gap:0}}
.solo .frame{{width:1920px;box-shadow:none}}
@media print{{@page{{size:1920px 1080px;margin:0}} body{{padding:0;background:none}} #deck{{gap:0}}
 .frame{{width:1920px;box-shadow:none;break-after:page}}}}
</style></head>
<body><div id="deck">
{slides}
</div>
<script>
const ICONS = {json.dumps(ICONS)};
document.querySelectorAll('x-icon').forEach(el => {{
  const p = ICONS[el.getAttribute('name')] || '';
  el.innerHTML = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + p + '</svg>';
}});
document.querySelectorAll('section').forEach(sec => {{
  const cons = [...sec.querySelectorAll('x-connector')];
  if (cons.length) {{
    let s = '<svg style="position:absolute;left:0;top:0;width:1920px;height:1080px;pointer-events:none" viewBox="0 0 1920 1080">';
    cons.forEach(c => {{
      const [x1,y1,x2,y2] = ['x1','y1','x2','y2'].map(a => +c.getAttribute(a));
      const col = c.style.color || '#000', w = parseFloat(c.style.borderWidth) || 2, my = (y1 + y2) / 2;
      s += `<polyline points="${{x1}},${{y1}} ${{x1}},${{my}} ${{x2}},${{my}} ${{x2}},${{y2 - 12}}" fill="none" stroke="${{col}}" stroke-width="${{w}}"/>`;
      s += `<polygon points="${{x2-10}},${{y2-14}} ${{x2+10}},${{y2-14}} ${{x2}},${{y2}}" fill="${{col}}"/>`;
      c.remove();
    }});
    sec.insertAdjacentHTML('afterbegin', s + '</svg>');
  }}
  const frame = document.createElement('div'); frame.className = 'frame';
  sec.parentNode.insertBefore(frame, sec); frame.appendChild(sec);
}});
const solo = new URLSearchParams(location.search).get('slide');
const frames = [...document.querySelectorAll('.frame')];
if (solo) {{ document.documentElement.classList.add('solo'); frames.forEach((f, i) => {{ if (i + 1 != +solo) f.remove(); }}); }}
function fit() {{ document.querySelectorAll('.frame').forEach(f => {{ f.firstElementChild.style.transform = 'scale(' + (f.clientWidth / 1920) + ')'; }}); }}
window.addEventListener('resize', fit); window.addEventListener('beforeprint', () => frames.forEach(f => f.firstElementChild.style.transform = 'none')); fit();
let cur = 0;
document.addEventListener('keydown', e => {{
  if (!['ArrowRight','ArrowDown','PageDown','ArrowLeft','ArrowUp','PageUp'].includes(e.key)) return;
  cur = Math.max(0, Math.min(frames.length - 1, cur + (['ArrowRight','ArrowDown','PageDown'].includes(e.key) ? 1 : -1)));
  frames[cur].scrollIntoView({{behavior: 'smooth', block: 'center'}}); e.preventDefault();
}});
</script></body></html>
"""
(d / "deck.html").write_text(html, encoding="utf-8")
print("wrote", d / "deck.html", len(deck["order"]), "slides")
