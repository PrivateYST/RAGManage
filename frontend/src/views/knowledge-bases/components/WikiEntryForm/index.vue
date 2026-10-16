<!-- 词条内容表单：编辑名称、别名、负责人、有效期并选择原文，不要求手填 ID。 -->
<script setup lang="ts">
import type { WikiEntryFormProps } from './type'
import type { WikiPayload } from '@/api/wiki'
import { useWikiEntryForm } from './index'
import './index.scss'
defineProps<WikiEntryFormProps>()
const emit = defineEmits<{ save: []; cancel: []; search: [] }>()
const model = defineModel<WikiPayload>({ required: true })
const sourceQuery = defineModel<string>('sourceQuery', { required: true })
const { aliases, toggleSource } = useWikiEntryForm(model)
</script>
<template>
  <!-- 表单是弹窗内部区块，不复用 dialog-card 的固定宽度和独立白卡片外观。 -->
  <form
    class="dialog-card flex min-h-0 w-full min-w-0 max-w-none flex-1 flex-col overflow-hidden rounded-none border-0 bg-transparent p-0 shadow-none"
    @submit.prevent="emit('save')"
  >
    <!-- 表单字段独立滚动，底部保存/取消始终可见，避免长来源列表挤出提交操作。 -->
    <div class="grid min-h-0 flex-1 gap-[20px] overflow-y-auto pr-[8px]">
      <div class="rounded-md border border-border bg-secondary/40 px-[16px] py-[12px]">
        <h3 class="text-sm font-semibold">{{ editing ? '编辑词条' : '创建词条草稿' }}</h3>
        <p class="mt-[6px] text-xs text-muted-foreground">
          保存为草稿，审核发布后生效；修改已发布内容需重新审核。
        </p>
      </div>
      <section class="min-w-0" aria-label="词条基本信息">
        <h4 class="text-sm font-semibold">基本信息</h4>
        <label
          >词条名称<input
            v-model.trim="model.term"
            required
            minlength="2"
            maxlength="200"
            placeholder="例如：0～6岁儿童健康管理服务"
            :disabled="busy"
        /></label>
        <label
          >定义<textarea
            v-model.trim="model.definition"
            rows="3"
            maxlength="10000"
            required
            placeholder="写出可审核的规范定义"
            :disabled="busy"
          />
        </label>
        <label
          >别名<input
            v-model.lazy="aliases"
            maxlength="2000"
            placeholder="多个别名用逗号分隔"
            :disabled="busy"
        /></label>
      </section>
      <section class="min-w-0 border-t border-border pt-[16px]" aria-label="词条治理信息">
        <h4 class="text-sm font-semibold">负责人和有效期</h4>
        <label
          >负责人<select v-model="model.owner_user_id" :disabled="busy">
            <option :value="null">未指定（送审前须指定）</option>
            <option v-for="member in options.members" :key="member.id" :value="Number(member.id)">
              {{ member.display_name }}
            </option>
          </select></label
        >
        <div class="grid grid-cols-1 gap-[12px] sm:grid-cols-2">
          <label>有效期起始<input v-model="model.valid_from" type="date" :disabled="busy" /></label
          ><label
            >有效期截止<input v-model="model.valid_until" type="date" :disabled="busy"
          /></label>
        </div>
      </section>
      <fieldset class="m-0 grid min-w-0 gap-[12px] rounded-lg border border-border p-[16px]">
        <legend class="px-[6px] text-sm font-semibold">
          原文来源（已选择 {{ model.sources.length }} 条）
        </legend>
        <div class="flex gap-[8px]">
          <input
            v-model="sourceQuery"
            class="min-w-0 flex-1 rounded-md border border-input bg-background px-[12px] py-[8px] text-sm"
            aria-label="搜索原文"
            placeholder="输入正文关键词筛选，如：新生儿家庭访视"
            @keydown.enter.prevent="emit('search')"
          /><button
            class="secondary-button"
            type="button"
            :disabled="searching || busy"
            @click="emit('search')"
          >
            {{ searching ? '搜索中…' : '搜索原文' }}
          </button>
        </div>
        <div
          class="grid max-h-[220px] gap-[8px] overflow-y-auto rounded-md border border-border p-[8px]"
        >
          <label
            v-for="source in options.sources"
            :key="source.chunk_id"
            class="m-0 flex cursor-pointer items-start gap-[10px] rounded-md p-[10px] hover:bg-secondary"
          >
            <input
              type="checkbox"
              class="mt-[3px] h-[16px] w-[16px] shrink-0"
              :checked="model.sources.some((item) => item.chunk_id === Number(source.chunk_id))"
              :disabled="busy"
              @change="toggleSource(source.chunk_id)"
            />
            <span class="min-w-0"
              ><strong class="text-sm"
                >{{ source.document_title }} · v{{ source.version_no }} ·
                {{ source.locator?.page ? `第 ${source.locator.page} 页` : '原文' }}</strong
              ><span class="mt-[6px] block line-clamp-3 text-xs text-muted-foreground">{{
                source.content
              }}</span></span
            >
          </label>
          <p v-if="!options.sources.length" class="p-2 text-sm text-muted-foreground">
            没有匹配的已发布原文，请更换关键词或先发布文档。
          </p>
        </div>
        <p class="text-xs text-muted-foreground">
          最多显示 100 条。可搜索后继续选择；已选来源会保留。送审前须关联至少一条原文。
        </p>
      </fieldset>
    </div>
    <div class="dialog-actions shrink-0 bg-background">
      <button type="button" class="secondary-button" :disabled="busy" @click="emit('cancel')">
        取消</button
      ><button class="primary-button" :disabled="busy">{{ busy ? '保存中…' : '保存草稿' }}</button>
    </div>
  </form>
</template>
