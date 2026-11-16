(() => {
  const state = {
    query: "",
    status: "active",
    category: "",
    atelier_store: "",
    source_mod: "",
    body_type: "",
    quality: "",
    tag: "",
    sort_by: "name",
    sort_dir: "asc",
    page: 1,
    page_size: 48,
    selectedIds: new Set(),
    currentItems: [],
    inspectedItem: null,
    activeSave: null,
  };

  const viewer3d = new window.MeshViewer3D(document.getElementById("meshCanvas"));

  function showToast(msg) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => el.classList.add("hidden"), 2800);
  }

  async function api(url, opts = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function populateSelect(el, countsObj, defaultLabel) {
    const current = el.value;
    el.innerHTML = `<option value="">${defaultLabel}</option>`;
    Object.entries(countsObj || {})
      .sort((a, b) => a[0].localeCompare(b[0]))
      .forEach(([name, count]) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = `${name} (${count})`;
        el.appendChild(opt);
      });
    el.value = current;
  }

  function renderTags(tagCounts) {
    const cloud = document.getElementById("tagCloud");
    cloud.innerHTML = "";
    Object.entries(tagCounts || {}).forEach(([tag, count]) => {
      const btn = document.createElement("button");
      btn.className = `tag-pill ${state.tag === tag ? "active" : ""}`;
      btn.textContent = `${tag} (${count})`;
      btn.onclick = () => {
        state.tag = state.tag === tag ? "" : tag;
        state.page = 1;
        loadItems();
      };
      cloud.appendChild(btn);
    });
  }

  function qualityColor(quality) {
    switch ((quality || "").toLowerCase()) {
      case "iconic": return "#fcee09";
      case "legendary": return "#ff7b00";
      case "epic": return "#b84dff";
      case "rare": return "#05d9e8";
      case "uncommon": return "#2ee59d";
      default: return "#8b93b0";
    }
  }

  function categorySvgShape(category, color) {
    switch (category) {
      case "Outer Torso":
      case "Outfit":
        return `<path d="M95 36 L130 24 L160 36 L190 24 L225 36 L245 85 L220 96 L208 66 L208 175 L112 175 L112 66 L100 96 L75 85 Z" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>`;
      case "Inner Torso":
        return `<path d="M115 34 L140 26 L160 40 L180 26 L205 34 L222 70 L200 78 L195 168 L125 168 L120 78 L98 70 Z" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>`;
      case "Legs":
        return `<path d="M115 30 L205 30 L215 175 L175 175 L160 95 L145 175 L105 175 Z" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>`;
      case "Feet":
        return `<path d="M108 40 L146 40 L150 135 L195 152 L195 172 L105 172 Z" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>`;
      case "Head":
        return `<path d="M105 120 C105 55, 215 55, 215 120 L222 148 L98 148 Z" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>`;
      case "Face":
        return `<path d="M88 85 L232 85 L220 124 L176 124 L160 108 L144 124 L100 124 Z" fill="${color}" fill-opacity="0.22" stroke="${color}" stroke-width="2.5"/>`;
      default:
        return `<polygon points="160,34 216,74 196,158 124,158 104,74" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2.5"/>`;
    }
  }

  function makeFallbackSvgDataUri(item) {
    const color = qualityColor(item.quality);
    const shape = categorySvgShape(item.category, color);
    const label = (item.category || "APPAREL").toUpperCase();
    const sub = (item.appearance_name && item.appearance_name !== "default" ? item.appearance_name : item.source_mod || "").slice(0, 28);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200" viewBox="0 0 320 200">
      <rect width="320" height="200" fill="#090b12"/>
      <rect x="6" y="6" width="308" height="188" fill="none" stroke="${color}" stroke-opacity="0.35" stroke-width="1.5"/>
      ${shape}
      <text x="160" y="186" fill="${color}" font-family="monospace" font-size="11" text-anchor="middle">${label}${sub ? " · " + sub.replace(/[<>&"]/g, "") : ""}</text>
    </svg>`;
    return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
  }

  function safeAssetUrl(prefix, relPath) {
    if (!relPath) return "";
    const encoded = relPath
      .split("/")
      .map((seg) => encodeURIComponent(seg))
      .join("/");
    return `${prefix}/${encoded}`;
  }

  function formatBytes(bytes) {
    if (!bytes) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(2)} MB`;
  }

  async function loadItems() {
    const params = new URLSearchParams({
      q: state.query,
      status: state.status,
      category: state.category,
      atelier_store: state.atelier_store,
      source_mod: state.source_mod,
      body_type: state.body_type,
      quality: state.quality,
      tag: state.tag,
      sort_by: state.sort_by,
      sort_dir: state.sort_dir,
      page: String(state.page),
      page_size: String(state.page_size),
    });

    const data = await api(`/api/items?${params.toString()}`);
    state.currentItems = data.items;

    document.getElementById("statActive").textContent = data.summary.total_active;
    document.getElementById("statRejected").textContent = data.summary.total_rejected;
    document.getElementById("statQuarantined").textContent = data.summary.total_quarantined;

    populateSelect(document.getElementById("filterCategory"), data.facets.categories, "All Categories");
    populateSelect(document.getElementById("filterStore"), data.facets.atelier_stores, "All Stores");
    populateSelect(document.getElementById("filterMod"), data.facets.source_mods, "All Mods");
    populateSelect(document.getElementById("filterBody"), data.facets.body_types, "All Bodies");
    populateSelect(document.getElementById("filterQuality"), data.facets.qualities, "All Qualities");
    renderTags(data.facets.tags);

    const totalPages = Math.max(1, Math.ceil(data.total_filtered / state.page_size));
    document.getElementById("resultInfo").textContent = `${data.total_filtered} items`;
    document.getElementById("pageInfo").textContent = `${data.page} / ${totalPages}`;
    document.getElementById("prevPage").disabled = data.page <= 1;
    document.getElementById("nextPage").disabled = data.page >= totalPages;

    renderGrid(data.items, data.scanning);
    updateBatchButtons();

    if (data.scanning) {
      clearTimeout(loadItems._pollTimer);
      loadItems._pollTimer = setTimeout(loadItems, 1500);
    }
  }

  function renderGrid(items, isScanning = false) {
    const grid = document.getElementById("itemsGrid");
    grid.innerHTML = "";
    if (!items.length) {
      grid.innerHTML = isScanning
        ? `<div class="hint">Scanning your Cyberpunk 2077 mod folders (this takes a few seconds for large mod lists)...</div>`
        : `<div class="hint">No clothing items match the current filters. Click "Load 120 Mock Mods" or configure your Mods Directory in Paths.</div>`;
      return;
    }

    for (const item of items) {
      const card = document.createElement("div");
      card.className = `card ${item.status === "rejected" ? "rejected" : ""}`;

      const thumbUrl = item.preview_image
        ? safeAssetUrl("/mod-assets", item.preview_image)
        : makeFallbackSvgDataUri(item);
      const thumbHtml = `<img id="thumb-${encodeURIComponent(item.id)}" src="${thumbUrl}" alt="${item.name}" loading="lazy" />`;

      card.innerHTML = `
        <div class="card-thumb">
          <input type="checkbox" class="card-check" ${state.selectedIds.has(item.id) ? "checked" : ""} />
          <span class="quality-badge">${item.quality}</span>
          ${thumbHtml}
        </div>
        <div class="card-body">
          <div class="card-title">${item.name}</div>
          <div class="card-sub">${item.category} · ${item.body_type} · €\$${item.price}</div>
          <div class="card-sub">${item.atelier_store}</div>
          <div class="card-tags">${(item.tags || []).slice(0, 3).map((t) => `<span>${t}</span>`).join("")}</div>
          <div class="card-actions">
            <button class="btn btn-accent btn-sm btn-inspect">Inspect / 3D</button>
            <button class="btn btn-sm ${item.status === "rejected" ? "btn-secondary" : "btn-danger"} btn-toggle-reject">
              ${item.status === "rejected" ? "Unreject" : "Reject"}
            </button>
          </div>
        </div>
      `;

      const cb = card.querySelector(".card-check");
      cb.onclick = (e) => {
        e.stopPropagation();
        if (cb.checked) state.selectedIds.add(item.id);
        else state.selectedIds.delete(item.id);
        updateBatchButtons();
      };

      card.querySelector(".card-thumb").onclick = () => openInspector(item);
      card.querySelector(".btn-inspect").onclick = () => openInspector(item);
      card.querySelector(".btn-toggle-reject").onclick = async () => {
        const endpoint = item.status === "rejected" ? "/api/unreject" : "/api/reject";
        await api(endpoint, { method: "POST", body: JSON.stringify({ item_ids: [item.id] }) });
        showToast(item.status === "rejected" ? `Restored ${item.name}` : `Marked ${item.name} as rejected`);
        loadItems();
      };

      grid.appendChild(card);
    }

    const currentSlider = document.getElementById("tileSizeSlider");
    if (currentSlider) applyTileSize(currentSlider.value);
    autoLoadPagePreviews(items);
  }

  let previewGen = 0;
  async function autoLoadPagePreviews(items) {
    const gen = ++previewGen;
    const queue = items.filter((it) => !it.preview_image);
    if (!queue.length) return;

    // Group items on the current page by source_mod so shared archives are only extracted once
    const modGroups = new Map();
    for (const item of queue) {
      const key = item.source_mod || item.id;
      if (!modGroups.has(key)) modGroups.set(key, []);
      modGroups.get(key).push(item);
    }

    for (const [, groupItems] of modGroups.entries()) {
      if (gen !== previewGen) return;
      // Yield immediately if Inspector modal is open so 3D inspection gets 100% priority
      while (!document.getElementById("inspectorModal").classList.contains("hidden")) {
        await new Promise((r) => setTimeout(r, 250));
        if (gen !== previewGen) return;
      }
      try {
        const rep = groupItems[0];
        const res = await api("/api/extract-preview", {
          method: "POST",
          body: JSON.stringify({ item_id: rep.id }),
        });
        if (gen !== previewGen) return;
        const texUrl = res.texture || res.image || null;
        if (res.mesh) {
          for (const it of groupItems) {
            it._cachedMeshUrl = res.mesh;
            it._cachedTexUrl = texUrl;
          }
        }
        // Prefer Textured 3D Render snapshot as the primary tile image when a 3D mesh exists!
        if (res.mesh && window.renderGlbThumbnailDataUrl) {
          const snapUrl = await window.renderGlbThumbnailDataUrl(res.mesh, qualityColor(rep.quality), texUrl);
          if (gen !== previewGen) return;
          for (const it of groupItems) {
            it._cachedImgUrl = snapUrl;
            const img = document.getElementById(`thumb-${encodeURIComponent(it.id)}`);
            if (img) img.src = snapUrl;
          }
        } else if (res.image) {
          for (const it of groupItems) {
            it._cachedImgUrl = res.image;
            const img = document.getElementById(`thumb-${encodeURIComponent(it.id)}`);
            if (img) img.src = res.image;
          }
        }
      } catch {
        // Keep SVG fallback if archive has neither icon nor mesh
      }
    }
  }

  function updateBatchButtons() {
    const count = state.selectedIds.size;
    document.getElementById("selectedCount").textContent = `${count} selected`;
    document.getElementById("btnBatchReject").disabled = count === 0;
    document.getElementById("btnBatchUnreject").disabled = count === 0;
    document.getElementById("btnBatchCet").disabled = count === 0;
  }

  async function openInspector(item) {
    state.inspectedItem = item;
    document.getElementById("inspTitle").textContent = item.name;

    const imgEl = document.getElementById("inspImg");
    const existingThumb = document.getElementById(`thumb-${encodeURIComponent(item.id)}`);
    imgEl.src = item.preview_image
      ? safeAssetUrl("/mod-assets", item.preview_image)
      : (existingThumb ? existingThumb.src : makeFallbackSvgDataUri(item));

    const metaGrid = document.getElementById("inspMetaGrid");
    const rows = [
      ["TweakDB ID", item.tweak_id],
      ["Category", item.category],
      ["Atelier Store", item.atelier_store],
      ["Source Mod", item.source_mod],
      ["Body Type", item.body_type],
      ["Quality", item.quality],
      ["File Size", formatBytes(item.file_size)],
      ["Files", (item.associated_files || []).join(", ")],
    ];
    metaGrid.innerHTML = rows
      .map(([k, v]) => `<div class="meta-key">${k}</div><div class="meta-val">${v}</div>`)
      .join("");

    document.getElementById("inspCetInput").value = `Game.AddToInventory("${item.tweak_id}", 1)`;
    const rejBtn = document.getElementById("inspRejectBtn");
    rejBtn.textContent = item.status === "rejected" ? "Unreject Item" : "Mark Rejected";

    document.getElementById("inspectorModal").classList.remove("hidden");

    const meshSelect = document.getElementById("meshSelect");
    const texSelect = document.getElementById("texSelect");
    meshSelect.innerHTML = `<option value="">Default 3D Mesh</option>`;
    texSelect.innerHTML = `<option value="">Studio Weave (No Texture)</option>`;

    if (item._cachedMeshUrl) {
      try {
        await viewer3d.loadGlbUrl(item._cachedMeshUrl, item.name, qualityColor(item.quality), item._cachedTexUrl || null);
      } catch {
        // Fall through to full extract-item if cached URL failed
      }
    }
    if (item.mesh_file) {
      try {
        const url = safeAssetUrl("/mod-assets", item.mesh_file);
        if (item.mesh_file.toLowerCase().endsWith(".glb")) {
          await viewer3d.loadGlbUrl(url, item.name, qualityColor(item.quality));
        } else {
          const res = await fetch(url);
          if (res.ok) {
            const objText = await res.text();
            viewer3d.loadObjText(objText, item.name, qualityColor(item.quality));
          } else {
            viewer3d.loadProceduralFallback(item.category, item.name);
          }
        }
      } catch {
        viewer3d.loadProceduralFallback(item.category, item.name);
      }
    } else {
      if (!item._cachedMeshUrl) {
        viewer3d.loadProceduralFallback(item.category, item.name);
      }
      // Extract 3D mesh & surface textures via WolvenKitDaemon
      try {
        if (!item._cachedMeshUrl) showToast("Loading textured 3D mesh...");
        const ext = await api("/api/extract-item", {
          method: "POST",
          body: JSON.stringify({ item_id: item.id }),
        });
        if (state.inspectedItem && state.inspectedItem.id === item.id) {
          const allTex = [...(ext.textures || []), ...(ext.images || [])];
          const uniqueTex = Array.from(new Set(allTex));
          const primaryTex = uniqueTex[0] || null;

          if (uniqueTex.length) {
            imgEl.src = uniqueTex[0];
            uniqueTex.forEach((tUrl, idx) => {
              const opt = document.createElement("option");
              opt.value = tUrl;
              opt.textContent = `Texture ${idx + 1}: ${decodeURIComponent(tUrl.split("/").pop())}`;
              if (idx === 0) opt.selected = true;
              texSelect.appendChild(opt);
            });
          }

          if (ext.meshes && ext.meshes.length) {
            ext.meshes.forEach((mUrl, idx) => {
              const opt = document.createElement("option");
              opt.value = mUrl;
              opt.textContent = `Mesh ${idx + 1}: ${decodeURIComponent(mUrl.split("/").pop())}`;
              if (idx === 0) opt.selected = true;
              meshSelect.appendChild(opt);
            });

            const glbUrl = ext.meshes.find((m) => m.toLowerCase().endsWith(".glb")) || ext.meshes[0];
            if (glbUrl.toLowerCase().endsWith(".glb")) {
              if (!item._cachedMeshUrl) {
                await viewer3d.loadGlbUrl(glbUrl, `${item.name} (${ext.archive})`, qualityColor(item.quality), primaryTex);
              }
              if (window.renderGlbThumbnailDataUrl) {
                const snapUrl = await window.renderGlbThumbnailDataUrl(glbUrl, qualityColor(item.quality), primaryTex);
                const cardImg = document.getElementById(`thumb-${encodeURIComponent(item.id)}`);
                if (cardImg) cardImg.src = snapUrl;
              }
            }
          } else {
            showToast(ext.message || `No 3D .mesh found in ${ext.archive || "archive"}`);
          }

          meshSelect.onchange = async () => {
            if (meshSelect.value) {
              await viewer3d.loadGlbUrl(meshSelect.value, item.name, qualityColor(item.quality), texSelect.value || null);
            }
          };
          texSelect.onchange = async () => {
            if (texSelect.value) {
              await viewer3d.loadTextureUrl(texSelect.value);
              imgEl.src = texSelect.value;
            } else {
              viewer3d.clearTexture();
            }
          };
        }
      } catch {
        // Keep procedural fallback
      }
    }
  }

  async function openQuarantineModal() {
    const [qData, rejData] = await Promise.all([
      api("/api/quarantine"),
      api("/api/items?status=rejected&page_size=500"),
    ]);

    document.getElementById("pendingRejectCount").textContent = rejData.items.length;
    const pendingList = document.getElementById("pendingRejectList");
    pendingList.innerHTML = rejData.items.length
      ? rejData.items
          .map(
            (it) => `<div class="q-row">
              <div><strong>${it.name}</strong> <span class="hint">(${it.source_mod})</span></div>
              <button class="btn btn-sm btn-secondary" data-unreject="${it.id}">Undo</button>
            </div>`
          )
          .join("")
      : `<div class="hint">No pending rejected items.</div>`;

    pendingList.querySelectorAll("[data-unreject]").forEach((btn) => {
      btn.onclick = async () => {
        await api("/api/unreject", { method: "POST", body: JSON.stringify({ item_ids: [btn.dataset.unreject] }) });
        openQuarantineModal();
        loadItems();
      };
    });

    const qList = document.getElementById("quarantinedList");
    qList.innerHTML = qData.records.length
      ? qData.records
          .map(
            (rec) => `<div class="q-row">
              <div>
                <strong>${rec.source_mod}</strong> (${rec.item_names.length} items)
                <div class="hint">${rec.files.join(", ")}</div>
              </div>
              <div class="row-gap">
                <button class="btn btn-sm btn-accent" data-restore="${rec.record_id}">Restore</button>
                <button class="btn btn-sm btn-danger" data-delete="${rec.record_id}">Delete</button>
              </div>
            </div>`
          )
          .join("")
      : `<div class="hint">Quarantine folder is empty.</div>`;

    qList.querySelectorAll("[data-restore]").forEach((btn) => {
      btn.onclick = async () => {
        await api("/api/quarantine/restore", { method: "POST", body: JSON.stringify({ record_id: btn.dataset.restore }) });
        showToast("Restored mod files back to game folder");
        openQuarantineModal();
        loadItems();
      };
    });

    qList.querySelectorAll("[data-delete]").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm("Permanently delete these quarantined mod files from disk?")) return;
        await api("/api/quarantine/delete", {
          method: "POST",
          body: JSON.stringify({ record_id: btn.dataset.delete, confirm: true }),
        });
        showToast("Permanently deleted quarantined files");
        openQuarantineModal();
        loadItems();
      };
    });

    document.getElementById("quarantineModal").classList.remove("hidden");
  }

  // Event bindings
  document.getElementById("searchInput").addEventListener("input", (e) => {
    state.query = e.target.value;
    state.page = 1;
    loadItems();
  });

  document.querySelectorAll("#statusTabs button").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll("#statusTabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.status = btn.dataset.status;
      state.page = 1;
      loadItems();
    };
  });

  for (const [id, key] of [
    ["filterCategory", "category"],
    ["filterStore", "atelier_store"],
    ["filterMod", "source_mod"],
    ["filterBody", "body_type"],
    ["filterQuality", "quality"],
    ["sortBy", "sort_by"],
  ]) {
    document.getElementById(id).onchange = (e) => {
      state[key] = e.target.value;
      state.page = 1;
      loadItems();
    };
  }

  document.getElementById("sortDirBtn").onclick = (e) => {
    state.sort_dir = state.sort_dir === "asc" ? "desc" : "asc";
    e.target.textContent = state.sort_dir.toUpperCase();
    loadItems();
  };

  document.getElementById("btnClearFilters").onclick = () => {
    state.query = "";
    state.category = "";
    state.atelier_store = "";
    state.source_mod = "";
    state.body_type = "";
    state.quality = "";
    state.tag = "";
    state.page = 1;
    document.getElementById("searchInput").value = "";
    loadItems();
  };

  document.getElementById("selectAllPage").onchange = (e) => {
    for (const it of state.currentItems) {
      if (e.target.checked) state.selectedIds.add(it.id);
      else state.selectedIds.delete(it.id);
    }
    renderGrid(state.currentItems);
    updateBatchButtons();
  };

  document.getElementById("btnBatchReject").onclick = async () => {
    const ids = Array.from(state.selectedIds);
    await api("/api/reject", { method: "POST", body: JSON.stringify({ item_ids: ids }) });
    state.selectedIds.clear();
    showToast(`Marked ${ids.length} items as rejected`);
    loadItems();
  };

  document.getElementById("btnBatchUnreject").onclick = async () => {
    const ids = Array.from(state.selectedIds);
    await api("/api/unreject", { method: "POST", body: JSON.stringify({ item_ids: ids }) });
    state.selectedIds.clear();
    showToast(`Restored ${ids.length} items`);
    loadItems();
  };

  document.getElementById("btnBatchCet").onclick = async () => {
    const ids = new Set(state.selectedIds);
    const tweakIds = state.currentItems.filter((i) => ids.has(i.id)).map((i) => i.tweak_id);
    const res = await api("/api/cet-commands", { method: "POST", body: JSON.stringify({ tweak_ids: tweakIds }) });
    await navigator.clipboard.writeText(res.commands).catch(() => {});
    showToast(`Copied ${tweakIds.length} CET commands to clipboard`);
  };

  document.getElementById("prevPage").onclick = () => {
    if (state.page > 1) { state.page--; loadItems(); }
  };
  document.getElementById("nextPage").onclick = () => {
    state.page++;
    loadItems();
  };

  document.getElementById("btnGenerateMock").onclick = async () => {
    await api("/api/generate-mock", { method: "POST", body: JSON.stringify({ count: 120 }) });
    showToast("Generated 120 mock Cyberpunk 2077 clothing mods");
    loadItems();
  };

  document.getElementById("btnRescan").onclick = async () => {
    await api("/api/rescan", { method: "POST", body: "{}" });
    showToast("Rescanned mod directory");
    loadItems();
  };

  document.getElementById("btnQuarantineModal").onclick = openQuarantineModal;
  document.getElementById("btnExecuteQuarantine").onclick = async () => {
    const res = await api("/api/quarantine/execute", { method: "POST", body: "{}" });
    showToast(`Moved ${res.moved_files.length} mod files to quarantine`);
    openQuarantineModal();
    loadItems();
  };

  let browseTargetInputId = null;
  let browseCurrent = "";
  let browseParent = "";

  async function loadBrowse(dirPath) {
    const res = await api(`/api/browse?path=${encodeURIComponent(dirPath || "")}`);
    browseCurrent = res.current;
    browseParent = res.parent;
    document.getElementById("browseCurrentPath").textContent = browseCurrent || "Drives";
    const list = document.getElementById("browseList");
    list.innerHTML = res.dirs.length
      ? res.dirs
          .map(
            (d) => `<div class="q-row">
              <span>${d.name}</span>
              <button class="btn btn-sm btn-secondary" data-open-dir="${d.path}">Open</button>
            </div>`
          )
          .join("")
      : `<div class="hint">No subdirectories.</div>`;
    list.querySelectorAll("[data-open-dir]").forEach((btn) => {
      btn.onclick = () => loadBrowse(btn.dataset.openDir);
    });
  }

  document.querySelectorAll("[data-browse]").forEach((btn) => {
    btn.onclick = () => {
      browseTargetInputId = btn.dataset.browse;
      const startVal = document.getElementById(browseTargetInputId).value;
      document.getElementById("folderBrowser").classList.remove("hidden");
      loadBrowse(startVal).catch(() => loadBrowse(""));
    };
  });

  document.getElementById("btnBrowseUp").onclick = () => loadBrowse(browseParent);
  document.getElementById("btnBrowseSelect").onclick = () => {
    if (browseTargetInputId && browseCurrent) {
      document.getElementById(browseTargetInputId).value = browseCurrent;
    }
    document.getElementById("folderBrowser").classList.add("hidden");
  };

  document.getElementById("btnPaths").onclick = async () => {
    const [cfg, detected] = await Promise.all([
      api("/api/config"),
      api("/api/detect-installs"),
    ]);
    document.getElementById("cfgModDir").value = cfg.mod_dir;
    document.getElementById("cfgQuarantineDir").value = cfg.quarantine_dir;
    document.getElementById("cfgSaveDir").value = cfg.save_dir;
    document.getElementById("folderBrowser").classList.add("hidden");

    const d = detected.diagnostics;
    document.getElementById("diagBanner").textContent =
      `Current scan: ${d.archive_count} .archive files, ${d.tweak_count} .yaml/.tweak files, ${d.reds_count} .reds atelier scripts.`;

    const instEl = document.getElementById("detectedInstalls");
    if (detected.installations && detected.installations.length) {
      instEl.innerHTML = detected.installations
        .map(
          (inst) => `<div class="q-row">
            <div><strong>Detected Game:</strong> ${inst.path}</div>
            <button class="btn btn-sm btn-accent" data-use-install="${inst.path}">Use Game Root</button>
          </div>`
        )
        .join("");
      instEl.querySelectorAll("[data-use-install]").forEach((btn) => {
        btn.onclick = () => {
          document.getElementById("cfgModDir").value = btn.dataset.useInstall;
          showToast("Selected Cyberpunk 2077 game root");
        };
      });
    } else {
      instEl.innerHTML = `<div class="hint">No default Steam/GOG/Epic Cyberpunk 2077 install auto-detected. Use Browse... below to select your game or mod folder.</div>`;
    }

    document.getElementById("pathsModal").classList.remove("hidden");
  };

  document.getElementById("btnSavePaths").onclick = async () => {
    await api("/api/config", {
      method: "POST",
      body: JSON.stringify({
        mod_dir: document.getElementById("cfgModDir").value,
        quarantine_dir: document.getElementById("cfgQuarantineDir").value,
        save_dir: document.getElementById("cfgSaveDir").value,
      }),
    });
    document.getElementById("pathsModal").classList.add("hidden");
    showToast("Updated paths and rescanned");
    loadItems();
  };

  document.getElementById("btnSaves").onclick = async () => {
    const data = await api("/api/saves");
    document.getElementById("saveDirHint").textContent = `Scanning: ${data.save_dir}`;
    const list = document.getElementById("savesList");
    list.innerHTML = data.saves.length
      ? data.saves
          .map(
            (s) => `<div class="q-row">
              <div>
                <strong>${s.save_name}</strong> — ${s.life_path} · ${s.body_gender} · Lvl ${s.level} (SC ${s.street_cred})
                <div class="hint">${s.play_time_hours}h played · ${s.timestamp}</div>
              </div>
              <button class="btn btn-sm btn-accent" data-load-save="${s.save_name}">Load V</button>
            </div>`
          )
          .join("")
      : `<div class="hint">No Cyberpunk 2077 saves found in ${data.save_dir}.</div>`;

    list.querySelectorAll("[data-load-save]").forEach((btn) => {
      btn.onclick = () => {
        const save = data.saves.find((s) => s.save_name === btn.dataset.loadSave);
        state.activeSave = save;
        document.getElementById("vBannerText").textContent = `${save.life_path} V (${save.body_gender}, Level ${save.level})`;
        document.getElementById("vProfileBanner").classList.remove("hidden");
        document.getElementById("savesModal").classList.add("hidden");
        showToast(`Loaded V Save: ${save.save_name}`);
      };
    });
    document.getElementById("savesModal").classList.remove("hidden");
  };

  document.getElementById("btnFilterToV").onclick = () => {
    if (!state.activeSave) return;
    state.body_type = state.activeSave.body_gender;
    document.getElementById("filterBody").value = state.body_type;
    loadItems();
  };

  // Tile scaling (S / M / L / XL + continuous slider, persisted in localStorage)
  function applyTileSize(px) {
    const width = Math.max(140, Math.min(460, parseInt(px, 10) || 240));
    const thumbHeight = Math.round(width * 0.82);
    document.documentElement.style.setProperty("--tile-width", `${width}px`);
    document.documentElement.style.setProperty("--tile-thumb-height", `${thumbHeight}px`);
    const grid = document.getElementById("itemsGrid");
    if (grid) {
      grid.style.gridTemplateColumns = `repeat(auto-fill, minmax(${width}px, 1fr))`;
      grid.querySelectorAll(".card-thumb").forEach((el) => {
        el.style.height = `${thumbHeight}px`;
      });
    }
    const slider = document.getElementById("tileSizeSlider");
    if (slider && parseInt(slider.value, 10) !== width) slider.value = String(width);
    document.querySelectorAll("[data-tile-size]").forEach((btn) => {
      btn.classList.toggle("active", parseInt(btn.dataset.tileSize, 10) === width);
    });
    try { localStorage.setItem("2077view_tile_size", String(width)); } catch {}
  }

  const savedTileSize = (() => {
    try { return localStorage.getItem("2077view_tile_size"); } catch { return null; }
  })();
  applyTileSize(savedTileSize || 240);

  document.getElementById("tileSizeSlider").addEventListener("input", (e) => {
    applyTileSize(e.target.value);
  });
  document.querySelectorAll("[data-tile-size]").forEach((btn) => {
    btn.onclick = () => applyTileSize(btn.dataset.tileSize);
  });

  // Inspector controls
  document.getElementById("tab3dBtn").onclick = () => {
    document.getElementById("tab3dBtn").classList.add("active");
    document.getElementById("tab2dBtn").classList.remove("active");
    document.getElementById("viewer3dWrap").classList.remove("hidden");
    document.getElementById("viewer2dWrap").classList.add("hidden");
  };
  document.getElementById("tab2dBtn").onclick = () => {
    document.getElementById("tab2dBtn").classList.add("active");
    document.getElementById("tab3dBtn").classList.remove("active");
    document.getElementById("viewer2dWrap").classList.remove("hidden");
    document.getElementById("viewer3dWrap").classList.add("hidden");
  };
  document.getElementById("btnWireframe").onclick = (e) => {
    const wf = viewer3d.toggleWireframe();
    e.target.textContent = `Wireframe: ${wf ? "ON" : "OFF"}`;
  };
  document.getElementById("btnResetCam").onclick = () => viewer3d.resetCamera();
  document.getElementById("btnCopyCet").onclick = async () => {
    const val = document.getElementById("inspCetInput").value;
    await navigator.clipboard.writeText(val).catch(() => {});
    showToast("Copied CET command");
  };
  document.getElementById("inspRejectBtn").onclick = async () => {
    const it = state.inspectedItem;
    if (!it) return;
    const endpoint = it.status === "rejected" ? "/api/unreject" : "/api/reject";
    await api(endpoint, { method: "POST", body: JSON.stringify({ item_ids: [it.id] }) });
    document.getElementById("inspectorModal").classList.add("hidden");
    loadItems();
  };

  document.querySelectorAll("[data-close]").forEach((btn) => {
    btn.onclick = () => document.getElementById(btn.dataset.close).classList.add("hidden");
  });

  loadItems();
})();

