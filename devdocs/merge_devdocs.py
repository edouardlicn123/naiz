#!/usr/bin/env python3
"""
merge_devdocs.py —— 将 devdocs/ 下 devdoc 116-176 的 .md 文件合并为一份 HTML 总结。
模仿 0.2版开发文档总结.html 的格式。
"""

import glob
import html
import os
import re
from collections import OrderedDict

SRC_DIR = "/home/edo/naiz/devdocs"
OUT_FILE = os.path.join(SRC_DIR, "116-176开发文档总结.html")
TEMPLATE_FILE = os.path.join(SRC_DIR, "0.2版开发文档总结.html")

# ---------- 分组方案 ----------
GROUPS = [
    ("g1", "一、输入边界、偏好、翻译收口", 116, 121,
     "CG 后首句对白自动翻页根修启动的 116/117 输入边界收口，118/119/120 玩家偏好分家与单一配置源，121 翻译与脚本长度上限收口。"),
    ("g2", "二、FM 地址修复与 MIDI→FM 通路", 122, 127,
     "BGM 本地静音根因、MIDI 转 FM 通路实现计划与 GM 映射数据、FM 寄存器地址公式根修（125 主 + 验证结果）、以及修复后仍\"无音乐\"的二次排查。"),
    ("g3", "三、BGM 颤动系列诊断", 128, 133,
     "FM_finished 过早、菜单立绘加载期间卡顿、虚拟时钟平滑→步进变基准、剩余颤动与立绘拖慢 ABD 方案、二轮根修与量化预取。"),
    ("g4", "四、参考引擎调研与音频架构选型", 134, 139,
     "OPNA 定时器中断驱动音泵立项（方案 C）、S7 音色试听与 LFO、FM 音色实验室长远方案、实机 flute buzz 反馈、FM 音高低八度根修、虚拟时钟尖峰钳制。"),
    ("g5", "五、BGM buzz 消除与 FM 音色迭代", 140, 155,
     "从全链路 buzz 总览（140）到诊断取证（141-143）、开源 PC98-BGM 调研（144-145）、改造建议与计划（146-150），再到 bell 八度修复、残余电流声、flute-pms 颤音、实机闭环、长笛水泡 legato-tie 根修（151-155）。"),
    ("g6", "六、ISR 中断驱动音泵系列", 157, 171,
     "音色分配器改动（157）、不可打断性取证（163）、方案 A TimerB-IRQ3 立项→实机落地→密集期停顿根因→TimerB 实际周期定论→架构收口与单位化泵→ISR/协作泵双失修复（164-171）。158-162 位于 模仿升级计划/ 子目录，不在本次汇总范围。"),
    ("g7", "七、ISR 路径修复与虚拟时钟收口", 172, 176,
     "修复验证通过（172）、虚拟时钟停顿保护与追赶爆发（173）、TimerB 中断线候选扫描与看门狗选举（174）、ISR 路径回退与根因待解（175）、最终根因定位：DOS/4GW 中断栈段 SS≠DS 致栈局部指针写入失效（176）。"),
]

