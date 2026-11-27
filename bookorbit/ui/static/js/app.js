/* BookOrbit AI - small helpers for the screens (no external libraries). */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // modals / toggles
  document.addEventListener("click", (e) => {
    const open = e.target.closest("[data-open]");
    if (open) { $("#" + open.dataset.open).classList.add("show"); }
    const close = e.target.closest("[data-close]");
    if (close) { $("#" + close.dataset.close).classList.remove("show"); }
    if (e.target.classList.contains("modal-bg")) e.target.classList.remove("show");
    const tog = e.target.closest("[data-toggle]");
    if (tog) { const el = $("#" + tog.dataset.toggle); el.style.display = el.style.display === "none" ? "" : "none"; }
    const fill = e.target.closest("[data-fill]");
    if (fill) { $("#" + fill.dataset.fill).value = fill.dataset.value; }
    const enroll = e.target.closest("[data-enroll]");
    if (enroll) {
      const f = $("#enroll-form");
      f.action = "/admin/users/" + enroll.dataset.enroll + "/face";
      $("#enroll-name").textContent = enroll.dataset.name;
      $("#enroll-modal").classList.add("show");
    }
  });

  // UC-08 step 2-3: show the confirmation and let the customer confirm or cancel
  $$("form[data-confirm]").forEach((f) => f.addEventListener("submit", (e) => {
    if (!window.confirm(f.dataset.confirm)) e.preventDefault();
  }));

  // review character counter
  const comment = $("#comment"), counter = $("#char-count");
  if (comment && counter) {
    const upd = () => { counter.textContent = comment.value.length + " / 1000"; };
    comment.addEventListener("input", upd); upd();
  }

  // ---------------------------------------------------------- face box
  $$("[data-facebox]").forEach((box) => {
    const msg = $("[data-facemsg]", box), cam = $("[data-cam]", box);
    const show = (d) => {
      msg.textContent = d.message;
      msg.className = "facemsg " + (d.ok ? "ok" : "bad");
      if (d.preview) cam.innerHTML = '<img alt="Captured face" src="' + d.preview + '">';
    };
    const capture = $("[data-capture]", box);
    if (capture) capture.addEventListener("click", async () => {
      msg.textContent = "Capturing…"; msg.className = "facemsg";
      const r = await fetch("/face/capture?purpose=" + box.dataset.purpose, { method: "POST" });
      show(await r.json());
    });
    const photo = $("[data-photo]", box);
    photo.addEventListener("change", async () => {
      if (!photo.files.length) return;
      const fd = new FormData(); fd.append("face_photo", photo.files[0]);
      msg.textContent = "Checking photo…"; msg.className = "facemsg";
      const r = await fetch("/face/upload", { method: "POST", body: fd });
      show(await r.json());
    });
  });

  // --------------------------------------------------------------- chat
  window.initChat = function (url) {
    const form = $("#chat-form"), input = $("#question"), send = $("#send"), msgs = $("#msgs");
    input.addEventListener("input", () => { send.disabled = !input.value.trim(); });
    const add = (html, cls) => {
      const d = document.createElement("div"); d.className = "msg " + cls; d.innerHTML = html;
      msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight; return d;
    };
    async function ask(q) {
      add(esc(q), "me");
      input.value = ""; send.disabled = true;
      const wait = add('<span class="muted">Thinking…</span>', "bot");
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      const d = await r.json();
      let html = esc(d.text || "");
      if (d.table && d.table.length) html += "<table>" + d.table.map((r) => "<tr><td>" + esc(r[0]) + "</td><td>" + esc(r[1]) + "</td></tr>").join("") + "</table>";
      if (d.examples && d.examples.length) html += '<div class="suggest" style="margin-top:8px">' + d.examples.map((e) => '<button type="button" data-ask="' + esc(e) + '">' + esc(e) + "</button>").join("") + "</div>";
      if (d.books && d.books.length) html += '<div class="minibooks">' + d.books.map((b) => '<a href="/books/' + b.book_ID + '"><img src="' + b.cover + '" alt=""><div>' + esc(b.title) + "</div></a>").join("") + "</div>";
      const cls = { RAG: "rag", ACCOUNT: "rag", LLM: "llm", ADMIN: "admin" }[d.source] || "";
      if (d.label) html += '<span class="label ' + cls + '" data-source="' + d.source + '">' + esc(d.label) + "</span>";
      wait.innerHTML = html; wait.dataset.source = d.source;
      msgs.scrollTop = msgs.scrollHeight;
    }
    form.addEventListener("submit", (e) => { e.preventDefault(); if (input.value.trim()) ask(input.value.trim()); });
    document.addEventListener("click", (e) => { const b = e.target.closest("[data-ask]"); if (b) ask(b.dataset.ask); });
  };

  // ------------------------------------------------------------- reader
  window.initReader = function (actUrl, quizUrl) {
    const page = $("#page"), out = $("#aiout"), prev = $("#sel-preview");
    let selection = "";
    document.addEventListener("selectionchange", () => {
      const s = window.getSelection();
      if (s && page.contains(s.anchorNode)) {
        selection = s.toString().trim();
        prev.textContent = selection ? "“" + (selection.length > 60 ? selection.slice(0, 60) + "…" : selection) + "”" : "nothing";
      }
    });
    async function act(action, question) {
      out.innerHTML = '<span class="muted">Working…</span>';
      const r = await fetch(actUrl, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, chapter: page.dataset.chapter, selection, question: question || "" }) });
      const d = await r.json();
      if (!d.ok) { out.innerHTML = '<div class="err" id="ai-error">' + esc(d.message) + "</div>"; return; }
      if (d.quiz) return renderQuiz(d);
      out.innerHTML = "<b>" + esc(d.title) + "</b>\n" + esc(d.text) + '<div class="src">' + esc(d.source) + "</div>";
    }
    function renderQuiz(d) {
      out.innerHTML = "<b>Quiz me</b>" + d.quiz.map((q, i) =>
        '<div class="quizq" data-q="' + i + '"><div class="small"><b>' + (i + 1) + ".</b> " + esc(q.question) + "</div>" +
        q.options.map((o, j) => '<button class="btn ghost small opt" data-i="' + i + '" data-j="' + j + '">' + esc(o) + "</button>").join("") +
        '<div class="tiny" data-res></div></div>').join("") + '<div class="src">' + esc(d.source) + "</div>";
      $$(".opt", out).forEach((b) => b.addEventListener("click", async () => {
        const box = b.closest(".quizq");
        if (box.dataset.done) return;
        const r = await fetch(quizUrl, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ quiz_ID: d.quiz_ID, index: +b.dataset.i, choice: +b.dataset.j }) });
        const res = await r.json();
        if (!res.ok) { $("[data-res]", box).textContent = res.message; return; }
        box.dataset.done = 1;
        $$(".opt", box).forEach((x) => { if (+x.dataset.j === res.answer_index) x.classList.add("right"); });
        if (!res.correct) b.classList.add("wrong");
        $("[data-res]", box).textContent = res.correct ? "Correct!" : "Not quite - the answer is “" + res.answer + "”.";
      }));
    }
    $$("[data-act]").forEach((b) => b.addEventListener("click", () => act(b.dataset.act)));
    $("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); act("ask", $("#ask").value); });
  };
})();
