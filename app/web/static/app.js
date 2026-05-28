let state = {
  docId: null,
  pageCount: 0,
  currentPage: 1,
  lastQuestion: "",
  lastAnswer: "",
  lastEvidence: [],
  isUploading: false
};

const $ = (id) => document.getElementById(id);

function setStatus(text) {
  const statusText = $("statusText");
  if (statusText) {
    statusText.textContent = text;
  } else {
    $("status").textContent = text;
  }
}

function setUploadBusy(isBusy) {
  state.isUploading = isBusy;
  $("status").classList.toggle("busy", isBusy);
  $("status").setAttribute("aria-disabled", String(isBusy));
}

function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[ch]));
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
  setUploadBusy(true);
  setStatus("正在上传并进行解析，请稍候……");
  try {
    const res = await fetch("/api/upload", { method: "POST", body: form });
    if (!res.ok) { setStatus(await res.text()); return; }
    await loadDocMeta(await res.json());
  } finally {
    $("fileInput").value = "";
    setUploadBusy(false);
  }
}

function openUploadDialog(event) {
  if (state.isUploading) return;
  if (event?.target === fileInputEl) return;
  fileInputEl.click();
}

function drawBox(bbox, imageWidth, imageHeight) {
  const img = $("pageImage");
  const canvas = $("overlay");
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

function focusBbox(bbox, imageWidth, imageHeight) {
  const img = $("pageImage");
  if (!img.complete || !img.clientWidth || !img.clientHeight) {
    img.onload = () => focusBbox(bbox, imageWidth, imageHeight);
    return;
  }
  drawBox(bbox, imageWidth, imageHeight);
  scrollPdfToBboxIfNeeded(bbox, imageWidth, imageHeight);
}

function scrollPdfToBboxIfNeeded(bbox, imageWidth, imageHeight) {
  const img = $("pageImage");
  const wrap = img.closest(".image-wrap");
  if (!wrap) return;

  const [x, y, w, h] = bbox;
  const scaleX = img.clientWidth / imageWidth;
  const scaleY = img.clientHeight / imageHeight;
  const target = {
    left: img.offsetLeft + x * scaleX,
    top: img.offsetTop + y * scaleY,
    right: img.offsetLeft + (x + w) * scaleX,
    bottom: img.offsetTop + (y + h) * scaleY
  };
  const margin = 24;
  const visible = {
    left: wrap.scrollLeft + margin,
    top: wrap.scrollTop + margin,
    right: wrap.scrollLeft + wrap.clientWidth - margin,
    bottom: wrap.scrollTop + wrap.clientHeight - margin
  };
  const isVisible = target.left >= visible.left && target.right <= visible.right && target.top >= visible.top && target.bottom <= visible.bottom;
  if (isVisible) return;

  const targetScrollLeft = clamp(((target.left + target.right) / 2) - (wrap.clientWidth / 2), 0, wrap.scrollWidth - wrap.clientWidth);
  const targetScrollTop = clamp(((target.top + target.bottom) / 2) - (wrap.clientHeight / 2), 0, wrap.scrollHeight - wrap.clientHeight);
  wrap.scrollTo({
    left: target.left < visible.left || target.right > visible.right ? targetScrollLeft : wrap.scrollLeft,
    top: target.top < visible.top || target.bottom > visible.bottom ? targetScrollTop : wrap.scrollTop,
    behavior: "smooth"
  });
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(value, Math.max(min, max)));
}