# ---------- 从模板提取 CSS 和 footer ----------
def extract_template_parts(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # 提取 <style>...</style> 整块
    m = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    style_block = m.group(1) if m else ""
    # 提取 <footer>...</footer>
    m = re.search(r"<footer>(.*?)</footer>", content, re.DOTALL)
    footer_block = m.group(0) if m else ""
    return style_block, footer_block


# ---------- 文件名解析 ----------
def parse_md_filename(fname):
    """返回 (number, title_part, full_path) 或 None"""
    base = os.path.basename(fname)
    m = re.match(r"^(\d+)-(.+)\.md$", base)
    if not m:
        return None
    num = int(m.group(1))
    title = m.group(2)
    return (num, title, fname)


# ---------- 状态判定 ----------
def detect_status(md_text):
    head = md_text[:800]  # 前若干行
    # 按优先级
    if re.search(r"已落地|已实施|已完成|已完结", head):
        return "已落地"
    if re.search(r"未实施", head):
        return "未实施"
    if re.search(r"方案|计划|规划|立项|草案", head):
        return "方案/规划"
    if re.search(r"调研|分析|取证|审计", head):
        return "调研分析"
    if re.search(r"诊断|排查|修复|根修", head):
        return "修复/验证"
    return "开发记录"


# ---------- bullet 提取 ----------
def extract_bullets(md_text, max_bullets=5):
    """优先取 markdown bullet 列表的前几个，否则取有实质内容的段落要点"""
    lines = md_text.split("\n")
    bullets = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        # markdown bullet
        m = re.match(r"^[-*]\s+(.+)$", stripped)
        if m:
            txt = m.group(1).strip()
            # 跳过纯链接行
            if re.fullmatch(r"\[.*?\]\(.*?\)", txt):
                continue
            # 跳过表格分隔行
            if txt.startswith("|---") or txt.startswith("|--"):
                continue
            if len(txt) > 5:
                bullets.append(txt[:180])
                if len(bullets) >= max_bullets:
                    return bullets
    # 如果 bullet 不够，从普通段落补
    if len(bullets) < 3:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            if not stripped:
                continue
            # 跳过标题行、引用块、表格行、bullet 行
            if stripped.startswith("#") or stripped.startswith(">") or stripped.startswith("|"):
                continue
            if re.match(r"^[-*]\s", stripped):
                continue
            if len(stripped) > 20:
                bullets.append(stripped[:180])
                if len(bullets) >= max_bullets:
                    break
    return bullets


# ---------- 最终落点 ----------
def extract_landing(md_text):
    lines = md_text.split("\n")
    # 1) 找含关键词的段落（取第一句）
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.search(r"落地|结论|结果|通过|成功|验证通过|已验证", stripped):
            # 取这一行或下一段
            candidate = stripped
            # 如果太短（可能只是标题），尝试下一段
            if len(candidate) < 15 and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
            # 取第一句（到中文句号或英文句号）
            m = re.match(r"^(.*?[。.!！])", candidate)
            if m:
                landing = m.group(1)
            else:
                landing = candidate[:150]
            if landing and len(landing) > 5 and not landing.startswith("#"):
                return landing
    # 2) 找最后一个 ## 标题下的第一段
    last_h2_idx = -1
    for i, line in enumerate(lines):
        if re.match(r"^##\s+", line.strip()):
            last_h2_idx = i
    if last_h2_idx >= 0:
        for i in range(last_h2_idx + 1, len(lines)):
            s = lines[i].strip()
            if s and not s.startswith("#") and not s.startswith("```") and not s.startswith(">"):
                if len(s) > 10:
                    m = re.match(r"^(.*?[。.!！])", s)
                    return (m.group(1) if m else s[:150])
                break
    return "见文档原文"


# ---------- 现状关联 ----------
def extract_rel(md_text):
    lines = md_text.split("\n")
    for line in lines:
        stripped = line.strip()
        if re.search(r"关联|后续|下一步|依赖|前置|devdoc\s*\d+|devdocs?/\d+", stripped, re.IGNORECASE):
            if len(stripped) > 10 and not stripped.startswith("#") and not stripped.startswith("```"):
                return stripped[:200]
    return None


# ---------- 处理单个 md ----------
def process_md(md_path):
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    parsed = parse_md_filename(md_path)
    if not parsed:
        return None
    num, title, _ = parsed
    status = detect_status(text)
    bullets = extract_bullets(text)
    landing = extract_landing(text)
    rel = extract_rel(text)
    return {
        "num": num,
        "title": title,
        "status": status,
        "bullets": bullets,
        "landing": landing,
        "rel": rel,
    }


# ---------- 主逻辑 ----------
def main():
    style_block, footer_block = extract_template_parts(TEMPLATE_FILE)

    # 发现文件
    pattern = os.path.join(SRC_DIR, "[1][1-7][0-9]-*.md")
    md_files = glob.glob(pattern)
    # 按编号过滤 + 解析
    docs = []
    for fp in md_files:
        parsed = parse_md_filename(fp)
        if not parsed:
            continue
        num, _, _ = parsed
        if 116 <= num <= 176:
            docs.append(fp)

    # 处理 + 排序
    processed = []
    for fp in docs:
        info = process_md(fp)
        if info:
            processed.append((fp, info))
    # 按编号升序；同编号按文件路径字典序
    processed.sort(key=lambda x: (x[1]["num"], x[0]))

    # 分配唯一 HTML id（同编号加 _b, _c 后缀）
    num_seen = {}
    for fp, info in processed:
        n = info["num"]
        count = num_seen.get(n, 0)
        num_seen[n] = count + 1
        info["html_id"] = f"doc-{n}" if count == 0 else f"doc-{n}_{chr(ord('a') + count)}"

    total = len(processed)
    print(f"共发现 {total} 份 devdoc (116-176)")

    # 按分组分桶
    group_buckets = OrderedDict()
    for gid, gtitle, gstart, gend, gdesc in GROUPS:
        group_buckets[gid] = {"title": gtitle, "start": gstart, "end": gend, "desc": gdesc, "items": []}

    for fp, info in processed:
        num = info["num"]
        for gid, gtitle, gstart, gend, gdesc in GROUPS:
            if gstart <= num <= gend:
                group_buckets[gid]["items"].append((fp, info))
                break

    # 生成 HTML
    out_parts = []

    # header
    out_parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Naiz 引擎 116-176 开发文档总结</title>
<style>{style_block}</style>
</head>
<body>
<div class="container">

<header>
  <h1>Naiz 引擎 116-176 开发文档总结</h1>
  <div class="subtitle">devdocs/ 开发记录全量归档汇总 — BGM 修复期、音频架构重构与 Naiz Queue 规划</div>
  <div class="meta">
    <span class="badge">覆盖 116–176 · {total} 份文档</span>
    <span class="badge">版本 0.3.000</span>
    <span class="badge">生成于 2026-10</span>
  </div>
</header>

<nav class="toc">
  <h2>目录</h2>
""")

    # TOC
    toc_entries = [
        ("g1", "一、输入边界、偏好、翻译收口（116–121）"),
        ("g2", "二、FM 地址修复与 MIDI→FM 通路（122–127）"),
        ("g3", "三、BGM 颤动系列诊断（128–133）"),
        ("g4", "四、参考引擎调研与音频架构选型（134–139）"),
        ("g5", "五、BGM buzz 消除与 FM 音色迭代（140–155）"),
        ("g6", "六、ISR 中断驱动音泵系列（157–171）"),
        ("g7", "七、ISR 路径修复与虚拟时钟收口（172–176）"),
    ]
    for gid, label in toc_entries:
        out_parts.append(f'  <a href="#{gid}">{label}</a>\n')
    out_parts.append("</nav>\n\n")

    # sections
    for gid, b in group_buckets.items():
        gtitle = b["title"]
        gstart = b["start"]
        gend = b["end"]
        gdesc = b["desc"]
        bucket = b["items"]
        out_parts.append(f'<!-- ============================================================ -->\n')
        out_parts.append(f'<section class="group" id="{gid}">\n')
        out_parts.append(f'  <div class="group-header"><h2>{html.escape(gtitle)}</h2><span class="range">{gstart} – {gend}</span></div>\n')
        out_parts.append(f'  <p class="group-desc">{html.escape(gdesc)}</p>\n')

        for fp, info in bucket:
            num = info["num"]
            title = html.escape(info["title"])
            status = html.escape(info["status"])
            bullets = info["bullets"]
            landing = html.escape(info["landing"])
            rel = info["rel"]
            hid = info["html_id"]

            out_parts.append(f'  <div class="doc" id="{hid}">\n')
            out_parts.append(f'    <div class="doc-head"><span class="doc-num">{num}</span><span class="doc-title">{title}</span><span class="doc-status">{status}</span></div>\n')
            out_parts.append(f'    <h4>核心思路</h4>\n')
            out_parts.append(f'    <ul>\n')
            for b in bullets:
                out_parts.append(f'      <li>{html.escape(b)}</li>\n')
            out_parts.append(f'    </ul>\n')
            out_parts.append(f'    <div class="landing"><b>最终落点：</b>{landing}</div>\n')
            if rel:
                out_parts.append(f'    <div class="rel"><b>现状关联：</b>{html.escape(rel)}</div>\n')
            out_parts.append(f'  </div>\n\n')

        out_parts.append(f'</section>\n\n')

    # footer — 但要改一下文字，不能直接用模板的 footer（它有固定版本号）
    # 自己构造一个类似的 footer
    out_parts.append(f"""<footer>
  Naiz 引擎 116-176 开发文档总结 · 由 devdocs/（116–176，{total} 份）精炼整理生成 · 版本 0.3.000
</footer>

</div>
</body>
</html>
""")

    # 写文件
    result = "".join(out_parts)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"✅ 已写入: {OUT_FILE}")
    print(f"   总行数: {result.count(chr(10))}")
    print(f"   字节数: {len(result.encode('utf-8'))}")

    # 分组统计
    for gid, b in group_buckets.items():
        nums = [info["num"] for _, info in b["items"]]
        print(f"   {gid} ({b['start']}-{b['end']}): {len(nums)} 份 — {nums}")


if __name__ == "__main__":
    main()
