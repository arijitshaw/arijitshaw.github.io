const layout = document.getElementById('layout');
const toggleBtn = document.getElementById('sidebarToggle');
const backdrop = document.getElementById('backdrop');

function setCollapsed(collapsed) {
  if (collapsed) {
    layout.classList.add('collapsed');
    toggleBtn.setAttribute('aria-expanded', 'false');
  } else {
    layout.classList.remove('collapsed');
    toggleBtn.setAttribute('aria-expanded', 'true');
  }
  try { localStorage.setItem('sidebarCollapsed', String(collapsed)); } catch {}
}

function initCollapseState() {
  let collapsed = false;
  try {
    const saved = localStorage.getItem('sidebarCollapsed');
    if (saved !== null) collapsed = (saved === 'true');
    else collapsed = window.matchMedia('(max-width: 820px)').matches; // default closed on mobile
  } catch {
    collapsed = window.matchMedia('(max-width: 820px)').matches;
  }
  setCollapsed(collapsed);
}

toggleBtn.addEventListener('click', () => {
  const nowCollapsed = !layout.classList.contains('collapsed');
  setCollapsed(nowCollapsed);
});

backdrop.addEventListener('click', () => setCollapsed(true));

// Existing logic for loading notes
async function loadIndex() {
  try {
    const res = await fetch('build/index.json');
    if (!res.ok) throw new Error('index.json not found. Run `make` to build it.');
    const items = await res.json();
    const list = document.getElementById('classList');
    list.innerHTML = '';
    items.forEach(item => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.textContent = item.title || item.slug;
      a.href = '#' + item.slug;
      a.addEventListener('click', (e) => {
        e.preventDefault();
        loadNote(item.slug);
        history.replaceState(null, '', '#' + item.slug);
        if (window.matchMedia('(max-width: 820px)').matches) setCollapsed(true);
      });
      li.appendChild(a);
      list.appendChild(li);
    });
    const target = location.hash.slice(1);
    if (target) loadNote(target);
  } catch (e) {
    console.warn(e);
  }
}
function loadNote(slug) {
  const frame = document.getElementById('notesFrame');
  const placeholder = document.getElementById('placeholder');
  frame.src = `build/notes/${slug}.html`;
  frame.style.display = 'block';
  placeholder.style.display = 'none';
  document.querySelectorAll('#classList a').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === '#' + slug);
  });
}
window.addEventListener('hashchange', () => {
  const slug = location.hash.slice(1);
  if (slug) loadNote(slug);
});

initCollapseState();
loadIndex();
