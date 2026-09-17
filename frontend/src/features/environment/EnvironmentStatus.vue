<script setup lang="ts">
import { onMounted, onUnmounted, shallowRef } from "vue";
import { fetchHealth, type Health } from "../../api/health";

const health = shallowRef<Health | null>(null);
const error = shallowRef("");
const loading = shallowRef(false);
let controller: AbortController | undefined;
const labels: Record<string, string> = {
  database: "PostgreSQL / pgvector",
  redis: "Redis",
  storage: "文件存储",
};
const statuses: Record<string, string> = {
  ok: "正常",
  unavailable: "无法连接",
  unconfigured: "待配置",
  vector_unavailable: "扩展未就绪",
};

async function refresh() {
  controller?.abort();
  const current = new AbortController();
  controller = current;
  loading.value = true;
  error.value = "";
  health.value = null;
  const timeout = setTimeout(() => current.abort(), 10000);
  try {
    health.value = await fetchHealth(current.signal);
  } catch {
    error.value = "暂时无法连接后端，请检查服务是否启动后重试。";
  } finally {
    clearTimeout(timeout);
    loading.value = false;
  }
}
onMounted(refresh);
onUnmounted(() => controller?.abort());
</script>

<template>
  <div class="card" :aria-busy="loading">
    <div class="card-header">
      <h2>服务状态</h2>
      <button type="button" :disabled="loading" @click="refresh">
        {{ loading ? "检查中…" : "重新检查" }}
      </button>
    </div>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-else-if="loading" role="status">正在连接本地服务…</p>
    <template v-else-if="health">
      <p role="status">
        {{ health.status === "ready" ? "基础服务已就绪" : "部分服务尚未就绪" }}
      </p>
      <dl class="checks">
        <div v-for="(status, name) in health.checks" :key="name">
          <dt>{{ labels[name] ?? name }}</dt>
          <dd :class="status === 'ok' ? 'success' : 'muted'">
            {{ statuses[status] ?? "待检查" }}
          </dd>
        </div>
      </dl>
    </template>
  </div>
</template>
