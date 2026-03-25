async function apiJson(url, method, body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch { data = { raw: text }; }
  if (!res.ok) {
    const msg = data && data.detail ? data.detail : JSON.stringify(data);
    throw new Error(msg);
  }
  return data;
}

function setResult(text) {
  document.getElementById("result").textContent = text;
}

const tooltipEl = document.getElementById("tooltip");
const tagPreviewCache = new Map();

function hideTooltip() {
  tooltipEl.style.display = "none";
}

function showTooltip(text, x, y) {
  tooltipEl.textContent = text;
  tooltipEl.style.display = "block";
  tooltipEl.style.left = (x + 14) + "px";
  tooltipEl.style.top = (y + 14) + "px";
}

async function fetchTagPreview(tag) {
  if (tagPreviewCache.has(tag)) return tagPreviewCache.get(tag);
  const res = await apiJson(`/api/lore/preview?tag=${encodeURIComponent(tag)}&max_chars=220`, "GET", null);
  const preview = res.preview || "";
  tagPreviewCache.set(tag, preview);
  return preview;
}

function getSelectedTags() {
  const nodes = document.querySelectorAll('input[data-tag="1"]:checked');
  return Array.from(nodes).map(n => n.value);
}

async function loadLoreTags() {
  const res = await apiJson("/api/lore/tags", "GET", null);
  const container = document.getElementById("loreTags");
  container.innerHTML = "";

  const tags = res.tags || [];
  if (tags.length === 0) {
    container.textContent = "未找到 settings/*.md";
    return;
  }

  // 默认全选
  tags.forEach(tag => {
    const label = document.createElement("label");
    label.className = "tag-chip";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = true;
    cb.dataset.tag = "1";
    cb.value = tag;

    const name = document.createElement("span");
    name.className = "tag-name";
    name.textContent = tag;

    label.appendChild(cb);
    label.appendChild(name);

    // 悬浮展示预览内容（懒加载 + 缓存）
    label.addEventListener("mouseenter", async (e) => {
      try {
        const preview = await fetchTagPreview(tag);
        const text = preview ? preview : "（该 tag 没有可预览内容）";
        showTooltip(text, e.clientX, e.clientY);
      } catch (err) {
        showTooltip("加载预览失败：" + (err.message || err), e.clientX, e.clientY);
      }
    });
    label.addEventListener("mousemove", (e) => {
      if (tooltipEl.style.display === "none") return;
      tooltipEl.style.left = (e.clientX + 14) + "px";
      tooltipEl.style.top = (e.clientY + 14) + "px";
    });
    label.addEventListener("mouseleave", () => hideTooltip());

    container.appendChild(label);
  });
}

loadLoreTags().catch(e => {
  setResult("加载 lore tags 失败：" + e.message);
});

document.getElementById("btnSelectAll").addEventListener("click", () => {
  document.querySelectorAll('input[data-tag="1"]').forEach(n => { n.checked = true; });
});

document.getElementById("btnInvertSelect").addEventListener("click", () => {
  document.querySelectorAll('input[data-tag="1"]').forEach(n => { n.checked = !n.checked; });
});

document.getElementById("btnCreate").addEventListener("click", async () => {
  setResult("创建中...");
  const start_time_slot = document.getElementById("timeSlotOverride").value || null;
  const pov_character_id = document.getElementById("povCharacterOverride").value || null;
  const initial_user_task = document.getElementById("userTask").value || null;
  const lore_tags = getSelectedTags();

  try {
    const data = await apiJson("/api/novels", "POST", {
      start_time_slot,
      pov_character_id,
      initial_user_task,
      lore_tags,
    });
    document.getElementById("novelId").value = data.novel_id;
    setResult(`创建成功！novel_id = ${data.novel_id}\n\n接下来在页面里选择模式并点击“运行模式”。`);
  } catch (e) {
    setResult("创建失败：" + e.message);
  }
});

document.getElementById("btnRun").addEventListener("click", async () => {
  const novel_id = document.getElementById("novelId").value.trim();
  if (!novel_id) {
    setResult("请先创建新小说或填写 novel_id。");
    return;
  }

  const mode = document.getElementById("mode").value;
  const user_task = document.getElementById("userTask").value.trim();
  const chapter_index_raw = document.getElementById("chapterIndex").value;
  const chapter_index = chapter_index_raw ? Number(chapter_index_raw) : null;

  const time_slot_override = document.getElementById("timeSlotOverride").value || null;
  const pov_character_id_override = document.getElementById("povCharacterOverride").value || null;
  const lore_tags = getSelectedTags();

  if (!lore_tags || lore_tags.length === 0) {
    setResult("请至少勾选 1 项设定 tag（settings/*.md 文件名）。");
    return;
  }

  setResult("运行中（请耐心等待模型输出）...");
  try {
    const data = await apiJson(`/api/novels/${novel_id}/run`, "POST", {
      mode,
      user_task,
      chapter_index,
      time_slot_override,
      pov_character_id_override,
      lore_tags,
    });

    const header = [
      `mode=${data.mode}, chapter_index=${data.chapter_index}`,
      `state_updated=${data.state_updated}`,
      data.usage_metadata ? `usage=${JSON.stringify(data.usage_metadata)}` : "",
    ].filter(Boolean).join("\n");

    const continuity = data.state && data.state.continuity ? JSON.stringify(data.state.continuity, null, 2) : "";
    const stateTail = continuity ? `\n\n[continuity]\n${continuity}` : "";

    const content = data.content ? `\n\n[content]\n${data.content}` : "";
    const plan = data.plan ? `\n\n[plan]\n${JSON.stringify(data.plan, null, 2)}` : "";

    setResult(header + stateTail + content + plan);
  } catch (e) {
    setResult("运行失败：" + e.message);
  }
});

