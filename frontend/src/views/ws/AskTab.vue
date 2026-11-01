<script setup lang="ts">
import { ArrowUp, Database, Download, LoaderCircle, RotateCcw, Square } from "lucide-vue-next";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink, useRouter } from "vue-router";

import { chatStream, del, get, post, waitForJob, type AIStatus, type ChatMessage, type Citation, type Job } from "@/api/client";
import { ago, int } from "@/lib/format";
import { renderAnswer } from "@/lib/markdown";
import { confirm } from "@/state/confirm";
import { fail, notify } from "@/state/toasts";
import { useWorkspace } from "@/state/workspace";

type Turn = { id: string; role: "user" | "assistant"; content: string; citations: Citation[]; mode?: string | null; streaming?: boolean; error?: string };

const { ws, reload } = useWorkspace();
const router = useRouter();
const status = ref<AIStatus | null>(null);
const turns = ref<Turn[]>([]);
const question = ref("");
const indexing = ref<{ progress: number; total: number } | null>(null);
const announce = ref("");
const log = ref<HTMLElement | null>(null);
let streamCtrl: AbortController | null = null;
const streaming = computed(() => turns.value.some((t) => t.streaming));

const SUGGESTIONS = [
  "Which ledgers and legal entities are configured?",
  "List the payment terms and their due days",
  "Which inventory organizations belong to each business unit?",
];

async function load() {
  if (!ws.value) return;
  try {
    status.value = await get<AIStatus>(`/workspaces/${ws.value.id}/ai`);
    if (status.value.index_job && !indexing.value) void follow(status.value.index_job);
    const history = await get<ChatMessage[]>(`/workspaces/${ws.value.id}/ai/messages`);
    turns.value = history.map((m) => ({ ...m, id: String(m.id) }));
    await scrollDown();
  } catch (e) {
    fail(e);
  }
}
watch(() => ws.value?.id, load, { immediate: true });
onBeforeUnmount(() => streamCtrl?.abort());

async function follow(job: Job) {
  indexing.value = { progress: job.progress, total: job.total };
  const final = await waitForJob(job.id, (j) => (indexing.value = { progress: j.progress, total: j.total }));
  indexing.value = null;
  if (final.status === "succeeded") notify(final.message);
  else fail(new Error(final.message), "Indexing failed");
  await Promise.all([load(), reload()]);
}

async function buildIndex() {
  if (!ws.value) return;
  try {
    void follow(await post<Job>(`/workspaces/${ws.value.id}/ai/index`));
  } catch (e) {
    fail(e);
  }
}

async function scrollDown() {
  await nextTick();
  log.value?.scrollTo({ top: log.value.scrollHeight });
}

async function ask(text = question.value) {
  const q = text.trim();
  if (!q || !ws.value || streaming.value) return;
  question.value = "";
  turns.value.push({ id: `u${Date.now()}`, role: "user", content: q, citations: [] });
  const reply: Turn = { id: `a${Date.now()}`, role: "assistant", content: "", citations: [], streaming: true };
  turns.value.push(reply);
  const live = turns.value[turns.value.length - 1]!;
  announce.value = "Answering…";
  await scrollDown();
  streamCtrl = new AbortController();
  try {
    for await (const ev of chatStream(ws.value.id, q, streamCtrl.signal)) {
      if (ev.event === "citations") live.citations = ev.data;
      else if (ev.event === "token") live.content += ev.data;
      else if (ev.event === "done") live.mode = ev.data.mode;
      else if (ev.event === "error") live.error = ev.data.message;
      if (ev.event === "token") void scrollDown();
    }
    announce.value = live.error ? `Answer failed: ${live.error}` : "Answer ready.";
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") live.error = "Stopped.";
    else live.error = fail(e);
  } finally {
    live.streaming = false;
    streamCtrl = null;
    await scrollDown();
  }
}

async function clear() {
  if (!ws.value || !(await confirm({ title: "Clear this conversation?", body: "All questions and answers in this workspace are deleted.", action: "Clear", danger: true }))) return;
  await del(`/workspaces/${ws.value.id}/ai/messages`);
  turns.value = [];
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    void ask();
  }
}

