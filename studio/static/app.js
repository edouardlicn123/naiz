/* Naiz 剧本工坊 — 前端逻辑（原生 JS，无框架） */
(function () {
  "use strict";

  var S = {
    project: null,
    scenes: [],
    cfgs: [],
    current: null,        // 当前打开的文件名（.nb 或配置文件）
    currentKind: "scene", // 'scene' | 'cfg'
    meta: null,
    dirty: false,
    assets: null,
    pollTimer: null,
    serialTimer: null,
    serialFrom: 0,
    cm: null,             // CodeMirror 实例（可用时）
  };

  var $ = function (id) { return document.getElementById(id); };

  // ── 基础请求 ──────────────────────────────────────────
  function api(method, path, body) {
    return fetch(path, {
      method: method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then(function (r) {
      return r.json().then(function (j) { j._code = r.status; return j; });
    });
  }

  var toastTimer = null;
  function toast(msg, isErr) {
    var el = $("toast");
    el.textContent = msg;
    el.className = isErr ? "err" : "";
    el.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.add("hidden"); }, 2600);
  }

  // 服务器返回的中文错误 → 当前语言（识别不到则原样显示）
  function trErr(msg) {
    msg = String(msg || "");
    if (msg.indexOf("已在运行") >= 0) return t("job_dup");
    if (msg.indexOf("文件不存在") >= 0) return t("not_found");
    if (msg.indexOf("forbidden") >= 0) return t("forbidden");
    return msg;
  }

  // ── 编辑器 ────────────────────────────────────────────
  function initEditor(commands) {
    if (!window.CodeMirror) {
      // 未成功加载 CodeMirror 时退化为纯文本编辑
      $("editor-host").classList.add("hidden");
      $("editor-fallback").classList.remove("hidden");
      $("editor-fallback").addEventListener("input", function () { markDirty(true); });
      var ta = $("editor-fallback");
      function taCursor() {
        var lines = ta.value.slice(0, ta.selectionStart).split("\n");
        setCursor({ line: lines.length - 1, ch: lines[lines.length - 1].length });
      }
      ta.addEventListener("keyup", taCursor);
      ta.addEventListener("click", taCursor);
      ta.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); saveScene(); }
      });
      return;
    }
    window.naizDefineNBMode(commands);
    S.cm = CodeMirror($("editor-host"), {
      mode: "naiznb",
      theme: "naiz",
      lineNumbers: true,
      styleActiveLine: true,
      matchBrackets: true,
      indentUnit: 2,
      extraKeys: {
        "Ctrl-S": function () { saveScene(); },
        "Cmd-S": function () { saveScene(); },
        "Ctrl-Space": "autocomplete",
      },
    });
    S.cm.on("change", function () { markDirty(true); });
    S.cm.on("cursorActivity", function () { setCursor(S.cm.getCursor(false)); });
  }

  function editorGet() {
    return S.cm ? S.cm.getValue() : $("editor-fallback").value;
  }
  function editorSet(text) {
    if (S.cm) S.cm.setValue(text);
    else $("editor-fallback").value = text;
    markDirty(false);
  }

  function markDirty(v) {
    S.dirty = v;
    $("dirty-mark").classList.toggle("hidden", !v);
    var sh = $("save-hint");
    if (v) { sh.textContent = t("dirty"); sh.className = "warn"; }
  }

  // 状态栏辅助
  function setCursor(pos) {
    $("sb-cursor").textContent = "Ln " + (pos.line + 1) + ", Col " + (pos.ch + 1);
  }
  function setSbJob(cls, text) {
    var el = $("sb-job");
    el.className = cls || "";
    el.textContent = text;
  }

  // ── 补全 ──────────────────────────────────────────────
  function hintFor(cm) {
    var cur = cm.getCursor(), line = cm.getLine(cur.line);
    var before = line.slice(0, cur.ch);
    var word = /[A-Za-z0-9_]*$/.exec(before)[0];
    var mCmd = /^([A-Za-z_][A-Za-z0-9_]*)\(/.exec(before.slice(0, before.length - word.length));
    var list = [];
    var meta = S.meta || { assets: {} };
    if (mCmd && before.indexOf("{", mCmd.index) === -1 && before.indexOf(")", mCmd.index + mCmd[1].length + 1) >= 0) {
      // 在 { } 载荷内：按命令给资产 key
      var cmd = mCmd[1], pool = [];
      var a = meta.assets || {};
      if (cmd === "bgm") pool = a.bgm || [];
      else if (cmd === "sound") pool = a.snd || [];
      else if (cmd === "voice") pool = a.vc || [];
      else if (cmd === "bg" || cmd === "cg") pool = a.img || [];
      else if (cmd === "char") pool = meta.chars || [];
      else if (cmd === "question") pool = meta.variables || [];
      list = pool.slice();
    } else if (!mCmd) {
      // 行首：命令名补全
      list = (meta.commands || []).slice();
    }
    list = list.filter(function (x) { return x.indexOf(word) === 0 && x !== word; });
    return { list: list, from: CodeMirror.Pos(cur.line, cur.ch - word.length), to: cur };
  }

  // ── 项目 / 场景 ───────────────────────────────────────
  function loadProjects() {
    return api("GET", "/api/projects").then(function (j) {
      var sel = $("project-select");
      sel.innerHTML = "";
      (j.projects || []).forEach(function (p) {
        var o = document.createElement("option");
        o.value = p; o.textContent = p;
        sel.appendChild(o);
      });
      // 默认优先 demo-a2，其次第一个
      var def = j.projects.indexOf("demo-a2") >= 0 ? "demo-a2" : (j.projects[0] || "");
      sel.value = def;
      S.project = def;
    });
  }

  function loadProject() {
    if (!S.project) return;
    return Promise.all([
      api("GET", "/api/scenes/" + S.project),
      api("GET", "/api/meta/" + S.project),
      api("GET", "/api/assets/" + S.project),
    ]).then(function (rs) {
      S.scenes = rs[0].scenes || [];
      S.cfgs = rs[0].configs || [];
      S.meta = rs[1];
      S.assets = rs[2];
      renderLists();
      if (!S.cm && !window.CodeMirror) { /* textarea 模式无需重建 */ }
      else if (!S.cm) initEditor(S.meta.commands);
      refreshLamps();
      var first = S.scenes.length ? S.scenes[0].name : null;
      if (!S.current || !(S.currentKind === "scene"
            ? S.scenes.some(function (s) { return s.name === S.current; })
            : S.cfgs.some(function (c) { return c.name === S.current && c.exists; }))) {
        if (first) openPath("scene", first);
      }
    });
  }

  function renderLists() {
    $("scene-count").textContent = S.scenes.length;
    $("cfg-count").textContent =
      S.cfgs.filter(function (c) { return c.exists; }).length + "/" + S.cfgs.length;
    var ul = $("scene-list");
    ul.innerHTML = "";
    S.scenes.forEach(function (s) {
      var li = document.createElement("li");
      li.textContent = s.name;
      li.title = s.size + " B";
      if (S.currentKind === "scene" && s.name === S.current) li.className = "active";
      li.addEventListener("click", function () { openPath("scene", s.name); });
      ul.appendChild(li);
    });
    var uc = $("cfg-list");
    uc.innerHTML = "";
    S.cfgs.forEach(function (c) {
      var li = document.createElement("li");
      li.textContent = c.name;
      li.title = c.exists ? ("projects/" + S.project + "/" + c.name + " (" + c.size + " B)")
                          : t("not_found");
      if (!c.exists) { li.className = "missing"; }
      else {
        if (S.currentKind === "cfg" && c.name === S.current) li.className = "active";
        li.addEventListener("click", function () { openPath("cfg", c.name); });
      }
      uc.appendChild(li);
    });
    // 素材图片
    var ui = $("img-list");
    ui.innerHTML = "";
    var imgs = (S.assets && S.assets.imgs) || [];
    imgs.forEach(function (a) {
      var li = document.createElement("li");
      li.textContent = a.rel.replace(/^png\//, "");
      li.title = a.mag ? "MAG: projects/" + S.project + "/" + a.mag : t("no_mag");
      li.addEventListener("click", function () { openAssetImage(a); });
      ui.appendChild(li);
    });
    $("img-count").textContent = imgs.length;
    // 音频
    var ua = $("audio-list");
    ua.innerHTML = "";
    var audioItems = [];
    if (S.assets) {
      S.assets.bgm.forEach(function (n) { audioItems.push({ kind: "bgm", name: n, label: t("label_bgm") + " · " + n }); });
      S.assets.se.forEach(function (n) { audioItems.push({ kind: "se", name: n, label: t("label_se") + " · " + n }); });
      S.assets.voice.forEach(function (n) { audioItems.push({ kind: "voice", name: n, label: t("label_voice") + " · " + n }); });
    }
    audioItems.forEach(function (it) {
      var li = document.createElement("li");
      li.textContent = it.label;
      li.title = t("listen");
      li.addEventListener("click", function () { openAssetAudio(it); });
      ua.appendChild(li);
    });
    $("audio-count").textContent = audioItems.length;
    // 动画
    api("GET", "/api/anims/" + S.project).then(function (j) {
      var un = $("anim-list");
      un.innerHTML = "";
      var anims = j.anims || [];
      $("anim-count").textContent = anims.length;
      anims.forEach(function (a) {
        var li = document.createElement("li");
        li.textContent = a.name;
        li.title = "projects/" + S.project + "/ani/" + a.name;
        li.addEventListener("click", function () {
          un.querySelectorAll("li").forEach(function (x) { x.classList.remove("active"); });
          li.classList.add("active");
          openAnim(a);
        });
        un.appendChild(li);
      });
    });
  }

  function openAssetImage(a) {
    switchTab("media");
    $("media-cap").textContent = "assets/" + S.project + "/" + a.rel +
      (a.mag ? "　→　projects/" + S.project + "/" + a.mag : "");
    var img = $("media-img");
    img.src = "/api/asset/img/" + S.project + "/" + encodeURIComponent(a.rel);
    img.classList.remove("hidden");
    var mw = $("media-mag-wrap");
    if (a.mag) {
      $("media-mag").src = "/api/asset/mag/" + S.project + "/" + a.mag;
      mw.classList.remove("hidden");
    } else {
      mw.classList.add("hidden");
    }
    var au = $("media-audio");
    au.pause();
    au.classList.add("hidden");
    $("media-canvas").classList.add("hidden");
    $("anim-ctrl").classList.add("hidden");
    S.animPlaying = false;
  }

  function openAssetAudio(it) {
    switchTab("media");
    var sub = it.kind === "bgm" ? "bgm/" : (it.kind === "se" ? "se/" : "voice/");
    $("media-cap").textContent = "assets/" + S.project + "/" + sub + it.name +
      (it.kind === "bgm" ? t("midi_note") : "");
    $("media-img").classList.add("hidden");
    $("media-mag-wrap").classList.add("hidden");
    $("media-canvas").classList.add("hidden");
    $("anim-ctrl").classList.add("hidden");
    S.animPlaying = false;
    var au = $("media-audio");
    au.src = "/api/asset/audio/" + S.project + "/" + it.kind + "/" + encodeURIComponent(it.name);
    au.classList.remove("hidden");
  }

  // ── 动画播放器（canvas，逐帧按 60Hz tick 调度）──
  function openAnim(a) {
    switchTab("media");
    $("media-img").classList.add("hidden");
    $("media-mag-wrap").classList.add("hidden");
    var au = $("media-audio");
    au.pause();
    au.classList.add("hidden");
    api("GET", "/api/anim/meta/" + S.project + "/" + a.name).then(function (mt) {
      if (mt.error) return toast(trErr(mt.error), true);
      S.animMeta = mt;
      var cv = $("media-canvas");
      cv.width = mt.w; cv.height = mt.h;
      cv.classList.remove("hidden");
      $("anim-ctrl").classList.remove("hidden");
      var seek = $("anim-seek");
      seek.max = mt.nframes - 1; seek.value = 0;
      S.animFrames = [];
      for (var i = 0; i < mt.nframes; i++) {
        var im = new Image();
        im.src = "/api/anim/frame/" + S.project + "/" + a.name + "/" + i;
        S.animFrames.push(im);
      }
      var cume = [], acc = 0;
      mt.ticks.forEach(function (tk) { cume.push(acc); acc += tk * (1000 / 60); });
      S.animCume = cume; S.animTotal = Math.max(1, acc);
      $("media-cap").textContent = "ani/" + a.name + " — " +
        (mt.type === 1 ? t("anim_cine") : t("anim_fs")) + " " +
        mt.w + "×" + mt.h + " · " + t("anim_frames", { n: mt.nframes });
      S.animPlaying = true;
      $("anim-play").textContent = "❚❚";
      drawAnim(0);
      S.animT0 = performance.now();
      requestAnimationFrame(animTick);
    });
  }

  function drawAnim(i) {
    S.animIdx = i;
    var cv = $("media-canvas");
    var ctx = cv.getContext("2d");
    var im = S.animFrames[i];
    var paint = function () { if (S.animIdx === i) ctx.drawImage(im, 0, 0); };
    if (im.complete && im.naturalWidth) paint(); else im.onload = paint;
    $("anim-seek").value = i;
    $("anim-frame").textContent = (i + 1) + "/" + S.animMeta.nframes;
  }

  function animTick() {
    if (!S.animPlaying || !S.animCume) return;
    var tms = (performance.now() - S.animT0) % S.animTotal;
    var i = 0;
    while (i + 1 < S.animCume.length && S.animCume[i + 1] <= tms) i++;
    if (i !== S.animIdx) drawAnim(i);
    requestAnimationFrame(animTick);
  }

  function toggleAnim() {
    if (!S.animMeta) return;
    if (S.animPlaying) {
      S.animPlaying = false;
      $("anim-play").textContent = "▶";
    } else {
      S.animPlaying = true;
      $("anim-play").textContent = "❚❚";
      S.animT0 = performance.now() - (S.animCume[S.animIdx] || 0);
      requestAnimationFrame(animTick);
    }
  }

  function openPath(kind, name) {
    var url = kind === "scene"
      ? "/api/scene/" + S.project + "/" + name
      : "/api/cfg/" + S.project + "/" + name;
    api("GET", url).then(function (j) {
      if (j.error) return toast(j.error, true);
      S.current = name;
      S.currentKind = kind;
      $("current-file").textContent = kind === "scene"
        ? "projects/" + S.project + "/scene/" + name
        : (name === "images.map"
            ? "assets/" + S.project + "/" + name
            : "projects/" + S.project + "/" + name);
      if (S.cm) S.cm.setOption("mode", kind === "scene" ? "naiznb" : { name: "null" });
      editorSet(j.content);
      renderLists();
      $("save-hint").textContent = "";
    });
  }

  function saveScene() {
    if (!S.current) return;
    var url = S.currentKind === "scene"
      ? "/api/scene/" + S.project + "/" + S.current
      : "/api/cfg/" + S.project + "/" + S.current;
    api("PUT", url, { content: editorGet() })
      .then(function (j) {
        if (j.error) return toast(t("save_fail", { e: trErr(j.error) }), true);
        markDirty(false);
        $("save-hint").textContent = t("saved_at", { t: new Date().toLocaleTimeString() });
        $("save-hint").className = "";
        if (S.currentKind === "scene") {
          doLint();       // 剧本保存后自动校验
          refreshLamps();
        } else {
          // 配置保存后刷新补全元数据（角色/表情/变量/资产表可能变化）
          api("GET", "/api/meta/" + S.project).then(function (m) {
            S.meta = m;
            toast(t("cfg_saved"));
          });
        }
      });
  }

  // ── 校验 / 构建 / 打包 / 启动测试 ─────────────────────
  function setBtns(disabled) {
    ["btn-lint", "btn-build", "btn-pack", "btn-launch"].forEach(function (id) {
      $(id).disabled = disabled;
    });
  }

  function doLint() {
    if (!S.project) return;
    var badge = document.querySelector('[data-tab="lint"] .badge');
    if (badge) badge.remove();
    api("POST", "/api/lint/" + S.project).then(function (j) {
      if (j.error) return toast(j.error, true);
      $("lint-out").textContent = j.output || "(no output)";
      var b = document.createElement("span");
      b.className = "badge" + (j.code === 0 ? " zero" : "");
      b.textContent = j.code === 0 ? "0" : String(j.code);
      document.querySelector('[data-tab="lint"]').appendChild(b);
      toast(j.code === 0 ? t("lint_ok") : t("lint_err", { n: j.code }), j.code !== 0);
    });
  }

  function runAction(action, doneMsg) {
    if (!S.project) return;
    if (S.dirty) { toast(t("save_first"), true); return; }
    setBtns(true);
    $("lamp-run").classList.add("on");
    setSbJob("busy", t("sb_submit", { a: doneMsg }));
    switchTab("jobs");
    $("job-out").textContent = "…";
    api("POST", "/api/" + action + "/" + S.project).then(function (j) {
      if (j.error) {
        setBtns(false);
        $("lamp-run").classList.remove("on");
        setSbJob("error", t("submit_fail"));
        return toast(trErr(j.error), true);
      }
      pollJob(j.job_id, doneMsg);
    });
  }

  function pollJob(jid, doneMsg) {
    if (S.pollTimer) clearInterval(S.pollTimer);
    S.pollTimer = setInterval(function () {
      api("GET", "/api/jobs/" + jid).then(function (j) {
        var stKey = j.status === "done" ? "st_done" :
                    (j.status === "failed" ? "st_failed" : "st_running");
        $("job-out").textContent = (j.lines || []).join("\n") +
          "\n\n[" + t(stKey) + "]" + (j.code !== null && j.code !== undefined
            ? " " + t("exit_code", { c: j.code }) : "");
        $("job-out").scrollTop = $("job-out").scrollHeight;
        if (j.status !== "running") {
          clearInterval(S.pollTimer); S.pollTimer = null;
          setBtns(false);
          $("lamp-run").classList.remove("on");
          var ok = j.status === "done";
          var now = new Date().toLocaleTimeString();
          setSbJob(ok ? "ok" : "error",
            ok ? t("sb_done", { a: doneMsg, t: now })
               : t("sb_fail", { a: doneMsg, c: j.code, t: now }));
          toast(ok ? t("sb_done", { a: doneMsg, t: "" }).trim()
                   : t("sb_fail", { a: doneMsg, c: j.code, t: "" }).trim(), !ok);
          refreshLamps();
          if (j.kind === "launch") startSerialPoll();
        } else {
          setSbJob("busy", t("sb_running", { a: doneMsg, n: (j.lines || []).length }));
        }
      });
    }, 700);
  }

  // ── 串口日志轮询 ──────────────────────────────────────
  function startSerialPoll() {
    switchTab("serial");
    S.serialFrom = 0;
    $("serial-out").textContent = "";
    if (S.serialTimer) clearInterval(S.serialTimer);
    var misses = 0;
    S.serialTimer = setInterval(function () {
      api("GET", "/api/serial/" + S.project + "?from=" + S.serialFrom).then(function (j) {
        if (j.size > 0 || j.chunk) misses = 0; else misses++;
        if (j.chunk) {
          $("serial-out").textContent += j.chunk;
          S.serialFrom = j.size;
          $("serial-out").scrollTop = $("serial-out").scrollHeight;
        }
        if (misses > 40) { clearInterval(S.serialTimer); S.serialTimer = null; } // 约 40s 无日志则停
      });
    }, 1000);
  }

  // ── 状态灯 ────────────────────────────────────────────
  function refreshLamps() {
    if (!S.project) return;
    api("GET", "/api/status/" + S.project).then(function (j) {
      $("lamp-stale").className = "lamp" + (j.hdi_stale ? " on" : "");
      $("lamp-stale").textContent = j.hdi_stale ? t("lamp_stale") : t("lamp_ready");
      if (!j.hdi_stale) $("lamp-stale").classList.add("warn");
      $("lamp-noeng").className = "lamp" + (!j.engine_exists ? " on" : "");
      api("GET", "/api/jobs").then(function (k) {
        $("lamp-run").classList.toggle("on", (k.jobs || []).length > 0);
      });
    });
  }

  // ── 面板标签 ──────────────────────────────────────────
  function switchTab(name) {
    document.querySelectorAll(".tab").forEach(function (t) {
      t.classList.toggle("active", t.dataset.tab === name);
    });
    document.querySelectorAll(".tab-body").forEach(function (b) {
      b.classList.toggle("active", b.id === "tab-" + name);
    });
  }

  // ── 启动 ──────────────────────────────────────────────
  function init() {
    initLang();
    $("lang-select").addEventListener("change", function () { setLang(this.value); });
    document.addEventListener("langchange", function () {
      renderLists();      // 音频标签等动态文案随语言刷新
      refreshLamps();
    });
    $("btn-guide").addEventListener("click", function () {
      // 中文界面看中文手册，其余语言回退英文版
      window.open("/guidebook/" + (window.currentLang() === "zh" ? "cn/" : "en/"), "_blank");
    });
    $("anim-play").addEventListener("click", toggleAnim);
    $("anim-seek").addEventListener("input", function () {
      if (!S.animMeta) return;
      S.animPlaying = false;
      $("anim-play").textContent = "▶";
      drawAnim(parseInt(this.value, 10) || 0);
    });
    $("project-select").addEventListener("change", function () {
      S.project = this.value; S.current = null; S.currentKind = "scene";
      if (S.cm) S.cm.setValue("");
      loadProject();
    });
    $("btn-lint").addEventListener("click", doLint);
    $("btn-build").addEventListener("click", function () { runAction("build", t("btn_build")); });
    $("btn-pack").addEventListener("click", function () { runAction("pack", t("btn_pack")); });
    $("btn-launch").addEventListener("click", function () { runAction("launch", t("btn_launch").replace(/^\u25B6\s*/, "")); });
    $("btn-save").addEventListener("click", saveScene);
    document.querySelectorAll(".tab").forEach(function (t) {
      t.addEventListener("click", function () { switchTab(t.dataset.tab); });
    });
    // 分组标题折叠
    document.querySelectorAll(".side-title[data-target]").forEach(function (t) {
      t.addEventListener("click", function () {
        var ul = $(t.dataset.target);
        ul.classList.toggle("folded");
        t.classList.toggle("folded", ul.classList.contains("folded"));
      });
    });
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); saveScene(); }
    });

    // CodeMirror 补全注册（initEditor 内已定义模式后再注册）
    if (window.CodeMirror) {
      CodeMirror.registerHelper("hint", "naiz", hintFor);
    }

    loadProjects().then(function () {
      if (S.cm) {
        // 编辑器已就绪：注册补全命令
        S.cm.setOption("extraKeys", Object.assign({}, S.cm.getOption("extraKeys"), {
          "Ctrl-Space": function (cm) { cm.showHint({ hint: hintFor, completeSingle: false }); },
        }));
      }
      return loadProject();
    }).then(function () {
      // 编辑器在 loadProject 里才初始化（需要命令表），这里再挂补全
      if (S.cm) {
        S.cm.setOption("extraKeys", Object.assign({}, S.cm.getOption("extraKeys"), {
          "Ctrl-Space": function (cm) { cm.showHint({ hint: hintFor, completeSingle: false }); },
        }));
      }
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
