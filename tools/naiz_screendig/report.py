"""
报告生成模块

为截图调试会话生成可视化报告。
"""

import os
import json



def generate_html_report(session_data, session_dir):
    """Generate an HTML debug report"""
    report_path = os.path.join(session_dir, "report.html")

    screenshots = session_data.get("screenshots", [])
    analysis = session_data.get("analysis", {})

    html_parts = []
    html_parts.append("<!DOCTYPE html>")
    html_parts.append("<html lang='zh-CN'>")
    html_parts.append("<head>")
    html_parts.append("<meta charset='UTF-8'>")
    html_parts.append(f"<title>NP2kai 截图调试报告 - {session_data.get('session_id', '')}</title>")
    html_parts.append("<style>")
    html_parts.append("body { font-family: Arial, sans-serif; margin: 20px; background: #fafafa; }")
    html_parts.append("h1 { color: #333; }")
    html_parts.append(".summary { background: #fff; padding: 15px; border-radius: 5px; margin-bottom: 20px; }")
    html_parts.append(".screenshot-item { background: #fff; margin: 15px 0; padding: 15px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }")
    html_parts.append(".screenshot-item img { max-width: 640px; border: 1px solid #ddd; }")
    html_parts.append(".analysis { background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 3px; font-family: monospace; font-size: 12px; }")
    html_parts.append(".issue { color: #d32f2f; font-weight: bold; }")
    html_parts.append(".ok { color: #388e3c; }")
    html_parts.append(".timestamp { color: #666; font-size: 12px; }")
    html_parts.append("</style>")
    html_parts.append("</head>")
    html_parts.append("<body>")

    html_parts.append("<h1>NP2kai 截图调试报告</h1>")

    html_parts.append("<div class='summary'>")
    html_parts.append(f"<p><strong>会话 ID:</strong> {session_data.get('session_id', 'N/A')}</p>")
    html_parts.append(f"<p><strong>开始时间:</strong> {session_data.get('start_time', 'N/A')}</p>")
    html_parts.append(f"<p><strong>截图数量:</strong> {len(screenshots)}</p>")
    html_parts.append("</div>")

    html_parts.append("<h2>截图序列</h2>")

    for shot in screenshots:
        filename = shot["filename"]
        shot_analysis = analysis.get(filename, {})

        html_parts.append("<div class='screenshot-item'>")
        html_parts.append(f"<h3>{filename}</h3>")
        html_parts.append(f"<p class='timestamp'>时间偏移: {shot.get('elapsed', 0):.2f}s | 文件大小: {shot.get('size', 0)} bytes</p>")
        html_parts.append(f"<img src='{filename}' alt='{filename}'>")

        if shot_analysis:
            html_parts.append("<div class='analysis'>")

            color_info = shot_analysis.get("color", {})
            if "error" not in color_info:
                mean = color_info.get("mean", [])
                html_parts.append(f"<p>颜色均值 (R,G,B): {mean}</p>")
                issues = color_info.get("issues", [])
                if issues:
                    html_parts.append(f"<p class='issue'>检测到问题: {', '.join(issues)}</p>")
                else:
                    html_parts.append("<p class='ok'>颜色正常</p>")

            text_info = shot_analysis.get("text", {})
            if "error" not in text_info:
                edge_density = text_info.get("edge_density", 0)
                text_present = text_info.get("text_layer_present", False)
                html_parts.append(f"<p>边缘密度: {edge_density}</p>")
                if text_present:
                    html_parts.append("<p class='issue'>文本层可能存在</p>")
                else:
                    html_parts.append("<p class='ok'>文本层透明</p>")

            baseline_info = shot_analysis.get("baseline", {})
            if "error" not in baseline_info:
                similarity = baseline_info.get("similarity", 0)
                html_parts.append(f"<p>基准相似度: {similarity:.2%}</p>")

            html_parts.append("</div>")

        html_parts.append("</div>")

    html_parts.append("</body>")
    html_parts.append("</html>")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_parts))

    print(f"[report] HTML report generated: {report_path}")
    return report_path


def save_session_json(session_data, session_dir):
    """Save session data as JSON"""
    json_path = os.path.join(session_dir, "session_data.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)
    print(f"[report] Session data saved: {json_path}")
    return json_path
