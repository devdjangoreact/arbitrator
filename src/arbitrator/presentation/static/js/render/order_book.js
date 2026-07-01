/** @param {object} lvl @param {"ask"|"bid"} side */
function renderObRow(lvl, side) {
  const cumPct = Math.min(100, Math.max(0, lvl.fill_pct));
  const amount = Number(lvl.amount) || 0;
  const total = Number(lvl.total) || 0;
  const lvlShare = total > 0 ? Math.min(100, Math.max(0, (amount / total) * 100)) : 0;
  const lvlBar =
    lvlShare > 0
      ? `<div class="ob-fill lvl ${side}" style="width:${lvlShare}%"></div>`
      : "";
  return `
    <div class="ob-row">
      <div class="ob-fill cum ${side}" style="width:${cumPct}%">${lvlBar}</div>
      <div class="ob-text ${side}">
        <span class="ob-col-price">${fmtNum(lvl.price, 5)}</span>
        <span class="ob-col-total">${compactK(lvl.total)}</span>
      </div>
    </div>`;
}

/** @param {object} book */
function renderBookCard(book) {
  const roleTag = book.side_role === "short" ? "ob-tag-short" : "ob-tag-long";
  const roleLetter = book.side_role === "short" ? "S" : "L";
  const mtypeTag = book.market_type === "futures" ? "ob-tag-fut" : "ob-tag-spot";
  const midCls = book.side_role === "short" ? "short" : "long";
  const bookKey = `${book.exchange_id}-${book.market_type}`;

  const askRows = (book.asks || []).slice(0, 10).map((lvl) => renderObRow(lvl, "ask")).join("");
  const bidRows = (book.bids || []).slice(0, 10).map((lvl) => renderObRow(lvl, "bid")).join("");

  return `
    <div class="card" data-book="${bookKey}">
      <div class="ob-top">
        <span class="ob-top-meta">${book.exchange_id.toUpperCase()} <span class="${roleTag}">${roleLetter}</span> · <span class="${mtypeTag}">${book.market_type === "futures" ? "F" : "S"}</span> · ${book.volume_24h_label} · ${book.range_label}</span>
        <div class="ob-squeeze">
          <button class="btn btn-squeeze active" type="button">1</button>
          <button class="btn btn-squeeze" type="button">2</button>
          <button class="btn btn-squeeze" type="button">5</button>
          <button class="btn btn-squeeze" type="button">10</button>
          <input class="ob-squeeze-val" type="text" value="1" title="Зжимання">
        </div>
      </div>
      <div class="ob-text-head"><span>Ціна</span><span>Сума</span></div>
      <div class="ob-body">
        <div class="ob-side">${askRows}</div>
        <div class="ob-mid-bar"><span class="ob-mid-price ${midCls}">${fmtNum(book.mid_price, 5)}</span></div>
        <div class="ob-side">${bidRows}</div>
      </div>
    </div>`;
}

/** @param {HTMLElement} root @param {object[]} books */
function renderOrderBooks(root, books) {
  if (!root) return;
  const shortBooks = books.filter((b) => b.side_role === "short");
  const longBooks = books.filter((b) => b.side_role === "long");
  root.innerHTML = `
    <div class="ob-market-row">
      <div class="ob-market-col">${shortBooks.map(renderBookCard).join("")}</div>
      <div class="ob-market-col">${longBooks.map(renderBookCard).join("")}</div>
    </div>`;
  bindObSqueeze(root);
}

/** @param {HTMLElement} root @param {object} book */
function patchOrderBook(root, book) {
  const bookKey = `${book.exchange_id}-${book.market_type}`;
  const card = root.querySelector(`[data-book="${bookKey}"]`);
  if (!card) return;
  const meta = card.querySelector(".ob-top-meta");
  const roleTag = book.side_role === "short" ? "ob-tag-short" : "ob-tag-long";
  const roleLetter = book.side_role === "short" ? "S" : "L";
  const mtypeTag = book.market_type === "futures" ? "ob-tag-fut" : "ob-tag-spot";
  if (meta) {
    meta.innerHTML = `${book.exchange_id.toUpperCase()} <span class="${roleTag}">${roleLetter}</span> · <span class="${mtypeTag}">${book.market_type === "futures" ? "F" : "S"}</span> · ${book.volume_24h_label} · ${book.range_label}`;
  }
  const mid = card.querySelector(".ob-mid-price");
  if (mid) {
    mid.textContent = fmtNum(book.mid_price, 5);
    mid.className = `ob-mid-price ${book.side_role === "short" ? "short" : "long"}`;
  }
  const sides = card.querySelectorAll(".ob-side");
  const askSide = sides[0];
  const bidSide = sides[1];
  if (askSide) {
    askSide.innerHTML = (book.asks || []).slice(0, 10).map((lvl) => renderObRow(lvl, "ask")).join("");
  }
  if (bidSide) {
    bidSide.innerHTML = (book.bids || []).slice(0, 10).map((lvl) => renderObRow(lvl, "bid")).join("");
  }
}

function bindObSqueeze(root) {
  root.querySelectorAll(".ob-squeeze").forEach((group) => {
    const inp = group.querySelector(".ob-squeeze-val");
    group.querySelectorAll(".btn-squeeze").forEach((btn) => {
      btn.addEventListener("click", () => {
        group.querySelectorAll(".btn-squeeze").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        if (inp) inp.value = btn.textContent.trim();
      });
    });
    inp?.addEventListener("input", () => {
      group.querySelectorAll(".btn-squeeze").forEach((b) => b.classList.remove("active"));
    });
  });
}

window.renderOrderBooks = renderOrderBooks;
window.patchOrderBook = patchOrderBook;
window.bindObSqueeze = bindObSqueeze;
