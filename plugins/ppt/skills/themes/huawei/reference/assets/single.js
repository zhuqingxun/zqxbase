/* 单页模板自适应缩放：按视口等比缩放 1920×1080 胶片 */
(function () {
  function fit() {
    const slide = document.querySelector('.slide');
    if (!slide) return;
    const vw = window.innerWidth, vh = window.innerHeight;
    const scale = Math.min(vw / 1920, vh / 1080);
    slide.style.transform = `scale(${scale})`;
  }
  document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.add('single');
    fit();
    window.addEventListener('resize', fit);
  });
})();
