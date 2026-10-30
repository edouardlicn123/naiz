/* Naiz 剧本工坊 — 界面多语言（en / zh / ja / ko，默认 en）
 * 静态文案：<element data-i18n="key"> 与 data-i18n-title="key"
 * 动态文案：JS 里 t("key", {n: 1})
 */
(function () {
  "use strict";

  var DICT = {
    en: {
      btn_lint: "Validate", btn_build: "Compile Data", btn_pack: "Build Image",
      btn_launch: "\u25B6 Launch Test", btn_save: "Save",
      tip_lint: "Run nb_validator on the project",
      tip_build: "makegame.sh build: convert assets, pack data, compile engine",
      tip_pack: "makegame.sh make: inject HDI disk image",
      tip_launch: "makegame.sh test --serial: launch emulator with serial log",
      tip_save: "Save current file (Ctrl+S)",
      tab_lint: "Lint", tab_jobs: "Build Output", tab_serial: "Serial Log", tab_media: "Assets",
      lamp_stale: "Image Stale", lamp_ready: "Image Ready",
      lamp_noeng: "Engine Missing", lamp_run: "Job Running",
      group_scenes: "Scenes scene/*.nb", group_cfg: "Project Config",
      group_imgs: "Images", group_audio: "Audio", group_anims: "Animations",
      btn_guide: "Guidebook", tip_guide: "Open the design & dev guidebook",
      anim_fs: "fullscreen", anim_cine: "cinematic", anim_frames: "{n} frames",
      ph_lint: "(no lint run yet)", ph_jobs: "(no jobs)", ph_serial: "(no test started)",
      media_none: "(pick an asset on the left)",
      mag_label: "MAG converted output (as shown in the emulator)",
      midi_note: "\u3000(MIDI preview synth; real sound is FM)",
      no_mag: "(no MAG mapping)", listen: "click to preview",
      label_bgm: "BGM", label_se: "SE", label_voice: "Voice",
      dirty: "\u25CF unsaved", saved_at: "Saved {t}",
      cfg_saved: "Config saved, completions refreshed",
      save_fail: "Save failed: {e}",
      lint_ok: "Validation passed: 0 errors", lint_err: "{n} error(s) found",
      save_first: "Save first (Ctrl+S) before running", submit_fail: "Submit failed",
      job_dup: "A job is already running",
      st_running: "running", st_done: "done", st_failed: "failed",
      exit_code: "(exit {c})",
      sb_ready: "Ready",
      sb_submit: "Submitting {a}\u2026", sb_running: "{a} running\u2026 ({n} lines)",
      sb_done: "{a} done  {t}", sb_fail: "{a} failed (exit {c})  {t}",
      not_found: "File not found", forbidden: "Forbidden",
    },
    zh: {
      btn_lint: "校验", btn_build: "编译数据", btn_pack: "制作镜像",
      btn_launch: "\u25B6 启动测试", btn_save: "保存",
      tip_lint: "运行 nb_validator 校验当前项目",
      tip_build: "makegame.sh build：素材转换+数据打包+引擎编译",
      tip_pack: "makegame.sh make：注入 HDI 磁盘镜像",
      tip_launch: "makegame.sh test --serial：启动模拟器并回传串口日志",
      tip_save: "保存当前文件（Ctrl+S）",
      tab_lint: "校验结果", tab_jobs: "构建输出", tab_serial: "串口日志", tab_media: "素材",
      lamp_stale: "镜像过期", lamp_ready: "镜像就绪",
      lamp_noeng: "引擎缺失", lamp_run: "任务运行中",
      group_scenes: "场景 scene/*.nb", group_cfg: "项目配置",
      group_imgs: "素材图片", group_audio: "音频", group_anims: "动画",
      btn_guide: "设计手册", tip_guide: "打开设计与开发手册（guildbook）",
      anim_fs: "全屏", anim_cine: "电影", anim_frames: "{n} 帧",
      ph_lint: "（尚未校验）", ph_jobs: "（无任务）", ph_serial: "（未开始测试）",
      media_none: "（从左侧选择素材）",
      mag_label: "MAG 转换产物（模拟器实际显示效果）",
      midi_note: "\u3000（MIDI 预览合成音色，实际为 FM 音源）",
      no_mag: "（无 MAG 映射）", listen: "点击试听",
      label_bgm: "BGM", label_se: "SE", label_voice: "语音",
      dirty: "\u25CF 未保存", saved_at: "已保存 {t}",
      cfg_saved: "配置已保存，补全数据已刷新",
      save_fail: "保存失败: {e}",
      lint_ok: "校验通过：0 错误", lint_err: "校验发现 {n} 个错误",
      save_first: "请先保存（Ctrl+S）再执行", submit_fail: "提交失败",
      job_dup: "该任务已在运行",
      st_running: "运行中", st_done: "完成", st_failed: "失败",
      exit_code: "(退出码 {c})",
      sb_ready: "就绪",
      sb_submit: "提交 {a}\u2026", sb_running: "{a} 运行中\u2026（输出 {n} 行）",
      sb_done: "{a} 完成  {t}", sb_fail: "{a} 失败（退出码 {c}）  {t}",
      not_found: "文件不存在", forbidden: "禁止访问",
    },
    ja: {
      btn_lint: "検証", btn_build: "データ生成", btn_pack: "イメージ作成",
      btn_launch: "\u25B6 テスト起動", btn_save: "保存",
      tip_lint: "nb_validator でプロジェクトを検証",
      tip_build: "makegame.sh build：素材変換＋データ梱包＋エンジン编译",
      tip_pack: "makegame.sh make：HDI ディスクイメージへ注入",
      tip_launch: "makegame.sh test --serial：エミュレータ起動＋シリアルログ取得",
      tip_save: "現在のファイルを保存（Ctrl+S）",
      tab_lint: "検証結果", tab_jobs: "ビルド出力", tab_serial: "シリアルログ", tab_media: "素材",
      lamp_stale: "イメージ未更新", lamp_ready: "イメージ準備完了",
      lamp_noeng: "エンジン未生成", lamp_run: "ジョブ実行中",
      group_scenes: "シーン scene/*.nb", group_cfg: "プロジェクト設定",
      group_imgs: "素材画像", group_audio: "オーディオ", group_anims: "アニメ",
      btn_guide: "開発ガイド", tip_guide: "デザイン・開発ガイドを開く",
      anim_fs: "フルスクリーン", anim_cine: "シネマ", anim_frames: "{n} フレーム",
      ph_lint: "（未検証）", ph_jobs: "（ジョブなし）", ph_serial: "（テスト未開始）",
      media_none: "（左側で素材を選択）",
      mag_label: "MAG 変換後の出力（エミュレータ表示と同一）",
      midi_note: "\u3000（MIDI プレビュー合成音。実際は FM 音源）",
      no_mag: "（MAG マッピングなし）", listen: "クリックで試聴",
      label_bgm: "BGM", label_se: "SE", label_voice: "ボイス",
      dirty: "\u25CF 未保存", saved_at: "保存済み {t}",
      cfg_saved: "設定を保存、補完データを更新しました",
      save_fail: "保存失敗: {e}",
      lint_ok: "検証合格：0 エラー", lint_err: "{n} 件のエラー",
      save_first: "先に保存してください（Ctrl+S）", submit_fail: "送信失敗",
      job_dup: "ジョブが既に実行中です",
      st_running: "実行中", st_done: "完了", st_failed: "失敗",
      exit_code: "(終了コード {c})",
      sb_ready: "準備完了",
      sb_submit: "{a} を送信中\u2026", sb_running: "{a} 実行中\u2026（{n} 行）",
      sb_done: "{a} 完了  {t}", sb_fail: "{a} 失敗（終了コード {c}）  {t}",
      not_found: "ファイルが存在しません", forbidden: "アクセス禁止",
    },
    ko: {
      btn_lint: "검증", btn_build: "데이터 빌드", btn_pack: "이미지 생성",
      btn_launch: "\u25B6 테스트 실행", btn_save: "저장",
      tip_lint: "nb_validator로 프로젝트 검증",
      tip_build: "makegame.sh build: 에셋 변환+데이터 패킹+엔진 컴파일",
      tip_pack: "makegame.sh make: HDI 디스크 이미지 주입",
      tip_launch: "makegame.sh test --serial: 에뮬레이터 실행+시리얼 로그",
      tip_save: "현재 파일 저장 (Ctrl+S)",
      tab_lint: "검증 결과", tab_jobs: "빌드 출력", tab_serial: "시리얼 로그", tab_media: "에셋",
      lamp_stale: "이미지 지연", lamp_ready: "이미지 준비됨",
      lamp_noeng: "엔진 없음", lamp_run: "작업 실행 중",
      group_scenes: "씬 scene/*.nb", group_cfg: "프로젝트 설정",
      group_imgs: "이미지", group_audio: "오디오", group_anims: "애니메이션",
      btn_guide: "개발 가이드", tip_guide: "디자인·개발 가이드 열기",
      anim_fs: "전체 화면", anim_cine: "시네마", anim_frames: "{n} 프레임",
      ph_lint: "(아직 검증 안 함)", ph_jobs: "(작업 없음)", ph_serial: "(테스트 미시작)",
      media_none: "(왼쪽에서 에셋 선택)",
      mag_label: "MAG 변환 결과 (에뮬레이터 표시와 동일)",
      midi_note: "\u3000(MIDI 미리듣기 합성음, 실제는 FM 음원)",
      no_mag: "(MAG 매핑 없음)", listen: "클릭하여 미리듣기",
      label_bgm: "BGM", label_se: "SE", label_voice: "음성",
      dirty: "\u25CF 저장 안 됨", saved_at: "저장됨 {t}",
      cfg_saved: "설정 저장, 자동완성 데이터 갱신됨",
      save_fail: "저장 실패: {e}",
      lint_ok: "검증 통과: 0 오류", lint_err: "{n}개 오류 발견",
      save_first: "먼저 저장하세요 (Ctrl+S)", submit_fail: "제출 실패",
      job_dup: "작업이 이미 실행 중입니다",
      st_running: "실행 중", st_done: "완료", st_failed: "실패",
      exit_code: "(종료 코드 {c})",
      sb_ready: "준비",
      sb_submit: "{a} 제출 중\u2026", sb_running: "{a} 실행 중\u2026 ({n}줄)",
      sb_done: "{a} 완료  {t}", sb_fail: "{a} 실패 (종료 코드 {c})  {t}",
      not_found: "파일이 없습니다", forbidden: "접근 금지",
    },
  };

  var LANGS = ["en", "zh", "ja", "ko"];
  var LS_KEY = "naiz_studio_lang";

  function dict(lang) { return DICT[lang] || DICT.en; }

  window.t = function (key, vars) {
    var s = dict(localStorage.getItem(LS_KEY))[key];
    if (s === undefined) s = DICT.en[key];
    if (s === undefined) return key;
    if (vars) {
      Object.keys(vars).forEach(function (k) {
        s = s.replace("{" + k + "}", vars[k]);
      });
    }
    return s;
  };

  window.currentLang = function () {
    return localStorage.getItem(LS_KEY) || "en";
  };

  window.setLang = function (lang) {
    if (LANGS.indexOf(lang) < 0) lang = "en";
    localStorage.setItem(LS_KEY, lang);
    document.documentElement.lang = lang;
    document.body.setAttribute("data-lang", lang);
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = window.t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-title]").forEach(function (el) {
      el.title = window.t(el.getAttribute("data-i18n-title"));
    });
    var sel = document.getElementById("lang-select");
    if (sel) sel.value = lang;
    document.dispatchEvent(new CustomEvent("langchange"));
  };

  window.initLang = function () {
    window.setLang(window.currentLang());
  };
})();
