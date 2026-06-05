# QQ 音乐登录指南（扫码）

> 用途：让 AI 电台用你的 QQ 音乐账号取歌曲直链和歌词。**不登录也能跑**，但只能拿到部分歌曲（VIP 歌、特殊版权歌会失败，自动降级到网易云兜底）；登录后基本和你在 QQ 音乐 App 里听到的一样。
>
> 本项目用**扫码登录** —— 凭据由内置的 QQMusicApi 服务（`:8080`）以 SQLite 管理并自动续期，**扫一次几乎永久有效**（除非腾讯主动踢账号才需重扫）。无需手动复制 cookie。

---

## 操作步骤（约 1 分钟）

1. 启动电台（双击 `点我启动电台.bat`，或手动起后端 `:8000` + QQMusicApi `:8080`）。
2. 浏览器打开 **`http://<本机IP>:8000/qq-login.html`**（如 `http://127.0.0.1:8000/qq-login.html`）。
3. 用**手机 QQ** 扫码确认登录。
4. 页面提示登录成功、显示你的 musicid 即可。回到播放器，QQ 源就生效了。

> 也可以在播放器的 ⚙ 配置面板 →「QQ 音乐」section 点「扫码登录」，打开同一个页面。

---

## 验证是否生效

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

---

## 失败排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 扫码后状态一直不变 | `:8080` 服务没起来 / 多 worker | 确认 QQMusicApi 服务在跑；`config.toml` 里须 `workers=1`（多 worker 会导致轮询命中不同进程，永远拿不到登录成功事件） |
| `直链 0 字符` / `result=-1` | 未登录或凭据失效 | 重新打开 `/qq-login.html` 扫码 |
| 直链能拿到但下载 502 | VPN 拦了 QQ 音乐域名 | 把 `y.qq.com`、`ws.stream.qqmusic.qq.com`、`dl.stream.qqmusic.qq.com`、`y.gtimg.cn` 加入 VPN direct 名单 |
| 只能拿 128k / 普通音质 | 当前账号不是 QQ 音乐 VIP | 升级 QQ 音乐绿钻；或接受次音质 |

---

## 安全提示

登录凭据存在 `:8080` 服务的 `web/data/credentials.sqlite3`（已在 `.gitignore`，不入仓）。**不要分享 / 截图泄露 / 贴到公开仓库。**
