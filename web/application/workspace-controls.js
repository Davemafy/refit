"use strict";

const workspaceTheme = (() => {
 const preference = matchMedia("(prefers-color-scheme: dark)");
 const select = document.getElementById("workspaceTheme");
 const apply = () => {
  const mode = document.documentElement.dataset.themePreference || "system";
  document.documentElement.dataset.theme = mode === "system" ? (preference.matches ? "dark" : "light") : mode;
  if (select) select.value = mode;
 };
 preference.addEventListener("change", apply);
 select?.addEventListener("change", () => {
  document.documentElement.dataset.themePreference = select.value;
  try { localStorage.setItem("refit-theme", select.value); } catch {}
  apply();
 });
 apply();
 return apply;
})();

function openWorkspacePalette({items, refresh, activate, escape, trigger}) {
 const existing = document.getElementById("searchOverlay");
 if (existing) { existing.querySelector("input").focus(); return; }
 const origin = trigger || document.activeElement;
 const dialog = document.createElement("dialog");
 dialog.id = "searchOverlay";
 dialog.className = "command-dialog";
 dialog.setAttribute("aria-label", "Search agents and runs");
 dialog.innerHTML = '<div class="command-head"><span aria-hidden="true">⌕</span><input type="search" id="searchInput" placeholder="Search pages, agents or runs…" aria-label="Search your agents and runs" role="combobox" aria-expanded="true" aria-controls="searchResults" autocomplete="off"><button type="button" id="searchClose" aria-label="Close search">Esc</button></div><div id="searchResults" role="listbox" aria-label="Search results"></div><footer class="command-foot"><span><kbd>↑</kbd> <kbd>↓</kbd> Navigate</span><span><kbd>↵</kbd> Open</span></footer>';
 document.body.append(dialog);
 const input = dialog.querySelector("input"), list = dialog.querySelector("#searchResults");
 let options = [], selection = 0;
 const matchText = (value, query) => {
  const index = value.toLowerCase().indexOf(query);
  return !query || index < 0 ? escape(value) :
   escape(value.slice(0, index)) + "<mark>" + escape(value.slice(index, index + query.length)) +
   "</mark>" + escape(value.slice(index + query.length));
 };
 const select = (index, scroll = false) => {
  if (!options.length) return;
  selection = (index + options.length) % options.length;
  list.querySelectorAll("[role=option]").forEach((row, i) => row.setAttribute("aria-selected", String(i === selection)));
  const active = list.querySelector("#command-" + selection);
  input.setAttribute("aria-activedescendant", active.id);
  if (scroll) active.scrollIntoView({block:"nearest"});
 };
 const render = () => {
  const query = input.value.trim().toLowerCase();
  options = items().filter(x => (x.title+" "+x.sub).toLowerCase().includes(query)).slice(0, 18);
  list.innerHTML = options.length ? [...new Set(options.map(x => x.group))].map(group =>
   '<div class="command-group" role="group" aria-label="'+escape(group)+'"><div class="command-group-label">'+escape(group)+'</div>'+
   options.map((x,i) => x.group !== group ? "" :
    '<div class="command-row" role="option" id="command-'+i+'" data-index="'+i+'" data-search-action="'+escape(x.action)+'"><span>'+
    matchText(x.title,query)+'</span><small>'+matchText(x.sub,query)+'</small></div>').join("")+'</div>').join("") :
   '<p class="command-empty">No matches. Try a page name, repository, model or run ID.</p>';
  input.removeAttribute("aria-activedescendant");
  select(0);
 };
 const dismiss = () => {
  dialog.close();
  dialog.remove();
  origin?.focus();
 };
 const choose = index => {
  const item = options[index];
  if (!item) return;
  dismiss();
  activate(item);
 };
 dialog.addEventListener("cancel", e => { e.preventDefault(); dismiss(); });
 dialog.addEventListener("keydown", e => {
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); dismiss(); }
 });
 dialog.querySelector("#searchClose").onclick = dismiss;
 dialog.addEventListener("click", e => { if (e.target === dialog) dismiss(); });
 input.addEventListener("input", render);
 input.addEventListener("keydown", e => {
  if (!["ArrowDown","ArrowUp","Enter"].includes(e.key)) return;
  e.preventDefault();
  if (e.key === "Enter") choose(selection);
  else select(selection + (e.key === "ArrowDown" ? 1 : -1), true);
 });
 list.addEventListener("pointermove", e => {
  const row = e.target.closest("[data-index]");
  if (row) select(Number(row.dataset.index));
 });
 list.addEventListener("click", e => {
  const row = e.target.closest("[data-index]");
  if (row) choose(Number(row.dataset.index));
 });
 dialog.showModal();
 render();
 input.focus();
 refresh().then(() => { if (dialog.open) render(); }).catch(() => {});
}
