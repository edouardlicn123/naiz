"""
图像分析模块

轻量级分析功能，专注于 NP2kai 引擎渲染问题的检测：
1. 颜色平衡检测（青色偏色）
2. 文本层检测
3. 基准图像对比
"""

import os
from PIL import Image, ImageStat, ImageChops, ImageFilter
import numpy as np


class NP2kaiAnalyzer:
    """NP2kai screenshot analyzer"""

    def __init__(self):
        pass

    def analyze_color_balance(self, image_path):
        """Analyze color balance, detect cyan cast"""
        if not os.path.exists(image_path):
            return {"error": "file_not_found"}

        try:
            img = Image.open(image_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            stat = ImageStat.Stat(img)
            r, g, b = stat.mean

            issues = []
            if r < g * 0.5 and r < b * 0.5:
                issues.append("red_channel_low")

            if r > 240 and g > 240 and b > 240:
                issues.append("near_white")
            elif r < 15 and g < 15 and b < 15:
                issues.append("near_black")

            return {
                "mean": [round(r, 1), round(g, 1), round(b, 1)],
                "stddev": [round(s, 1) for s in stat.stddev],
                "issues": issues
            }
        except Exception as e:
            return {"error": str(e)}

    def detect_text_layer(self, image_path):
        """Detect whether a text layer is present (based on edge density)"""
        if not os.path.exists(image_path):
            return {"error": "file_not_found"}

        try:
            img = Image.open(image_path)
            gray = img.convert('L')

            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_data = np.array(edges)
            edge_density = float(np.sum(edge_data > 128)) / (edge_data.shape[0] * edge_data.shape[1])

            return {
                "edge_density": round(edge_density, 4),
                "text_layer_present": edge_density > 0.05
            }
        except Exception as e:
            return {"error": str(e)}

    def compare_with_baseline(self, image_path, baseline_path):
        """Compare with a baseline image"""
        if not os.path.exists(image_path) or not os.path.exists(baseline_path):
            return {"error": "file_not_found"}

        try:
            img = Image.open(image_path).convert('RGB')
            baseline = Image.open(baseline_path).convert('RGB')

            if img.size != baseline.size:
                return {"error": "size_mismatch"}

            diff = ImageChops.difference(img, baseline)
            diff_stat = ImageStat.Stat(diff)
            diff_mean = diff_stat.mean

            total_diff = sum(diff_mean)
            max_possible = 255 * 3
            similarity = 1 - (total_diff / max_possible)

            return {
                "diff_mean": [round(d, 1) for d in diff_mean],
                "diff_max": round(max(diff_mean), 1),
                "similarity": round(similarity, 4)
            }
        except Exception as e:
            return {"error": str(e)}

    def analyze_screenshot(self, image_path, baseline_path=None):
        """Comprehensive analysis of a single screenshot"""
        result = {
            "color": self.analyze_color_balance(image_path),
            "text": self.detect_text_layer(image_path)
        }

        if baseline_path:
            result["baseline"] = self.compare_with_baseline(image_path, baseline_path)

        return result