function openCitation(turn: Turn, n: number) {
  const c = turn.citations.find((x) => x.n === n);
  if (c) void router.push({ name: "data", query: { d: c.dataset_id, row: c.row } });
}
function onAnswerClick(turn: Turn, e: MouseEvent) {
  const btn = (e.target as HTMLElement).closest<HTMLElement>("[data-cite]");
  if (btn) openCitation(turn, Number(btn.dataset.cite));
}
</script>

<template>
  <div v-if="ws" class="ask">
    <p class="visually-hidden" role="status" aria-live="polite">{{ announce }}</p>

    <div v-if="!ws.datasets.length" class="setup panel">
      <Database aria-hidden="true" />
      <div>
        <h2>Convert first</h2>
        <p class="muted">Questions are answered from the converted datasets of this workspace.</p>
        <RouterLink :to="{ name: 'files' }" class="btn btn-sm">Review files</RouterLink>
      </div>
    </div>

    <div v-else-if="status && !status.indexed_at" class="setup panel">
      <Database aria-hidden="true" />
      <div>
        <h2>Build the search index</h2>
        <p class="muted">
          RET indexes every row of the {{ ws.datasets.length }} datasets so answers can quote exact records,
          with links back to the source row. Nothing leaves this server while indexing.
        </p>
        <button class="btn btn-primary" :disabled="!!indexing" :aria-busy="!!indexing" @click="buildIndex">
          <LoaderCircle v-if="indexing" class="spin" aria-hidden="true" />
          {{ indexing ? `Indexing ${indexing.total ? `${indexing.progress} / ${indexing.total} datasets` : "…"}` : "Build index" }}
        </button>
      </div>
    </div>

    <template v-else-if="status">
      <div class="meta">
        <p class="small muted num">
          <span class="badge" :class="status.llm_configured ? 'ok' : 'warn'">{{ status.llm_configured ? "AI answers" : "Retrieval only" }}</span>
          {{ int(status.indexed_rows) }} rows indexed {{ status.indexed_at ? ago(status.indexed_at) : "" }}
          <template v-if="!status.llm_configured"> · No AI model is configured, so answers list the best-matching records.</template>
        </p>
        <div class="meta-actions">
          <button class="btn btn-quiet btn-sm" :disabled="!!indexing" @click="buildIndex"><RotateCcw aria-hidden="true" /> Re-index</button>
          <a v-if="turns.length" class="btn btn-quiet btn-sm" :href="`/api/workspaces/${ws.id}/ai/transcript`" download><Download aria-hidden="true" /> Transcript</a>
          <button v-if="turns.length" class="btn btn-quiet btn-sm" @click="clear">Clear</button>
        </div>
      </div>

      <div ref="log" class="log" aria-label="Conversation">
        <div v-if="!turns.length" class="start">
          <p class="muted">Ask about the data in <strong>{{ ws.name }}</strong>. Answers cite the rows they come from.</p>
          <div class="suggest">
            <button v-for="s in SUGGESTIONS" :key="s" type="button" class="btn btn-sm" @click="ask(s)">{{ s }}</button>
          </div>
        </div>
        <article v-for="t in turns" :key="t.id" class="turn" :class="t.role">
          <p v-if="t.role === 'user'" class="q">{{ t.content }}</p>
          <template v-else>
            <div class="answer" @click="onAnswerClick(t, $event)">
              <span v-if="t.streaming && !t.content" class="thinking"><LoaderCircle class="spin" aria-hidden="true" /> Searching {{ int(status.indexed_rows) }} rows…</span>
              <!-- Sanitised by renderAnswer (DOMPurify); model output is untrusted. -->
              <div class="md" v-html="renderAnswer(t.content, t.citations.length)" />
              <p v-if="t.error" class="err small" role="alert">{{ t.error }}</p>
            </div>
            <ol v-if="t.citations.length && !t.streaming && t.mode !== 'retrieval'" class="sources" aria-label="Sources">
              <li v-for="c in t.citations" :key="c.n">
                <button type="button" class="src" @click="openCitation(t, c.n)">
                  <span class="cite">{{ c.n }}</span>
                  <span class="mono">{{ c.dataset }}</span><span class="subtle">row {{ int(c.row + 1) }}</span>
                </button>
              </li>
            </ol>
          </template>
        </article>
      </div>

      <form class="composer" @submit.prevent="ask()">
        <label for="q" class="visually-hidden">Your question</label>
        <textarea id="q" v-model="question" class="input" rows="2" maxlength="4000"
                  placeholder="Ask about ledgers, business units, payment terms…" @keydown="onKey" />
        <button v-if="streaming" type="button" class="btn btn-icon" aria-label="Stop answering" @click="streamCtrl?.abort()"><Square aria-hidden="true" /></button>
        <button v-else class="btn btn-primary btn-icon" aria-label="Send question" :disabled="!question.trim()"><ArrowUp aria-hidden="true" /></button>
      </form>
    </template>
  </div>
