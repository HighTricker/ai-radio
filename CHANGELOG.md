# Changelog

本项目的重要变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-06-05

首个公开发布版（内部迭代至 V4.2）。

### 核心功能
- **AI 主播写稿**：3 种文案模式——`song_intro`（纯歌曲介绍）/ `song_intro_taste`（结合听歌史）/ `weather_mood`（天气感悟），DeepSeek / 小米 MiMo 双 LLM 可切换
- **真实音色 TTS**：Fish Audio 云端合成，SHA256(文本+音色) 缓存
- **听歌画像注入**：解析 2018-2022 + 2025 共 6 年 QQ 音乐年度报告，生成跨年陪伴钩子（"这首你 2018 国庆循环了 44 遍"）
- **DJ 时间对齐**：旁白长度 ≈ 前奏长度，念完正好接上人声
- **双音源**：QQ 音乐（扫码登录、凭据自动续期）优先，网易云兜底
- **渐进式混音**：前端 Web Audio 双轨，旁白念完线性渐升背景歌曲
- **环境感知**（和风天气）、**预热队列**（切歌秒响应）、**反馈驱动**（dislike 自动跳过）

### 工程
- 架构：后端 FastAPI（:8000）+ QQMusicApi web 服务（:8080）+ 纯静态前端
- 34 例 unittest（解析器）；CORS 收紧、debug 端点开关、`/health` 探活 `:8080`、`load_config` 缓存
- 全项目脱敏，`.gitignore` 排除凭证 / 个人听歌数据 / 第三方库 / venv
- `.gitattributes` 统一换行符

[1.0.0]: https://github.com/HighTricker/ai-radio/releases/tag/v1.0.0