function setActiveItem(el, selector) {
  document.querySelectorAll(selector).forEach(item => item.classList.toggle("active", item === el));
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
  renderHtmlPreview(page);
  $("tableRegions").innerHTML = (page.table_regions || []).map(t => `
    <div class="table-card" data-bbox="${t.bbox.join(',')}" data-table-id="${(t.structured_tables || [])[0]?.table_id || ""}">
      <strong>疑似表格区域：${escapeHtml(t.id)}</strong>
      <div class="small">bbox=${t.bbox.join(', ')}；原因=${escapeHtml(t.reason)}</div>
      ${(t.structured_tables || []).map(table => `
        <div class="small">结构化：${escapeHtml(table.table_id)}；${escapeHtml(table.status)}；${escapeHtml(table.strategy)}；${table.row_count}x${table.column_count}</div>
      `).join("")}
    </div>
  `).join("");
  $("tableDetails").innerHTML = "";
  document.querySelectorAll(".table-card").forEach(el => el.onclick = async () => {
    setActiveItem(el, ".table-card");
    focusBbox(el.dataset.bbox.split(',').map(Number), page.image_width, page.image_height);
    if (el.dataset.tableId) {
      await loadTableDetail(el.dataset.tableId, page.image_width, page.image_height);
    }
  });

  $("ocrLines").innerHTML = page.lines.map(line => `
    <div class="ocr-line" data-bbox="${line.bbox.join(',')}">
      <div>${line.text}</div>
      <div class="small">${line.id}；${line.confidence_display || `置信度 ${line.confidence}`}</div>
    </div>
  `).join("");
  document.querySelectorAll(".ocr-line").forEach(el => el.onclick = () => {
    setActiveItem(el, ".ocr-line");
    focusBbox(el.dataset.bbox.split(',').map(Number), page.image_width, page.image_height);
  });
  $("overlay").getContext("2d").clearRect(0, 0, $("overlay").width, $("overlay").height);
}

function renderHtmlPreview(page) {
  const items = [
    ...(page.lines || [])
      .filter(line => String(line.text || "").trim() && !String(line.source_type || "").includes("table_"))
      .map(line => ({ type: "text", bbox: line.bbox || [0, 0, 0, 0], payload: line })),
    ...(page.tables || [])
      .map(table => ({ type: "table", bbox: table.bbox || [0, 0, 0, 0], payload: table })),
    ...(page.images || [])
      .map(image => ({ type: "image", bbox: image.bbox || [0, 0, 0, 0], payload: image }))
  ].sort((a, b) => (a.bbox[1] - b.bbox[1]) || (a.bbox[0] - b.bbox[0]));

  $("htmlPreviewBox").innerHTML = items.map(item => {
    const bbox = item.bbox.join(",");
    if (item.type === "table") {
      return `<section class="preview-item preview-table" data-bbox="${bbox}">${renderPreviewTable(item.payload)}</section>`;
    }
    if (item.type === "image") {
      const image = item.payload;
      return `
        <figure class="preview-item preview-figure" data-bbox="${bbox}">
          <div class="figure-box">图片/图表区域</div>
          <figcaption>${escapeHtml(image.element_id)}${image.ext ? ` / ${escapeHtml(image.ext)}` : ""}</figcaption>
        </figure>
      `;
    }
    return `
      <section class="preview-item preview-text" data-bbox="${bbox}">
        ${String(item.payload.text || "").split("\n").filter(Boolean).map(part => `<p>${escapeHtml(part)}</p>`).join("")}
      </section>
    `;
  }).join("") || "<p class='small'>暂无可预览内容。</p>";

  document.querySelectorAll(".preview-item[data-bbox]").forEach(el => {
    el.onclick = () => {
      setActiveItem(el, ".preview-item");
      focusBbox(el.dataset.bbox.split(",").map(Number), page.image_width, page.image_height);
    };
  });
}

