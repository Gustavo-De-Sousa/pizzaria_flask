document.querySelectorAll("[data-countdown]").forEach((el) => {
  const end = new Date(el.dataset.countdown);
  function tick() {
    const ms = end - new Date();
    if (ms <= 0) {
      el.textContent = "Promoção encerrada";
      return;
    }
    const h = Math.floor(ms / 3600000),
      m = Math.floor((ms % 3600000) / 60000),
      s = Math.floor((ms % 60000) / 1000);
    el.textContent = `Termina em ${h}h ${m}m ${s}s`;
    setTimeout(tick, 1000);
  }
  tick();
});
