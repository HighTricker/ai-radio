# AI 音乐电台

> AI 主播 + 听歌画像 + 真实音乐 API 驱动的私人电台。

## 项目目标

用 AI 语音生成 + 歌曲 API + 用户听歌画像，为用户播放一档「懂你」的电台 —— AI 主播按心情/天气/历史上的今天写旁白，随后渐进式播放背景歌曲。可接入自己的音乐 API、自己的喜爱歌单、自己的主播音色。

## 前端 dev server 访问规则

`localhost` 在某些 VPN 环境（如 TUN 模式代理）下可能被拦截或 DNS 解析异常。建议：

1. **dev server 监听所有网卡**：
   - 前端 Vite / Astro：`server.host = true`
   - 后端 uvicorn：`--host 0.0.0.0`
2. **三个访问地址按优先级**：
   - ⭐ `http://<本机 LAN IP>:<port>/`（内网段通常不被代理拦截）
   - `http://127.0.0.1:<port>/`（直写 IP 不走 DNS）
   - `http://localhost:<port>/`
3. **查本机 LAN IP**：`ipconfig`（Windows）/ `ifconfig`（macOS / Linux），取 `192.168.x.x` 或 `10.x.x.x` 段
4. **三个都打不开时**：
   - VPN 路由规则：把 `192.168.0.0/16`、`127.0.0.1`、`localhost` 加入 direct 直连名单
   - 浏览器关闭 DoH（安全 DNS）
   - 后端 CORS 白名单同时含 `localhost:<port>` 与 `127.0.0.1:<port>`
5. **端口占用排查**：
   - Windows：`netstat -ano | findstr :<port>` → `taskkill /F /PID <pid>`
   - macOS / Linux：`lsof -i :<port>` → `kill -9 <pid>`

---

> 本地私人配置（个人称呼 / 私人项目引用 / 机器特定路径等）见同级 `CLAUDE.local.md`（已 `.gitignore`，不入仓；Claude Code 会自动加载本地变体）。