</template>

<style scoped>
.ask { display: grid; gap: var(--space-3); max-width: 980px; }
.setup { display: flex; gap: var(--space-4); padding: var(--space-5); max-width: 70ch;
  & > svg { width: 28px; height: 28px; flex: none; color: var(--gold-ink); }
  & > div { display: grid; gap: var(--space-2); justify-items: start; } & h2 { font-size: var(--text-lg); } }
.meta { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); flex-wrap: wrap;
  & p { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; } }
.meta-actions { display: flex; gap: 4px; }
.log {
  display: grid; gap: var(--space-4); align-content: start; min-height: 320px; max-height: 62vh; overflow-y: auto;
  padding: var(--space-4); background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-lg);
}
.start { display: grid; gap: var(--space-3); }
.suggest { display: flex; flex-wrap: wrap; gap: 6px; & .btn { white-space: normal; text-align: start; height: auto; padding: 6px 12px; } }
.turn.user { justify-self: end; max-width: 75%; }
.q { padding: 9px 14px; border-radius: 14px 14px 4px 14px; background: var(--sunken); white-space: pre-wrap; }
.turn.assistant { display: grid; gap: var(--space-2); max-width: 70ch; }
.thinking { display: inline-flex; align-items: center; gap: 8px; color: var(--ink-3); & svg { width: 16px; height: 16px; } }
.md :deep(p + p), .md :deep(ul), .md :deep(ol), .md :deep(table) { margin-top: 8px; }
.md :deep(ul), .md :deep(ol) { padding-left: 20px; margin-bottom: 0; }
.md :deep(table) { border-collapse: collapse; font-size: var(--text-sm); display: block; overflow-x: auto; }
.md :deep(th), .md :deep(td) { border: 1px solid var(--line); padding: 4px 8px; text-align: start; }
.md :deep(code) { background: var(--sunken); padding: 1px 4px; border-radius: 3px; }
.md :deep(.cite), .cite {
  display: inline-grid; place-items: center; min-width: 18px; height: 18px; padding: 0 4px; margin: 0 1px;
  border: 0; border-radius: 4px; background: var(--gold-wash); color: var(--gold-ink);
  font: 700 11px/1 var(--sans); vertical-align: 1px; cursor: pointer;
}
.md :deep(.cite:hover) { background: var(--gold); color: var(--on-gold); }
.err { color: var(--bad); }
.sources { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.src { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px 3px 4px; border: 1px solid var(--line); border-radius: var(--radius);
  background: var(--surface); color: var(--ink-2); font: inherit; font-size: var(--text-xs); cursor: pointer;
  &:hover { border-color: var(--gold-ink); color: var(--ink); } & .cite { cursor: inherit; } }
.composer { display: flex; gap: var(--space-2); align-items: flex-end;
  & textarea { resize: vertical; min-height: 44px; } & .btn { height: 44px; width: 44px; } }
@media (max-width: 640px) { .turn.user { max-width: 92%; } }
</style>
