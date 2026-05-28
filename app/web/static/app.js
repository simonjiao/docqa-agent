let state = {
  docId: null,
  pageCount: 0,
  currentPage: 1,
  lastQuestion: "",
  lastAnswer: "",
  lastEvidence: []
};

const $ = (id) => document.getElementById(id);

function setStatus(text) { $("status").textContent = text; }

function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function renderChecks(containerId, checks) {
  const box = $(containerId);
  box.innerHTML = (checks || []).map(c => `
    <div class="check">
      ${badge(c.status)}<strong>${c.stage || ""} / ${c.name}</strong>
      <div class="small">${c.detail}</div>
    </div>
  `).join("") || "<p class='small'>暂无检查结果。</p>";
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach(btn => btn.classList.toggle("active", btn.dataset.tab === name));
  document.querySelectorAll(".tab-content").forEach(div => div.classList.toggle("active", div.id === name));
}

document.querySelectorAll(".tab").forEach(btn => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

async function postJson(url, data) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

async function loadDocMeta(meta) {
  state.docId = meta.doc_id;
  state.pageCount = meta.page_count;
  state.currentPage = 1;
  setStatus(`已解析：${meta.doc_id}；类型：${meta.probe.pdf_type}；策略：${meta.probe.strategy}；页数：${meta.page_count}；chunk 数：${meta.chunk_count}`);
  await loadPage(1);
}

async function uploadPdf() {
  const file = $("fileInput").files[0];
  if (!file) { setStatus("请先选择 PDF 文件。"); return; }
  const form = new FormData();
  form.append("file", file);
  setStatus("正在上传并进行 OCR，请稍候……");
  const res = await fetch("/api/upload", { method: "POST", body: form });
  if (!res.ok) { setStatus(await res.text()); return; }
  await loadDocMeta(await res.json());
}

function drawBox(bbox, imageWidth, imageHeight) {
  const img = $("pageImage");
  const canvas = $("overlay");
  const rect = img.getBoundingClientRect();
  const parent = img.parentElement.getBoundingClientRect();
  canvas.width = img.clientWidth;
  canvas.height = img.clientHeight;
  canvas.style.left = `${img.offsetLeft}px`;
  canvas.style.top = `${img.offsetTop}px`;
  const scaleX = img.clientWidth / imageWidth;
  const scaleY = img.clientHeight / imageHeight;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.lineWidth = 3;
  ctx.strokeStyle = "#1d5fd1";
  ctx.fillStyle = "rgba(29,95,209,.12)";
  const [x, y, w, h] = bbox;
  ctx.fillRect(x * scaleX, y * scaleY, w * scaleX, h * scaleY);
  ctx.strokeRect(x * scaleX, y * scaleY, w * scaleX, h * scaleY);
}

async function loadPage(pageNo) {
  if (!state.docId) return;
  state.currentPage = Math.max(1, Math.min(pageNo, state.pageCount));
  $("pageLabel").textContent = `${state.currentPage} / ${state.pageCount}`;
  $("pageImage").src = `/api/docs/${state.docId}/pages/${state.currentPage}/image?ts=${Date.now()}`;
  const res = await fetch(`/api/docs/${state.docId}/pages/${state.currentPage}/recognition`);
  const data = await res.json();
  const page = data.page;
  renderChecks("pageChecks", data.checks);
  $("tableRegions").innerHTML = (page.table_regions || []).map(t => `
    <div class="table-card" data-bbox="${t.bbox.join(',')}">
      <strong>疑似表格区域：${t.id}</strong>
      <div class="small">bbox=${t.bbox.join(', ')}；原因=${t.reason}</div>
    </div>
  `).join("");
  document.querySelectorAll(".table-card").forEach(el => el.onclick = () => drawBox(el.dataset.bbox.split(',').map(Number), page.image_width, page.image_height));

  $("ocrLines").innerHTML = page.lines.map(line => `
    <div class="ocr-line" data-bbox="${line.bbox.join(',')}">
      <div>${line.text}</div>
      <div class="small">${line.id}；置信度 ${line.confidence}</div>
    </div>
  `).join("");
  document.querySelectorAll(".ocr-line").forEach(el => el.onclick = () => drawBox(el.dataset.bbox.split(',').map(Number), page.image_width, page.image_height));
  $("overlay").getContext("2d").clearRect(0, 0, $("overlay").width, $("overlay").height);
}

async function ask() {
  if (!state.docId) { setStatus("请先上传 PDF。"); return; }
  const question = $("question").value.trim();
  if (!question) return;
  const result = await postJson(`/api/docs/${state.docId}/ask`, { question, top_k: 4 });
  state.lastQuestion = question;
  state.lastAnswer = result.answer;
  state.lastEvidence = result.evidence || [];
  $("answerBox").textContent = result.answer;
  renderChecks("answerChecks", result.checks);
  $("evidenceBox").innerHTML = state.lastEvidence.map(ev => `
    <div class="evidence">
      <strong>${ev.chunk_id}</strong> / 第 ${ev.page} 页 / score=${ev.score} / ${ev.kind}
      <pre>${ev.text}</pre>
    </div>
  `).join("") || "<p class='small'>无检索证据。</p>";
}

async function saveReview() {
  if (!state.docId || !state.lastQuestion) { setStatus("请先完成一次问答。"); return; }
  const item = await postJson(`/api/docs/${state.docId}/reviews`, {
    question: state.lastQuestion,
    answer: state.lastAnswer,
    evidence: state.lastEvidence,
    result: $("reviewResult").value,
    notes: $("reviewNotes").value
  });
  setStatus(`人工复核已记录：${item.item.result}`);
  await loadReviews();
}

async function loadReviews() {
  if (!state.docId) return;
  const res = await fetch(`/api/docs/${state.docId}/reviews`);
  const data = await res.json();
  $("reviewsBox").innerHTML = (data.items || []).map(item => `
    <div class="review-item">
      ${badge(item.result)}<strong>${item.question}</strong>
      <pre>${item.answer}</pre>
      <div class="small">${item.notes || "无备注"} / ${new Date(item.created_at_unix * 1000).toLocaleString()}</div>
    </div>
  `).join("") || "<p class='small'>暂无人工复核记录。</p>";
}

$("uploadBtn").onclick = uploadPdf;
$("prevPage").onclick = () => loadPage(state.currentPage - 1);
$("nextPage").onclick = () => loadPage(state.currentPage + 1);
$("askBtn").onclick = ask;
$("saveReviewBtn").onclick = saveReview;
$("refreshReviews").onclick = loadReviews;
