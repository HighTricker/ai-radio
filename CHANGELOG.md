# Changelog

本项目的重要变更记录于此。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Changed
- **LLM 收敛为单源 DeepSeek**：移除小米 MiMo provider 及其前端选项/配置项（`llm_providers.py` / `main.py` / 前端 `index.html` / `architecture.html` / `config.example.json` 同步）。
- **config.example 占位符统一**：所有占位值改为「请在此填入…」前缀，后端 `_is_real_value` / `_qweather_host` 同步识别，漏填的占位不再被当真凭证去请求 API，也不会被误判为「已填」。
- **文档对齐**：README 增加「项目定位」「前置门槛与成本」「环境要求」「Mac/Linux 手动启动」小节，并标注结构树里 clone 后不存在的目录；样板报告改为「大模型识别截图」工作流（删除对不存在脚本的引用）。

### Fixed
- **QQ 音乐 web 服务依赖补齐**：`backend/requirements.txt` 增加 `loguru / pydantic-settings[toml] / griffe`——它们在上游 QQMusicApi 的 PEP 735 `[dependency-groups].web` 里，`pip install` 不会自动装，缺失会导致 `:8080` 启动崩溃。

### Removed（仅从仓库追踪移除，本地保留）
- 一批硬编码个人绝对路径的 `probe_* / verify_*` 调试脚本、由启动器动态生成的 `_run-*.bat`、个人 `/bug` skill、`frontend/demos/` 早期 UI 草稿——避免发布噪音与本地路径暴露。

### Added
- 开源门面：README badges、`CONTRIBUTING.md`、`.github/` Issue·PR 模板。

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
