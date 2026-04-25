import { reactive } from "vue";

export const DEFAULT_LLM_TEMPERATURE = 0.7;
export const DEFAULT_LLM_MAX_TOKENS = 20000;

export type AppFormModel = {
  novelId: string;
  eventMode: "existing" | "new";
  existingEventId: string;
  newEventTimeSlot: string;
  newEventSummary: string;
  newEventPrevId: string;
  newEventNextId: string;
  povCharacterOverride: string[];
  focusCharacterIds: string[];
  conflictChoice: string;
  foreshadowChoice: string;
  supportingPreset: string;
  chapterPresetName: string;
  currentMap: string;
  userTask: string;
  llmTemperature: number | null;
  llmTopP: number | null;
  llmMaxTokens: number | null;
};

export function createAppForm() {
  return reactive<AppFormModel>({
    novelId: "",
    eventMode: "existing",
    existingEventId: "",
    newEventTimeSlot: "",
    newEventSummary: "",
    newEventPrevId: "",
    newEventNextId: "",
    povCharacterOverride: [],
    focusCharacterIds: [],
    conflictChoice: "自动",
    foreshadowChoice: "自动",
    supportingPreset: "自动",
    chapterPresetName: "",
    currentMap: "",
    userTask: "",
    llmTemperature: DEFAULT_LLM_TEMPERATURE,
    llmTopP: null,
    llmMaxTokens: DEFAULT_LLM_MAX_TOKENS,
  });
}

