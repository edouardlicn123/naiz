/* Naiz 剧本工坊 — NB 剧本语法模式
 * 行结构: 命令名(参数){载荷}
 *   - 命令名: nb-cmd（已知命令）/ nb-bad（未知命令，红色波浪线）
 *   - 参数:   nb-args（圆括号内）
 *   - 载荷:   nb-payload（花括号内，通常是资产 key 或台词）
 * 命令名清单由前端从 /api/meta 注入。
 */
(function () {
  "use strict";

  window.naizDefineNBMode = function (commands) {
    var list = (commands && commands.length) ? commands : [];
    var cmdRe = list.length
      ? new RegExp("^(?:" + list.map(escapeRe).join("|") + ")$")
      : null;

    function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

    CodeMirror.defineMode("naiznb", function () {
      return {
        startState: function () { return { stage: "cmd" }; },
        copyState: function (s) { return { stage: s.stage }; },
        token: function (stream, state) {
          if (stream.sol()) state.stage = "cmd";

          if (state.stage === "cmd") {
            if (stream.eatSpace()) return null;
            var w = stream.match(/^[A-Za-z_][A-Za-z0-9_]*/);
            if (w) {
              state.stage = "open";
              return cmdRe ? (cmdRe.test(w[0]) ? "nb-cmd" : "nb-bad") : "nb-cmd";
            }
            if (stream.match(/^[;#].*$/)) return "nb-punct";   // 行尾注释/分隔容错
            state.stage = "rest";
          }

          if (state.stage === "open") {
            if (stream.match(/^\(/)) { state.stage = "args"; return "nb-punct"; }
          }
          if (state.stage === "args") {
            if (stream.match(/^[^)]*\)/)) { state.stage = "brace"; return "nb-args"; }
            state.stage = "brace"; // 未闭合参数，宽松处理
          }
          if (state.stage === "brace") {
            if (stream.match(/^\{/)) { state.stage = "payload"; return "nb-brace"; }
          }
          if (state.stage === "payload") {
            if (stream.match(/^[^{}]*\}/)) { state.stage = "rest"; return "nb-payload"; }
            if (stream.eol()) { return "nb-payload"; }         // 未闭合载荷，本行兜底
            stream.next();
            return "nb-payload";
          }

          // rest: 行尾剩余原样消费
          stream.skipToEnd();
          return null;
        },
      };
    });
  };
})();
