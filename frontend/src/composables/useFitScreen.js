import { onBeforeUnmount, onMounted } from "vue";

/* 大屏等比缩放：设计稿 1920×1080，按窗口 min(w/1920, h/1080) 缩放并居中。
   注意：ECharts 尺寸读取 clientWidth（布局尺寸，不受 transform 影响），
   ThreeChinaMap 已改为 clientWidth 取尺寸，因此缩放不影响内部渲染分辨率。 */
export function useFitScreen(targetRef, designWidth = 1920, designHeight = 1080) {
  const fit = () => {
    const el = targetRef.value;
    if (!el) return;
    const scale = Math.min(window.innerWidth / designWidth, window.innerHeight / designHeight);
    el.style.transform = `scale(${scale})`;
    el.style.left = `${(window.innerWidth - designWidth * scale) / 2}px`;
    el.style.top = `${(window.innerHeight - designHeight * scale) / 2}px`;
  };
  onMounted(() => {
    fit();
    window.addEventListener("resize", fit);
  });
  onBeforeUnmount(() => window.removeEventListener("resize", fit));
}
