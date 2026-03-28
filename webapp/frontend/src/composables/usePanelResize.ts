import { onBeforeUnmount, ref } from "vue";

const LEFT_MIN_WIDTH = 280;
const LEFT_MAX_WIDTH = 680;
const MID_MIN_WIDTH = 340;
const MID_MAX_WIDTH = 760;

export function usePanelResize() {
  const leftPanelWidth = ref(360);
  const midPanelWidth = ref(420);

  let resizingLeft = false;
  let resizeStartX = 0;
  let resizeStartW = 0;

  let resizingMid = false;
  let midResizeStartX = 0;
  let midResizeStartW = 0;

  function onLeftResizeMove(e: MouseEvent) {
    if (!resizingLeft) return;
    const delta = e.clientX - resizeStartX;
    const next = Math.max(LEFT_MIN_WIDTH, Math.min(LEFT_MAX_WIDTH, resizeStartW + delta));
    leftPanelWidth.value = next;
  }

  function onLeftResizeUp() {
    if (!resizingLeft) return;
    resizingLeft = false;
    window.removeEventListener("mousemove", onLeftResizeMove);
    window.removeEventListener("mouseup", onLeftResizeUp);
  }

  function startResizeLeft(e: MouseEvent) {
    resizingLeft = true;
    resizeStartX = e.clientX;
    resizeStartW = leftPanelWidth.value;
    window.addEventListener("mousemove", onLeftResizeMove);
    window.addEventListener("mouseup", onLeftResizeUp);
  }

  function onMidResizeMove(e: MouseEvent) {
    if (!resizingMid) return;
    const delta = e.clientX - midResizeStartX;
    const next = Math.max(MID_MIN_WIDTH, Math.min(MID_MAX_WIDTH, midResizeStartW + delta));
    midPanelWidth.value = next;
  }

  function onMidResizeUp() {
    if (!resizingMid) return;
    resizingMid = false;
    window.removeEventListener("mousemove", onMidResizeMove);
    window.removeEventListener("mouseup", onMidResizeUp);
  }

  function startResizeMid(e: MouseEvent) {
    resizingMid = true;
    midResizeStartX = e.clientX;
    midResizeStartW = midPanelWidth.value;
    window.addEventListener("mousemove", onMidResizeMove);
    window.addEventListener("mouseup", onMidResizeUp);
  }

  onBeforeUnmount(() => {
    onLeftResizeUp();
    onMidResizeUp();
  });

  return {
    leftPanelWidth,
    midPanelWidth,
    startResizeLeft,
    startResizeMid,
  };
}
