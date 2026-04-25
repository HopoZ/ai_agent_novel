import { nextTick, type Ref } from "vue";
import { normalizeTag, scopeTagsForNovel } from "../domain/tags";

type TagTreeRef = {
  setCheckedKeys: (k: unknown[], leafOnly?: boolean) => void;
  getCheckedKeys: (leafOnly?: boolean) => unknown[];
  getHalfCheckedKeys: () => unknown[];
} | null;

export function applyTagScopeForCurrentNovel(params: {
  novelId: string;
  allTags: string[];
  selectedTags: string[];
  setTags: (rows: string[]) => void;
  setSelectedTags: (rows: string[]) => void;
  clearTagGroups: () => void;
}) {
  const scoped = scopeTagsForNovel(params.allTags, params.novelId);
  params.setTags(scoped);
  const existed = new Set((params.selectedTags || []).map((x) => normalizeTag(x)));
  params.setSelectedTags(scoped.filter((t) => existed.has(normalizeTag(t))));
  params.clearTagGroups();
}

export function syncTagTreeChecked(tagTreeRef: Ref<TagTreeRef>, selectedTags: Ref<string[]>) {
  nextTick(() => {
    if (tagTreeRef.value) tagTreeRef.value.setCheckedKeys([...selectedTags.value], false);
  });
}

export function selectAllTags(tags: Ref<string[]>, selectedTags: Ref<string[]>, tagTreeRef: Ref<TagTreeRef>) {
  selectedTags.value = [...tags.value];
  syncTagTreeChecked(tagTreeRef, selectedTags);
}

export function clearAllTags(selectedTags: Ref<string[]>, tagTreeRef: Ref<TagTreeRef>) {
  selectedTags.value = [];
  syncTagTreeChecked(tagTreeRef, selectedTags);
}

export function invertTags(tags: Ref<string[]>, selectedTags: Ref<string[]>, tagTreeRef: Ref<TagTreeRef>) {
  const set = new Set(selectedTags.value);
  selectedTags.value = tags.value.filter((t) => !set.has(t));
  syncTagTreeChecked(tagTreeRef, selectedTags);
}

export function onTagTreeCheck(tags: Ref<string[]>, selectedTags: Ref<string[]>, tagTreeRef: Ref<TagTreeRef>) {
  if (!tagTreeRef.value) return;
  const checkedKeys: string[] = (tagTreeRef.value.getCheckedKeys(false) || []) as string[];
  const halfKeys: string[] = (tagTreeRef.value.getHalfCheckedKeys() || []) as string[];
  const all = [...checkedKeys, ...halfKeys];
  selectedTags.value = all.filter((k) => tags.value.includes(k));
}