function renderPreviewTable(table) {
  const headers = table.headers?.length ? table.headers : Array.from({ length: table.column_count }, (_, idx) => `col_${idx + 1}`);
  return `
    <div class="preview-table-title">
      <strong>${escapeHtml(table.table_id)}</strong>
      ${badge(table.status)}
      <span class="small">${escapeHtml(table.strategy)} / ${table.row_count}x${table.column_count}</span>
    </div>
    <div class="table-scroll">
      <table>
        <thead><tr>${headers.map(header => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>
          ${(table.rows || []).map(row => `
            <tr>${headers.map(header => `<td>${escapeHtml(row.cells?.[header] ?? "")}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
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
      <strong>${escapeHtml(ev.chunk_id)}</strong> / 第 ${ev.page} 页 / score=${ev.score} / ${escapeHtml(ev.kind)}
      <div class="small">source_types=${escapeHtml((ev.source_types || []).join(", "))}；blocks=${escapeHtml((ev.source_block_ids || []).join(", "))}；warnings=${escapeHtml((ev.warnings || []).join(", "))}</div>
      ${renderEvidenceText(ev)}
    </div>
  `).join("") || "<p class='small'>无检索证据。</p>";
}

async function loadTableDetail(tableId, imageWidth, imageHeight) {
  const res = await fetch(`/api/docs/${state.docId}/tables/${tableId}`);
  if (!res.ok) return;
  const data = await res.json();
  $("tableDetails").innerHTML = renderStructuredTable(data.table, data.elements);
  document.querySelectorAll(".table-cell").forEach(cell => cell.onclick = () => {
    focusBbox(cell.dataset.bbox.split(',').map(Number), imageWidth, imageHeight);
  });
  document.querySelectorAll(".cell-review").forEach(btn => btn.onclick = async (event) => {
    event.stopPropagation();
    await markCellForReview(btn.dataset.tableId, btn.dataset.cellId, btn.dataset.value || "");
  });
}

function renderStructuredTable(table, elements = []) {
  const cellMap = new Map(elements.filter(item => item.element_type === "table_cell").map(item => [item.element_id, item]));
  const headers = table.headers?.length ? table.headers : Array.from({ length: table.column_count }, (_, idx) => `col_${idx + 1}`);
  return `
    <div class="table-structure">
      <div class="table-title">
        <strong>${escapeHtml(table.table_id)}</strong>
        ${badge(table.status)}
        <span class="small">${escapeHtml(table.strategy)} / ${table.row_count}x${table.column_count}</span>
      </div>
      <div class="table-scroll">
        <table>
          <thead><tr>${headers.map(header => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
          <tbody>
            ${(table.rows || []).map(row => `
              <tr>${headers.map((header, idx) => {
                const cellId = (row.cell_ids || [])[idx] || "";
                const cell = cellMap.get(cellId) || {};
                const bbox = (cell.bbox || [0, 0, 0, 0]).join(",");
                const value = row.cells?.[header] ?? "";
                return `<td class="table-cell" data-bbox="${bbox}">
                  <div>${escapeHtml(value)}</div>
                  <button class="secondary cell-review" data-table-id="${escapeHtml(table.table_id)}" data-cell-id="${escapeHtml(cellId)}" data-value="${escapeHtml(value)}">需复核</button>
                </td>`;
              }).join("")}</tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderEvidenceText(ev) {
  if (ev.kind === "table" && (ev.source_types || []).includes("table_json")) {
    try {
      const table = JSON.parse(ev.text);
      return renderStructuredTable(table, []);
    } catch {
      return `<pre>${escapeHtml(ev.text)}</pre>`;
    }
  }
  if (ev.kind === "table" && ev.text.includes("| ---")) {
    return markdownTableToHtml(ev.text);
  }
  return `<pre>${escapeHtml(ev.text)}</pre>`;
}

function markdownTableToHtml(text) {
  const lines = text.split("\n").filter(line => line.trim().startsWith("|"));
  if (lines.length < 2) return `<pre>${escapeHtml(text)}</pre>`;
  const rows = lines
    .filter(line => !/^\|\s*-+/.test(line))
    .map(line => line.split("|").slice(1, -1).map(cell => cell.trim()));
  const [headers, ...body] = rows;
  return `
    <div class="table-scroll">
      <table>
        <thead><tr>${headers.map(header => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>${body.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>
  `;
}

async function markCellForReview(tableId, cellId, value) {
  if (!state.docId || !cellId) return;
  const item = await postJson(`/api/docs/${state.docId}/reviews`, {
    question: `表格单元格复核 ${tableId}`,
    answer: value,
    evidence: [],
    result: "needs_fix",
    notes: "表格单元格需人工复核",
    target_element_ids: [cellId]
  });
  setStatus(`人工复核已记录：${item.item.result}`);
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

const statusEl = $("status");
const fileInputEl = $("fileInput");
statusEl.addEventListener("click", openUploadDialog);
statusEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    openUploadDialog(event);
  }
});
fileInputEl.addEventListener("click", (event) => event.stopPropagation());
fileInputEl.addEventListener("change", uploadPdf);
statusEl.dataset.uploadBound = "true";
fileInputEl.dataset.uploadBound = "true";
$("prevPage").onclick = () => loadPage(state.currentPage - 1);
$("nextPage").onclick = () => loadPage(state.currentPage + 1);
$("askBtn").onclick = ask;
$("saveReviewBtn").onclick = saveReview;
$("refreshReviews").onclick = loadReviews;
