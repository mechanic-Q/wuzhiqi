#!/usr/bin/env python3
"""每日新中国 — B站、小红书、视频号发布脚本（无人值守）

前置：10:00 cron 已生成视频 /mnt/e/每日新中国/<date>/video/每日新中国_<date>_GPT最终版.mp4
本脚本在 12:00 运行，做：
  1. 读 3新闻_概述.md，选主图
  2. ffmpeg 生成 B站横版封面(1920x1080) + 小红书竖版封面(1080x1440) + 视频号竖版封面
  3. 用 sau 发布 B站、小红书、视频号
  4. 输出结果摘要

退出码 0=全部成功，1=部分失败，2=致命错误

Do NOT modify any skill files, project files, or install packages.
"""

import re, subprocess, sys, time, random
from datetime import datetime
from pathlib import Path

SAU_DIR = Path("/home/lmr/social-auto-upload")
VENV    = f"source {SAU_DIR}/.venv/bin/activate"
DISPLAY = "env -u DISPLAY"  # WSL2 headless: fully unset DISPLAY so Chromium goes headless

# ── helpers ──────────────────────────────────────────────────────────────

def run(cmd, timeout=300, cwd=None):
    """Run command via bash, return (rc, stdout+stderr)."""
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                       timeout=timeout, cwd=cwd or SAU_DIR)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out.strip()

def sau(platform, *args, timeout=600, xvfb=False):
    disp = "xvfb-run -a" if xvfb else DISPLAY
    cmd = f"{VENV} && {disp} sau {platform} {' '.join(args)}"
    return run(cmd, timeout=timeout)

def ffprobe_duration(path):
    rc, out = run(f'ffprobe -v error -show_entries format=duration -of csv=p=0 "{path}"', timeout=10)
    try: return float(out.strip())
    except: return 0.0

def get_date():
    """Today in YYYY-MM-DD. Cron runs at 12:00 so video is already generated."""
    return datetime.now().strftime("%Y-%m-%d")

def read_headline(date_s):
    """Read 3新闻_概述.md and pick the most striking headline + source image."""
    p = Path(f"/mnt/e/每日新中国/{date_s}/3新闻_概述.md")
    if not p.exists():
        return None, None, None
    text = p.read_text("utf-8")
    # Parse ### entries
    entries = []
    for m in re.finditer(r'###\s+\[(.+?)\]\s+(.+?)\n(.+?)(?=\n###|\n##|\Z)', text, re.S):
        src, title, body = m.group(1), m.group(2).strip(), m.group(3).strip()
        if "当日无真实报道" in body or "栏目留空" in body:
            continue
        entries.append((src, title, body))

    # Priority: 机器人/AI/科技/制造 keywords > everything else
    priority_kw = ["机器人", "具身", "人工智能", "AI", "科技自立", "制造", "工业", "芯片", "半导体", "新能源"]
    best = None
    best_score = -1
    for src, title, body in entries:
        score = 0
        for kw in priority_kw:
            if kw in title or kw in body: score += 2
        # Prefer shorter titles (punchier)
        score += max(0, 30 - len(title)) * 0.1
        if score > best_score:
            best_score = score
            best = (src, title, body)

    if not best:
        return None, None, None

    # Find matching gpt image: pick gpt_01..10, prefer one matching best entry index
    vid_dir = Path(f"/mnt/e/每日新中国/{date_s}/video")
    gpt_images = sorted(vid_dir.glob("gpt_*.png"))
    if not gpt_images:
        return best[0], best[1], best[2]

    # Find index of best entry among real entries
    real_entries = [(s,t,b) for s,t,b in entries if "当日无真实报道" not in b]
    try:
        idx = real_entries.index(best)
        return best[0], best[1], best[2], str(gpt_images[min(idx, len(gpt_images)-1)])
    except ValueError:
        return best[0], best[1], best[2], str(gpt_images[0])

