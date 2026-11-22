(() => {
  const root = document.getElementById("admin-orders");
  if (!root) return;
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  const money = (n) =>
    n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  let lastSignature = "";
  async function refresh() {
    try {
      const res = await fetch("/admin/pedidos.json", {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) return;
      const pedidos = await res.json();
      document.getElementById("admin-order-count").textContent = pedidos.length;
      const signature = JSON.stringify(pedidos);
      if (signature === lastSignature) return;
      lastSignature = signature;
      root.innerHTML = "";
      if (!pedidos.length) {
        root.textContent = "Nenhum pedido recebido ainda.";
        return;
      }
      pedidos.forEach((p) => {
        const card = document.createElement("article");
        card.className = "admin-order";
        const head = document.createElement("div");
        head.className = "admin-order-head";
        const title = document.createElement("b");
        title.textContent = `Pedido #${p.id} · ${p.cliente}`;
        const date = document.createElement("small");
        date.textContent = p.criado_em;
        const left = document.createElement("div");
        left.append(title, date);
        const total = document.createElement("strong");
        total.textContent = money(p.total);
        head.append(left, total);
        card.append(head);
        p.itens.forEach((i) => {
          const line = document.createElement("p");
          line.textContent = `${i.quantidade}x ${i.nome} — ${money(i.preco * i.quantidade)}`;
          card.append(line);
        });
        const addr = document.createElement("p");
        addr.className = "muted";
        addr.textContent = `📍 ${p.endereco} · ${p.pagamento}`;
        card.append(addr);
        if (p.observacao) {
          const obs = document.createElement("p");
          obs.className = "muted";
          obs.textContent = `Obs.: ${p.observacao}`;
          card.append(obs);
        }
        const actions = document.createElement("div");
        actions.className = "admin-order-actions";
        const status = document.createElement("span");
        status.className = "status";
        status.textContent = p.status;
        actions.append(status);
        const form = document.createElement("form");
        form.method = "post";
        form.action = `/admin/pedido/${p.id}/status`;
        const csrf = document.createElement("input");
        csrf.type = "hidden";
        csrf.name = "csrf_token";
        csrf.value = token;
        form.append(csrf);
        const select = document.createElement("select");
        select.name = "status";
        [
          "Recebido",
          "Em preparo",
          "Saiu para entrega",
          "Concluído",
          "Cancelado",
        ].forEach((s) => {
          const o = document.createElement("option");
          o.textContent = s;
          o.value = s;
          o.selected = s === p.status;
          select.append(o);
        });
        const submit = document.createElement("button");
        submit.className = "btn btn-primary btn-small";
        submit.textContent = "Atualizar";
        const print = document.createElement("button");
        print.type = "button";
        print.className = "btn btn-outline btn-small";
        print.textContent = "Imprimir";
        print.onclick = () => window.print();
        form.append(select, submit, print);
        actions.append(form);
        card.append(actions);
        root.append(card);
      });
    } catch (e) {
      /* próxima atualização tentará novamente */
    }
  }
  refresh();
  setInterval(refresh, 8000);
})();
