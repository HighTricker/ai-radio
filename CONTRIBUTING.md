# 贡献指南

感谢你对 **AI 音乐电台** 感兴趣！

本项目是**个人向**项目，带有较强的环境假设（Windows 一键脚本、TUN 模式 VPN 适配、依赖作者本人的听歌画像数据）。在动手前，请先了解这些定位（见 [README · 项目定位](README.md#-项目定位先读)）。

## 提交前请先开 Issue

由于项目个人向、改动容易牵动整体设计，**较大的改动请先开一个 Issue 对齐方向**，避免 PR 做完才发现方向不合。小修小补（错别字、明显 bug、文档）可直接 PR。

## 本地开发

环境搭建照 [README · 快速开始](README.md#-快速开始) 即可。要点：

- Python ≥ 3.10，后端与 QQ 服务共用 `ai-radio/.venv`。
- `pip install -r ai-radio/backend/requirements.txt`。

### 运行测试

解析器有零额外配置的 unittest（装好 requirements 后即可跑）：

```bash
cd ai-radio/backend
python -m unittest discover -s tests
```

提交涉及解析 / 归一化逻辑的改动时，请补对应单测。

## 代码风格

- 写得**像周围的代码**：匹配既有的命名、注释密度与习惯用法。
- 路径一律用 `Path(__file__).resolve()` 推导，**不要硬编码盘符 / 绝对路径**。
- 新增外部依赖请同步进 `requirements.txt`。

## 千万不要提交个人数据 / 凭证

以下内容均已 `.gitignore`，**请确保它们不会出现在你的提交里**：

- `ai-radio/data/config.json`（API key / cookie）
- `ai-radio/data/user/taste.md`、`feedback.jsonl`、`data/cache/`、`data/songs/`
- `年度报告截图/`（个人听歌数据）
- `third_party/QQMusicApi/`（含 QQ 凭据 SQLite）

提交前用 `git status` 与 `git diff --cached` 自查一遍。

## 提交信息

使用简洁的中文前缀式信息，例如：

```
feat: 主播支持按时段切换语气
fix: 修复网易云 cookie 失效时未自动重登
docs: 补充 Mac 启动说明
```

## License

提交即表示你同意以本项目的 [MIT License](LICENSE) 授权你的贡献。
