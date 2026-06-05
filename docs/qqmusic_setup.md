# QQ 音乐 cookie 获取指南

> 用途：让 AI 电台后端用你的 QQ 音乐账号取歌曲直链和歌词。**没 cookie 也能跑**，但只能拿到部分歌曲（VIP 歌、特殊版权歌会失败）；填上 cookie 后基本和你在 QQ 音乐 App 里听到的一样。
>
> 有效期：`qm_keyst` 通常 **30-90 天**。如果某天 AI 电台突然 QQ 源全部失败，多半是 cookie 过期了，重做一次本指南即可。

---

## 操作步骤（约 5 分钟）

### 1. 浏览器登录 QQ 音乐网页版

打开 https://y.qq.com/ ，右上角点「登录」，用 QQ 扫码或账号密码登录。

> ⚠️ 必须是**网页版**。QQ 音乐 PC 客户端的 cookie 和网页版不通用，本项目只能用网页版的。

### 2. 打开开发者工具

登录成功后**保持当前页面**，按 `F12`（或 `Ctrl+Shift+I`）打开开发者工具。

### 3. 找到 cookies

在开发者工具里切到 **Application** 标签（Chrome / Edge）或 **Storage** 标签（Firefox）：

```
Application
  └─ Storage
      └─ Cookies
          └─ https://y.qq.com    ← 点这一项
```

右侧会出现一张表格，每行一个 cookie 字段。

### 4. 复制两个字段的值

在表格里找下面两行，记下 **Value** 列的内容：

| Name | Value（举例，每人不一样） |
|---|---|
| `uin` | `o123456789` 或 `123456789` |
| `qm_keyst` | `W_X_XXXXXXXXXXXXXXXXXXXX...`（一长串） |

> `uin` 前面有时带 `o`，复制时带上没关系，代码会自动剥掉。

### 5. 拼成单串填进配置

把两个值用 `; ` 拼起来，**整体填进 `data/config.json`** 的 `qqmusic_cookie` 字段：

```json
"qqmusic_cookie": "uin=123456789; qm_keyst=W_X_XXXXXXXXXXXXXXXXXX"
```

或者打开 AI 电台前端的 ⚙ 配置面板，找到「QQ 音乐」section 填进去保存。

---

## 验证 cookie 有效

后端启动后调测试接口：

```
POST http://localhost:8000/api/v1/config/test
Content-Type: application/json

{"service": "qqmusic"}
```

期望返回：

```json
{"ok": true, "message": "QQ 音乐连通正常（《xxx》直链 XXX 字符，歌词 XXX 字）"}
```

或者直接在浏览器试播：

```
http://localhost:8000/api/v1/debug/qqmusic?songmid=<some_songmid>&title=<song_title>&artists=<artist>
```

返回 JSON 里的 `song_url` 直接访问即可听到对应歌曲。

---

## 失败排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `直链 0 字符` / `result=-1` | cookie 没填或填错了 | 重做步骤 1-5，注意复制完整 |
| `result=2000` 等错误码 | cookie 已过期 | 重新登录网页版再拿一次 |
| `直链能拿到但下载 502` | VPN 拦了 QQ 音乐域名 | 把 `y.qq.com`、`ws.stream.qqmusic.qq.com`、`dl.stream.qqmusic.qq.com`、`y.gtimg.cn` 加入 VPN direct 名单 |
| 只能拿 128k / 普通音质 | 当前账号不是 QQ 音乐 VIP | 升级 QQ 音乐绿钻；或接受次音质 |

---

## 安全提示

`qm_keyst` 等同于你的登录态，**不要分享给别人 / 截图泄露 / 贴公开仓库**。
本项目 `data/config.json` 默认在 `.gitignore` 里，不会被 git 跟踪。
