(() => {
  const cart = new Map(),
    modal = document.getElementById("cart-modal");
  const money = (n) =>
    n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  const count = () => [...cart.values()].reduce((a, x) => a + x.qty, 0);
  function render() {
    const area = document.getElementById("cart-items"),
      totalEl = document.getElementById("cart-total");
    if (!area) return;
    area.innerHTML = "";
    let total = 0;
    if (!cart.size)
      area.innerHTML = '<p class="empty-cart">Seu carrinho está vazio.</p>';
    cart.forEach((x, id) => {
      total += x.price * x.qty;
      const row = document.createElement("div");
      row.className = "cart-row";
      row.innerHTML = `<div><b></b><small></small></div><div class="qty-control"><button data-minus="${id}">−</button><b>${x.qty}</b><button data-plus="${id}">+</button></div>`;
      row.querySelector("b").textContent = x.name;
      row.querySelector("small").textContent = money(x.price / 100) + " cada";
      area.appendChild(row);
    });
    totalEl.textContent = money(total / 100);
    document.getElementById("cart-count").textContent = count();
  }
  document.querySelectorAll(".add-button").forEach((btn) =>
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.id),
        old = cart.get(id);
      if (old) old.qty = Math.min(20, old.qty + 1);
      else cart.set(id, { name: btn.dataset.name, price: 0, qty: 1 });
      // O preço exibido é apenas informativo; o servidor consulta o banco e calcula o total real.
      const card = btn.closest(".product-card"),
        priceText = card.querySelector(".product-bottom strong").textContent;
      const numeric = Number(
        priceText.replace("R$", "").trim().replace(".", "").replace(",", "."),
      );
      cart.get(id).price = Math.round(numeric * 100);
      render();
    }),
  );
  document.getElementById("cart-open")?.addEventListener("click", () => {
    modal.classList.add("show");
    modal.setAttribute("aria-hidden", "false");
  });
  document.getElementById("cart-close")?.addEventListener("click", () => {
    modal.classList.remove("show");
    modal.setAttribute("aria-hidden", "true");
  });
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) modal.classList.remove("show");
  });
  document.getElementById("cart-items")?.addEventListener("click", (e) => {
    const minus = e.target.dataset.minus,
      plus = e.target.dataset.plus;
    if (minus) {
      const x = cart.get(Number(minus));
      x.qty--;
      if (x.qty <= 0) cart.delete(Number(minus));
    }
    if (plus) {
      const x = cart.get(Number(plus));
      x.qty = Math.min(20, x.qty + 1);
    }
    render();
  });
  document.querySelectorAll(".category-tab").forEach((btn) =>
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".category-tab")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document
        .querySelectorAll(".product-card")
        .forEach(
          (card) =>
            (card.hidden = card.dataset.category !== btn.dataset.filter),
        );
    }),
  );
  document
    .getElementById("checkout-form")
    ?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const feedback = document.getElementById("checkout-feedback");
      if (!cart.size) {
        feedback.textContent = "Adicione pelo menos um produto.";
        return;
      }
      const form = new FormData(e.currentTarget);
      const payload = {
        itens: [...cart.entries()].map(([produto_id, x]) => ({
          produto_id,
          quantidade: x.qty,
        })),
        endereco: form.get("endereco"),
        pagamento: form.get("pagamento"),
        observacao: form.get("observacao"),
      };
      const button = e.currentTarget.querySelector("button[type=submit]");
      button.disabled = true;
      feedback.textContent = "Enviando pedido...";
      try {
        const res = await fetch("/api/finalizar-pedido", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": token },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.erro || "Não foi possível enviar.");
        cart.clear();
        render();
        feedback.textContent = `Pedido #${data.pedido_id} enviado!`;
        setTimeout(() => (location.href = "/meus-pedidos"), 900);
      } catch (err) {
        feedback.textContent = err.message;
      } finally {
        button.disabled = false;
      }
    });
  render();
})();
