(async () => {
  const IDS = `
200177, 201355, 200175
`.split(/[,\s]+/).map(x => x.trim()).filter(Boolean);

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let ok = 0, skip = 0, err = 0, done = 0;
  const started = new Date();

  const log = [
    `Batch approval RAM started: ${started.toISOString()}`,
    `Total IDs: ${IDS.length}`,
    `URL: ${location.href}`,
    ``,
    `status\tid_order\tdetail`
  ];

  const box = document.createElement("textarea");
  box.style = "position:fixed;z-index:2147483647;right:10px;bottom:10px;width:560px;height:300px;background:#101820;color:#f4f7fb;font:12px Consolas,monospace;border:2px solid #18a999;padding:8px;";
  document.body.appendChild(box);

  const btn = document.createElement("button");
  btn.textContent = "Download Log";
  btn.style = "position:fixed;z-index:2147483647;right:10px;bottom:320px;padding:8px 12px;background:#18a999;color:white;border:0;border-radius:4px;";
  document.body.appendChild(btn);

  btn.onclick = () => {
    const blob = new Blob([box.value], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `karina_approval_log_${new Date().toISOString().replace(/[:.]/g, "-")}.txt`;
    a.click();
  };

  const update = line => {
    if (line) log.push(line);
    box.value = log.join("\n");
    box.scrollTop = box.scrollHeight;
    document.title = `BATCH ${done}/${IDS.length} OK${ok} SK${skip} ER${err}`;
  };

  const token = (() => {
    const scripts = [...document.scripts].map(s => s.textContent || "").join("\n");
    const match = scripts.match(/"_token"\s*:\s*"([^"]+)"/);
    return match && match[1];
  })();

  if (!token) {
    update("ERROR\tALL\tCSRF token not found");
    return;
  }

  const $ = window.jQuery;
  let dt = null;
  if ($ && $.fn && $.fn.DataTable && $.fn.DataTable.isDataTable("#myTable5")) {
    dt = $("#myTable5").DataTable();
  }

  async function hasRow(id) {
    if (dt) {
      dt.column(1).search(id).draw();
      await sleep(80);
    }

    const rows = [...document.querySelectorAll("#myTable5 tbody tr")]
      .filter(r => r.offsetParent !== null);

    return rows.some(r => {
      const c = r.cells;
      return c && c[1] && c[1].textContent.trim() === id;
    });
  }

  function removeRow(id) {
    if (!dt) return;
    dt.rows((idx, data, node) => {
      const c = node && node.cells;
      return !!(c && c[1] && c[1].textContent.trim() === id);
    }).remove().draw(false);
  }

  function approve(id) {
    return new Promise(resolve => {
      $.ajax({
        type: "POST",
        url: "/newkarina/approval_ram",
        data: {
          _token: token,
          id_order: id,
          action: "approve"
        },
        success: res => {
          let json = null;
          try { json = JSON.parse(res); } catch {}
          resolve({ json, text: String(res).slice(0, 200) });
        },
        error: xhr => {
          resolve({ error: true, status: xhr && xhr.status });
        }
      });
    });
  }

  update();

  for (const id of IDS) {
    try {
      const exists = await hasRow(id);

      if (!exists) {
        skip++;
        done++;
        update(`SKIP\t${id}\tnot found in waiting table`);
        continue;
      }

      const res = await approve(id);

      if (res.json && res.json.status === "ok") {
        ok++;
        done++;
        removeRow(id);
        update(`OK\t${id}\tapproved`);
      } else {
        err++;
        done++;
        update(`ERROR\t${id}\t${JSON.stringify(res).slice(0, 180)}`);
      }

      await sleep(150);
    } catch (e) {
      err++;
      done++;
      update(`ERROR\t${id}\t${String(e).slice(0, 180)}`);
    }
  }

  if (dt) dt.column(1).search("").draw();

  log.push("");
  log.push(`Finished: ${new Date().toISOString()}`);
  log.push(`Summary: OK=${ok} SKIP=${skip} ERROR=${err}`);
  box.value = log.join("\n");
  document.title = `BATCH_DONE OK${ok} SK${skip} ER${err}`;
})();