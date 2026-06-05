# 🎙️ AI 音乐电台

> AI 主播 + 听歌画像 + 真实音乐 API 驱动的私人电台。

一档「懂你」的私人电台：AI 主播按**心情 / 天气 / 历史上的今天**写旁白，用你喜欢的**音色**念出来，随后**渐进式**把背景歌曲推上来——歌单来自你自己的音乐 API 与多年听歌画像。

为「等待时的陪伴感」而做：起一档电台，主播念歌曲介绍 / 散文 / 历史掌故 / 天气感悟，然后把歌缓缓融入。

---

## ✨ 核心特性

- **AI 主播写稿**：5 种文案模式——歌曲介绍 / 经典散文 / 一句话引语 / 历史上的今天 / 天气感悟，由 DeepSeek 或小米 MiMo 大模型生成。
- **真实音色 TTS**：Fish Audio 云端合成，多音色可切换，SHA256(文本+音色) 缓存命中即时返回。
- **听歌画像注入**：解析你的 QQ 音乐 **2018–2025 年度报告**，主播会说「这首你 2018 国庆当天单曲循环了 44 遍」「陪了你 2018、2021 两年」——跨年陪伴感，是「懂你」的精华。
- **DJ 式时间对齐**：按 LRC 前奏长度倒推旁白字数（约 4 字/秒），主播念完正好接上人声第一句。
- **双源音乐**：QQ 音乐（扫码登录，凭据自动续期、几乎永久免维护）优先，网易云兜底；短效直链本地缓存规避过期。
- **渐进式混音**：前端 Web Audio 双轨——旁白念完后 3 秒线性渐升背景歌曲音量。
- **环境感知**：地理定位 + 和风天气 + 时段/季节，喂给「天气感悟」文案。
- **预热队列**：后台预制 5 首完整 episode（含 TTS），切「下一首」秒响应。
- **反馈驱动**：喜欢 / 跳过写入历史，同一首 dislike 累计自动跳过。

---

## 🏗️ 架构

双进程 + 纯静态前端：

| 部件 | 技术 | 端口 |
|---|---|---|
| 后端 API | **FastAPI**：编排选歌 → 多源取流 → 缓存 → LLM 写稿 → TTS | `:8000` |
| QQ 音乐服务 | **QQMusicApi** web 服务：扫码登录 + 凭据 SQLite 存储与自动续期 | `:8080` |
| 前端 | **纯手写 HTML + Web Audio**（无框架、无构建），由后端 `:8000` 托管 | （同 `:8000`） |

业务数据全部文件存储（`json` / `jsonl` / `md` / `mp3`），无数据库（仅 QQ 凭据存在 `:8080` 的 SQLite）。

---

## 🚀 快速开始

> 一键启动脚本为 Windows 版；其他平台可参照其中命令手动起两个服务。

### 1. 安装依赖

后端与 QQ 音乐服务共用 `ai-radio/.venv` 一个虚拟环境：

```powershell
cd ai-radio
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
# QQ 音乐服务的额外依赖见 third_party/QQMusicApi 的安装说明
```

### 2. 配置凭证

复制配置模板并填入你自己的 key：

```powershell
copy ai-radio\data\config.example.json ai-radio\data\config.json
```

各字段获取方式见下方「配置说明」。`data/config.json` 已在 `.gitignore`，不会入仓。

### 3. 启动

双击根目录 **`点我启动电台.bat`** —— 自动拉起后端 `:8000` + QQ 音乐服务 `:8080`，并打开浏览器。

### 4. 登录 QQ 音乐

打开 `/qq-login.html`，用**手机 QQ 扫码**。凭据由 `:8080` 的 SQLite 全权管理并自动续期，几乎永久有效（除非腾讯主动踢账号才需重扫）。

> **VPN（TUN 模式）访问**：`localhost` 可能被代理拦截，建议优先用 `http://<本机 LAN IP>:8000/`（`ipconfig` 查 `192.168.x.x`），其次 `http://127.0.0.1:8000/`。