def make_short_title(headline, platform="bilibili"):
    """Generate platform-appropriate short title from headline."""
    # Clean source tags and brackets
    h = re.sub(r'【.+?】', '', headline).strip()
    # Remove common news suffixes
    for suffix in ["（人民要论）", "（活力中国调研行）", "（总书记的人民情怀）"]:
        h = h.replace(suffix, "")
    h = h.strip("——").strip()
    # Remove ｜ and after for cleaner title
    h_short = h.split("｜")[0].strip()
    # Remove quotes
    h = h.replace("\u201c", "").replace("\u201d", "").replace("'", "").replace('"', "")
    h_short = h_short.replace("\u201c", "").replace("\u201d", "").replace("'", "").replace('"', "")
    full = h  # full cleaned headline for keyword matching

    if platform == "xiaohongshu":
        # ≤20 chars, curiosity + specificity
        if "机器人" in full: return "人形机器人真进厂打工了"
        if "科技" in full: return "中国科技今天又有新突破"
        if "导弹" in full or "海军" in full: return "中国海军又有大动作"
        return h_short[:20]
    elif platform == "bili_cover":
        # ≤25 chars for cover text readability
        if "机器人" in full: return "人形机器人真进厂打工了"
        if "科技" in full: return "中国科技又有新突破"
        return h_short[:25]
    else:  # bilibili
        # ≤80 chars, keyword + series tag
        if "机器人" in full: return f"人形机器人进厂打工，中国科技又有新进展｜每日新中国"
        return f"中国科技工业进展速览：{h_short}｜每日新中国"

def make_cover_ffmpeg(src_img, out_path, platform, title_text):
    """Generate platform cover with ffmpeg drawtext overlay."""
    font = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    if not Path(font).exists():
        font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

    if platform == "bilibili":
        # 1920x1080 横版，底部粗白字 + 深色底栏
        vf = (
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            f"drawbox=x=0:y=860:w=1920:h=220:color=black@0.65:t=fill,"
            f"drawtext=fontfile={font}:text='{title_text}':"
            f"fontcolor=white:fontsize=62:x=(w-text_w)/2:y=920:"
            f"shadowcolor=black:shadowx=2:shadowy=2"
        )
        size = "1920x1080"
    elif platform == "xiaohongshu":
        # 1080x1440 竖版，中间偏上白字 + 半透明遮罩
        # Shorten title for XHS
        short = title_text[:18] if len(title_text) > 18 else title_text
        vf = (
            f"scale=1080:1440:force_original_aspect_ratio=increase,"
            f"crop=1080:1440,"
            f"drawbox=x=0:y=580:w=1080:h=280:color=black@0.35:t=fill,"
            f"drawtext=fontfile={font}:text='{short}':"
            f"fontcolor=white:fontsize=54:x=(w-text_w)/2:y=660:"
            f"shadowcolor=black:shadowx=1:shadowy=1"
        )
        size = "1080x1440"
    elif platform == "tencent":
        # 视频号 1080x1440 竖版，大号居中白字，适合社交分享小图
        short = title_text[:15] if len(title_text) > 15 else title_text
        vf = (
            f"scale=1080:1440:force_original_aspect_ratio=increase,"
            f"crop=1080:1440,"
            f"drawbox=x=0:y=540:w=1080:h=360:color=black@0.55:t=fill,"
            f"drawtext=fontfile={font}:text='{short}':"
            f"fontcolor=white:fontsize=72:x=(w-text_w)/2:y=640:"
            f"shadowcolor=black:shadowx=3:shadowy=3,"
            f"drawtext=fontfile={font}:text='每日新中国':"
            f"fontcolor=white@0.8:fontsize=34:x=(w-text_w)/2:y=780:"
            f"shadowcolor=black:shadowx=1:shadowy=1"
        )
        size = "1080x1440"
    else:
        raise ValueError(f"unsupported cover platform: {platform}")

    # Escape single quotes in text for ffmpeg
    title_escaped = title_text.replace("'", r"\'")
    vf = vf.replace(f"text='{title_text}'", f"text='{title_escaped}'")

    cmd = f'ffmpeg -y -hide_banner -loglevel error -i "{src_img}" -vf "{vf}" -s {size} -frames:v 1 "{out_path}"'
    rc, out = run(cmd, timeout=60)
    return rc == 0, out

