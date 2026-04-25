export function formatConsistencyAudit(raw: unknown): { text: string; severity: "ok" | "warn" | "high" } {
  if (!raw || typeof raw !== "object") return { text: "", severity: "ok" };
  const x = raw as {
    score?: unknown;
    severity?: unknown;
    issue_count?: unknown;
    block_reasons?: Array<{ message?: unknown }>;
    recommended_actions?: Array<unknown>;
    issues?: Array<{ level?: unknown; message?: unknown; suggestion?: unknown }>;
  };
  const sev = String(x.severity || "ok");
  const severity: "ok" | "warn" | "high" = sev === "high" ? "high" : sev === "warn" ? "warn" : "ok";
  const score = Number(x.score ?? Number.NaN);
  const issueCount = Number(x.issue_count ?? 0);
  const issues = Array.isArray(x.issues) ? x.issues : [];
  const lines: string[] = [];
  lines.push(`评分：${Number.isFinite(score) ? score : "-"} / 100`);
  lines.push(`问题数：${Number.isFinite(issueCount) ? issueCount : issues.length}`);
  if (!issues.length) {
    lines.push("未发现明显一致性问题。");
  } else {
    const top = issues.slice(0, 4);
    for (const it of top) {
      const lvl = String(it?.level || "warn").toUpperCase();
      const msg = String(it?.message || "").trim();
      const sug = String(it?.suggestion || "").trim();
      if (msg) lines.push(`[${lvl}] ${msg}`);
      if (sug) lines.push(`  建议：${sug}`);
    }
    if (issues.length > top.length) {
      lines.push(`... 另有 ${issues.length - top.length} 条，可在后端返回中查看详情。`);
    }
  }
  const br = Array.isArray(x.block_reasons) ? x.block_reasons : [];
  if (br.length > 0) {
    lines.push("阻断原因：");
    for (const it of br.slice(0, 3)) {
      const msg = String(it?.message || "").trim();
      if (msg) lines.push(`- ${msg}`);
    }
  }
  const acts = Array.isArray(x.recommended_actions) ? x.recommended_actions : [];
  if (acts.length > 0) {
    lines.push("修复动作：");
    for (const a of acts.slice(0, 3)) {
      const txt = String(a || "").trim();
      if (txt) lines.push(`- ${txt}`);
    }
  }
  return { text: lines.join("\n"), severity };
}

export function buildShadowDigest(
  donePayload: Record<string, unknown>,
  modeStr: string,
  chapterTimelineEventId: string
): string {
  const blocks: string[] = [];
  if (modeStr) blocks.push(`模式：${modeStr}`);
  const chapterIndex = donePayload.chapter_index;
  if (chapterIndex != null && chapterIndex !== "") blocks.push(`章节：${String(chapterIndex)}`);
  if (chapterTimelineEventId) blocks.push(`事件归属：${chapterTimelineEventId}`);
  const plan = donePayload.plan as Record<string, unknown> | null | undefined;
  if (plan && typeof plan === "object") {
    const beats = Array.isArray(plan.beats) ? plan.beats.length : 0;
    if (beats > 0) blocks.push(`规划节拍：${beats} 条`);
    const timeSlot = String(plan.time_slot || "").trim();
    if (timeSlot) blocks.push(`时间段：${timeSlot}`);
  }
  const nextStatus = String(donePayload.next_status || "").trim();
  if (nextStatus) {
    const short = nextStatus.length > 160 ? `${nextStatus.slice(0, 160)}...` : nextStatus;
    blocks.push(`下章建议摘要：${short}`);
  }
  const sd = donePayload.shadow_director as Record<string, unknown> | null | undefined;
  if (sd && typeof sd === "object") {
    const digest = String(sd.digest || "").trim();
    if (digest) blocks.push(`导演策略：${digest}`);
  }
  return blocks.join("\n");
}

export function formatAutoRejudge(raw: unknown): string {
  if (!raw || typeof raw !== "object") return "";
  const x = raw as {
    effective_pov_ids?: Array<unknown>;
    effective_supporting_character_ids?: Array<unknown>;
    effective_shadow_director_guidance?: { conflict_type?: unknown; foreshadow_target?: unknown } | null;
    manual_pov?: unknown;
    manual_supporting?: unknown;
    event_plan_id?: unknown;
  };
  const pov = (Array.isArray(x.effective_pov_ids) ? x.effective_pov_ids : [])
    .map((v) => String(v || "").trim())
    .filter(Boolean);
  const sup = (Array.isArray(x.effective_supporting_character_ids) ? x.effective_supporting_character_ids : [])
    .map((v) => String(v || "").trim())
    .filter(Boolean);
  const g = x.effective_shadow_director_guidance && typeof x.effective_shadow_director_guidance === "object"
    ? x.effective_shadow_director_guidance
    : null;
  const rows: string[] = [];
  if (x.event_plan_id) rows.push(`事件计划：${String(x.event_plan_id)}`);
  rows.push(`主视角：${pov.length ? pov.join("、") : "未判定"}`);
  rows.push(`配角：${sup.length ? sup.join("、") : "自动/无"}`);
  const c = String(g?.conflict_type || "").trim();
  const f = String(g?.foreshadow_target || "").trim();
  if (c) rows.push(`冲突：${c}`);
  if (f) rows.push(`伏笔：${f}`);
  rows.push(
    `来源：POV${Boolean(x.manual_pov) ? "手动" : "自动"}，配角${Boolean(x.manual_supporting) ? "手动" : "自动"}`
  );
  return rows.join("\n");
}

