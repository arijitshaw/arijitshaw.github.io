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
loadIndex();