# ── main ─────────────────────────────────────────────────────────────────

def main():
    date_s = get_date()
    print(f"[INFO] date={date_s}")

    # 1. Locate video
    video = Path(f"/mnt/e/每日新中国/{date_s}/video/每日新中国_{date_s}_GPT最终版.mp4")
    if not video.exists():
        print(f"[FATAL] Video not found: {video}")
        return 2
    dur = ffprobe_duration(str(video))
    if dur < 30:
        print(f"[FATAL] Video too short ({dur:.0f}s), likely GPT image failures")
        return 2
    print(f"[INFO] video={video} dur={dur:.0f}s size={video.stat().st_size//1024}KB")

    # 2. Read headline + pick source image
    result = read_headline(date_s)
    if len(result) == 4:
        src, headline, body, src_img = result
    elif len(result) == 3:
        src, headline, body = result
        src_img = None
    else:
        print("[FATAL] Could not parse news overview")
        return 2

    if not src_img or not Path(src_img).exists():
        # Fallback: use first gpt image
        vid_dir = Path(f"/mnt/e/每日新中国/{date_s}/video")
        gpts = sorted(vid_dir.glob("gpt_*.png"))
        src_img = str(gpts[0]) if gpts else None
        if not src_img:
            print("[FATAL] No source image for cover")
            return 2
    print(f"[INFO] headline={headline} src_img={src_img}")

    # 3. Generate covers
    vid_dir = Path(f"/mnt/e/每日新中国/{date_s}/video")
    covers = {}
    for platform in ["bilibili", "xiaohongshu", "tencent"]:
        if platform == "bilibili":
            title = make_short_title(headline, "bili_cover")
        elif platform == "tencent":
            # 视频号封面大字，适合分享
            title = "人形机器人将进厂打工" if "机器" in headline else (headline[:15] if len(headline) > 15 else headline)
        else:
            title = make_short_title(headline, platform)
        out = str(vid_dir / f"cover_{platform}.png")
        ok, err = make_cover_ffmpeg(src_img, out, platform, title)
        if ok:
            covers[platform] = out
            print(f"[OK] cover_{platform}={out}")
        else:
            print(f"[WARN] cover_{platform} failed: {err}")

    # 4. Platform-specific metadata
    bili_title  = make_short_title(headline, "bilibili")
    bili_desc   = f"每日更新中国科技工业进展。本期亮点：{headline}"
    bili_tags   = "每日新中国,中国科技,人工智能,人形机器人,科技自立,中国制造,科工机械,工业升级,今日要闻,机器人"
    bili_tid    = "232"  # 科技→科工机械

    xhs_title   = make_short_title(headline, "xiaohongshu")
    xhs_desc    = (
        f"{headline}\n\n"
        "今天这期只抓一条主线：科技自立正在落到真实产业里。\n\n"
        "1. 具身智能机器人走向工厂和生活场景\n"
        "2. 中科院机器人技能学习研究有新进展\n"
        "3. 电力市场交易电量同比增长24.8%\n"
        "4. 生物制造、农业现代化也在推进\n\n"
        "我会每天整理一条中国科技工业进展。\n"
        "想长期看中国制造、AI、机器人和产业升级，建议先收藏，明天继续更。"
    )
    xhs_tags    = "人形机器人,人工智能,机器人,智能制造,中国制造,中国智造,科技改变生活,产业升级,科技数码,每日新中国"

    results = {}

    # 5. Publish B站
    print("\n[INFO] Publishing to Bilibili...")
    rc, out = sau("bilibili", "upload-video",
        "--account", "diyi",
        "--file", f'"{video}"',
        "--title", f'"{bili_title}"',
        "--desc", f'"{bili_desc}"',
        "--tid", bili_tid,
        "--tags", f'"{bili_tags}"',
        timeout=600)
    bili_ok = rc == 0 and ("upload" in out.lower() or "BV" in out or "成功" in out)
    results["bilibili"] = {"ok": bili_ok, "rc": rc, "out": out[-500:]}
    print(f"[BILI] ok={bili_ok} rc={rc}")

    # 7. Publish 小红书
    _j = random.uniform(30, 90)
    print(f"\n[INFO] Waiting {_j:.0f}s before Xiaohongshu...")
    time.sleep(_j)
    print("\n[INFO] Publishing to Xiaohongshu...")
    xhs_cover = covers.get("xiaohongshu")
    xhs_args = [
        "upload-video",
        "--account", "diyi",
        "--file", f'"{video}"',
        "--title", f'"{xhs_title}"',
        "--desc", f'"{xhs_desc}"',
        "--tags", f'"{xhs_tags}"',
    ]
    if xhs_cover and Path(xhs_cover).exists():
        xhs_args += ["--thumbnail", f'"{xhs_cover}"']
    rc, out = sau("xiaohongshu", *xhs_args, timeout=600)
    xhs_ok = rc == 0 and ("成功" in out or "发布" in out or rc == 0)
    results["xiaohongshu"] = {"ok": xhs_ok, "rc": rc, "out": out[-500:]}
    print(f"[XHS] ok={xhs_ok} rc={rc}")

    # 8. Publish 视频号
    _j = random.uniform(30, 90)
    print(f"\n[INFO] Waiting {_j:.0f}s before Tencent...")
    time.sleep(_j)
    print("\n[INFO] Publishing to Tencent/WeChat Channels...")
    tc_title = "人形机器人将进厂打工" if "机器" in headline else (headline[:20] if len(headline) > 20 else headline)
    # Pick best gpt image for tencent cover if available
    tc_cover = covers.get("tencent")
    # Build description from real news items
    md_path = Path(f"/mnt/e/每日新中国/{date_s}/3新闻_概述.md")
    tc_bullets = []
    if md_path.exists():
        for m in re.finditer(r'###\s+\[(.+?)\]\s+(.+?)\n', md_path.read_text("utf-8")):
            src, t = m.group(1), m.group(2).strip()
            # Skip empty placeholders
            if "当日无真实报道" in t or "栏目留空" in t:
                continue
            tc_bullets.append(t)
    # Pick top 4 bullets
    tc_bullets = tc_bullets[:4]
    if not tc_bullets:
        tc_bullets = [headline[:30]]

    tc_desc_lines = [headline, "", "今天速览："]
    for i, b in enumerate(tc_bullets, 1):
        # Clean brackets for readability
        b_clean = re.sub(r'[【】\[\]]', '', b)
        tc_desc_lines.append(f"{'①②③④⑤⑥⑦⑧'[i-1]} {b_clean}")
    tc_desc_lines.append("#每日新中国 #中国科技 #人工智能")
    tc_desc = "\n".join(tc_desc_lines)

    tc_args = [
        "upload-video",
        "--account", "diyi",
        "--file", f'"{video}"',
        "--title", f'"{tc_title}"',
        "--short-title", f'"{tc_title[:15]}"',
        "--desc", f'"{tc_desc}"',
        "--tags", '"每日新中国,中国科技,人工智能"',
        "--headed",
    ]
    if tc_cover and Path(tc_cover).exists():
        tc_args += ["--thumbnail", f'"{tc_cover}"']
    rc, out = sau("tencent", *tc_args, timeout=600, xvfb=True)
    tc_ok = rc == 0
    results["tencent"] = {"ok": tc_ok, "rc": rc, "out": out[-500:]}
    print(f"[TENCENT] ok={tc_ok} rc={rc}")

    # 9. Summary
    print("\n" + "="*60)
    print("每日新中国三平台发布结果")
    print("="*60)
    for p, r in results.items():
        status = "✅ 成功" if r["ok"] else "❌ 失败"
        print(f"{p:12s} {status}  rc={r['rc']}")
        if not r["ok"]:
            print(f"  output: {r['out'][-200:]}")

    any_fail = any(not r["ok"] for r in results.values())
    return 1 if any_fail else 0

if __name__ == "__main__":
    sys.exit(main())
