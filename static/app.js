// 표 위의 검색 상자: 글자와 구분으로 행을 걸러 낸다. 구분은 행의 data-key와 비교한다.
document.querySelectorAll(".filter[data-filter-for]").forEach((box) => {
  const table = document.getElementById(box.dataset.filterFor);
  if (!table) return;
  const input = box.querySelector("input");
  const select = box.querySelector("select");
  const count = box.querySelector(".count");
  const rows = [...table.tBodies[0].rows];
  const apply = () => {
    const q = (input?.value || "").trim().toLowerCase();
    const key = select?.value || "";
    let shown = 0;
    rows.forEach((row) => {
      const ok = (!q || row.textContent.toLowerCase().includes(q)) && (!key || row.dataset.key === key);
      row.hidden = !ok;
      if (ok) shown += 1;
    });
    if (count) count.textContent = q || key ? `${shown} / ${rows.length}건` : `${rows.length}건`;
  };
  input?.addEventListener("input", apply);
  select?.addEventListener("change", apply);
  apply();
});

// 표 머리를 누르면 그 열로 정렬한다. 숫자 열은 칸의 data-v 값을 쓴다.
document.querySelectorAll("table[data-sortable]").forEach((table) => {
  const heads = [...table.tHead.rows[0].cells];
  heads.forEach((th, col) => {
    if (th.dataset.type === "none") { th.style.cursor = "default"; return; }
    th.addEventListener("click", () => {
      // 처음 누르면 큰 값부터, 다시 누르면 작은 값부터
      const asc = th.getAttribute("aria-sort") === "descending";
      const numeric = th.dataset.type === "num";
      const key = (row) => {
        const cell = row.cells[col];
        if (!numeric) return cell.textContent.trim();
        const v = cell.dataset.v;
        return v === undefined || v === "" ? null : Number(v);
      };
      const rows = [...table.tBodies[0].rows].sort((a, b) => {
        const x = key(a), y = key(b);
        if (x === null) return 1;   // 값이 없는 칸은 항상 아래로
        if (y === null) return -1;
        const d = numeric ? x - y : x.localeCompare(y, "ko");
        return asc ? d : -d;
      });
      rows.forEach((r) => table.tBodies[0].appendChild(r));
      heads.forEach((h) => h.removeAttribute("aria-sort"));
      th.setAttribute("aria-sort", asc ? "ascending" : "descending");
    });
  });
});
