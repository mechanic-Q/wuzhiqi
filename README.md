# 无支祁

每日新中国多平台发布流程：生成平台封面，并通过 `social-auto-upload` / `sau` 发布到：

- B站
- 抖音
- 小红书
- 微信视频号

> Source-visible proprietary project. You may view the code, but no permission is granted to copy, modify, redistribute, or use it. Not open source.

## What it does

`scripts/daily_china_crosspost.py` expects the daily video pipeline to have already generated:

```text
/mnt/e/每日新中国/<YYYY-MM-DD>/3新闻_概述.md
/mnt/e/每日新中国/<YYYY-MM-DD>/video/每日新中国_<YYYY-MM-DD>_GPT最终版.mp4
/mnt/e/每日新中国/<YYYY-MM-DD>/video/gpt_*.png
```

Then it:

1. Parses `3新闻_概述.md` and selects a headline.
2. Generates covers with `ffmpeg`:
   - B站横版封面 `1920x1080`
   - 小红书竖版封面 `1080x1440`
   - 抖音竖版封面 `1080x1440`
   - 视频号竖版主封面 `1080x1440`（只设置一个主封面，优先手机个人主页）
3. Publishes with `sau` to B站 / 抖音 / 小红书 / 视频号.
4. Prints a four-platform success/failure summary.

## Requirements

- Linux / WSL2
- Python 3
- `ffmpeg` / `ffprobe`
- [`social-auto-upload`](https://github.com/dreammis/social-auto-upload) installed locally
- Valid platform cookies/accounts in `social-auto-upload`

Expected local path in this workflow:

```text
/home/lmr/social-auto-upload
```

## Run

```bash
python3 scripts/daily_china_crosspost.py
```

## Current account conventions

The script currently uses account name:

```text
diyi
```

Platform notes:

- B站: `tid=232` 科工机械
- 抖音: max 5 tags
- 小红书: title <= 20 chars recommended
- 视频号: title <= 15 chars recommended, only set the 3:4 vertical main cover by default

## Scheduling

In Hermes Agent this is scheduled at 12:00 after the 10:00 daily video generation job.

Minimal cron-style command:

```bash
python3 /home/lmr/.hermes/scripts/daily_china_crosspost.py
```

## Security

This repository intentionally does **not** include:

- cookies
- platform account state
- `.env`
- API keys
- generated videos/images
- personal Feishu/GitHub credentials

## License

Custom proprietary source-visible license. See [`LICENSE.md`](./LICENSE.md).

You may view the source code, but no permission is granted to copy, modify, redistribute, sublicense, create derivative works, or use it commercially without explicit written permission.

This is not open source.