---

## 🔑 配置说明（API key 获取）

| 字段 | 用途 | 获取 |
|---|---|---|
| `fish_audio_api_key` | AI 主播 TTS | <https://fish.audio> |
| `deepseek_api_key` / `mimo_api_key` | 主播写稿（二选一，`settings.llm_provider` 切换） | <https://platform.deepseek.com> / 小米 MiMo |
| `qweather_api_key` + `qweather_api_host` | 天气感知文案 | <https://dev.qweather.com> |
| `netease_music_u_cookie` | 网易云兜底音源（可选） | 浏览器登录网易云后取 `MUSIC_U` cookie |
| QQ 音乐 | 主音源 | **无需填 cookie**，启动后 `/qq-login.html` 扫码 |

> 建议保持 QQ 音乐绿钻（VIP）有效以获得高音质直链；非 VIP 会自动降级到网易云兜底（覆盖率约 70–80%）。

---

## 🎵 接入你自己的听歌画像

电台的「懂你」来自你的 QQ 音乐年度报告。把各年的**年度听歌报告**整理进 `年度报告截图/<年份>/qq_music_<年份>年度听歌报告.md`，文件内含若干 ` ```yaml ` 结构化块（`meta` / `top_songs` / `special_moments` …）+ 一节「## 主播叙事金句池」。参考 `年度报告截图.example/` 的样板格式。

后端 `services/listening_facts.py` 会自动加载 **2018–2022 + 2025** 各年报告，各年报告 schema 不同也能容错归一化，生成：
- **宏观画像**（注入 system prompt）：年度主题 / 性格标签 / 多年听歌轨迹。
- **当前歌钩子**（注入 user prompt）：这首歌在你历年里的循环次数、单曲循环冠军日、跨年陪伴等。

> 接入方式 = 「按年份放截图 + 大模型识别」工作流：把各年 QQ 年度听歌报告**截图**放进 `年度报告截图/<年份>/`，再让大模型（如 Claude）识别成上述 `.md`。**不提供自动导入脚本**——大模型识别这一步本身就胜任。

---

## 📁 项目结构

```
ai-radio/
  backend/        FastAPI 后端：adapters（音源）/ services（编排·写稿·TTS·画像）/ main.py
  frontend/       纯静态前端：index.html（播放+配置）/ qq-login.html（扫码）
  data/           config.json（gitignore）/ taste.md / feedback.jsonl / cache
  prompts/        5 种文案模式的 prompt 模板
  scripts/        离线工具：歌单导入 / 探针
third_party/
  QQMusicApi/     QQ 音乐 web 服务（:8080，扫码登录 + 取流 + 歌词）
年度报告截图/      个人各年 QQ 音乐听歌报告（听歌画像数据源）
开发文件/          PRD / 开发计划 / 工作计划 / bug 记录
点我启动电台.bat   一键启动（:8000 + :8080 + 开浏览器）
```

---

## 🛠️ 技术栈

FastAPI · Web Audio API · Fish Audio（TTS）· DeepSeek / 小米 MiMo（LLM）· QQMusicApi · pyncm（网易云）· 和风天气 · 霞鹜文楷

---

## 🙏 致谢

- [QQMusicApi](https://github.com/luren-dc/QQMusicApi) —— QQ 音乐 web 服务
- [Fish Audio](https://fish.audio) —— 主播音色合成
- 网易云音乐（via `pyncm`）—— 兜底音源
- DeepSeek / 小米 MiMo —— 主播写稿
- [和风天气](https://www.qweather.com) —— 天气数据
- [霞鹜文楷](https://github.com/lxgw/LxgwWenKai) —— 界面字体

---

## 📄 说明

个人自用项目。歌曲版权归各音乐平台及版权方所有；本项目仅用于个人听歌画像与陪伴，不分发任何音频内容。配置中的 API key、cookie 等凭证均为个人私有，请勿提交到公开仓库（`data/` 已整体 `.gitignore`）。
