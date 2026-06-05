# {year}年度歌单样板（example）

> **本文件是占位样板**，展示一个由 `scripts/import_qqmusic_playlist.py` 导出的年度歌单 yaml 结构。
> 实际使用：把 `年度报告截图.example/` 复制为 `年度报告截图/`，再跑导入脚本，会自动按 QQ 音乐分享链接抓出真实歌单覆盖到对应年份目录。
>
> 字段含义见每行注释。

> 来源：QQ 音乐
> 歌单 ID：<your_playlist_id>          # QQ 音乐分享链接中 `/playlist/<id>` 段
> 创建者：<your_qq_username>            # 你的 QQ 音乐昵称
> 共 N 首                                # 实际导出后会被脚本自动填充
> 抓取时间：YYYY-MM-DD                   # 脚本运行当天日期
> 抓取方式：QQ 音乐公开 cgi（fcg_ucc_getcdinfo_byids_cp.fcg）
> 原始链接：https://y.qq.com/n/ryqq_v2/playlist/<your_playlist_id>?...

```yaml
songs:
  # ---- 样例 1：经典国语 ----
  - title: 海阔天空                    # 歌名（QQ 音乐主名）
    artists: [Beyond]                  # 艺人列表，多艺人用 [a, b, c]
    album: 海阔天空                    # 专辑名
    duration_ms: 326000                # 时长毫秒
    isrc: null                         # ISRC 国际标准录音码（脚本通常拿不到，留 null）
    language: zh                       # zh / en / ja / ko / 其他
    sources:
      qqmusic:
        songmid: "<your_songmid>"      # QQ 音乐内部 ID，直链请求必需
        songid: 0                      # 数字版 ID（可选）
        album_mid: "<your_album_mid>"  # 专辑 mid（用于取专辑封面）
      netease:
        id: null                       # 网易云兜底 ID（搜索匹配后填，未匹配留 null）
    tags: [yearly:<year>, qq_<year>]   # 标签：年度 + 来源平台

  # ---- 样例 2：英文经典（含 version_note 字段） ----
  - title: Hotel California
    artists: [Eagles]
    album: Hotel California
    duration_ms: 391000
    isrc: null
    language: en
    version_note: "QQ 音乐显示名 \"Hotel California (Live)\""  # 多版本/Live/Remix 时填这里
    sources:
      qqmusic:
        songmid: "<your_songmid>"
        songid: 0
        album_mid: "<your_album_mid>"
      netease:
        id: null
    tags: [yearly:<year>, qq_<year>, 英语]
```

---

## 字段速查

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | ✅ | 歌名，按 QQ 音乐主名（去掉 Live / Remix 后缀，单独放 version_note）|
| `artists` | ✅ | 艺人列表，列表序与 QQ 音乐 cgi 返回一致 |
| `album` | ✅ | 专辑名 |
| `duration_ms` | ✅ | 时长毫秒，用于 DJ 时间对齐计算 |
| `language` | ✅ | zh / en / ja / ko / 其他，影响 LLM 旁白语言决策 |
| `isrc` | ⚪ | 国际标准录音码，QQ 音乐 cgi 一般不返回，留 null |
| `version_note` | ⚪ | 当存在多版本时填，用于区分 Live / Remix / 翻唱等 |
| `sources.qqmusic.songmid` | ✅ | QQ 音乐内部 ID，**直链请求必需** |
| `sources.qqmusic.album_mid` | ✅ | 专辑 mid，**封面 URL 拼接必需** |
| `sources.netease.id` | ⚪ | 网易云兜底搜索匹配后填，未匹配留 null |
| `tags` | ✅ | 至少含 `yearly:<year>` + `qq_<year>` 两条，影响 LLM 选歌权重 |

## 实际生成方式

```bash
python scripts/import_qqmusic_playlist.py \
  --batch "https://y.qq.com/n/ryqq_v2/playlist/<your_playlist_id>?..." \
  --year 2022 \
  --output 年度报告截图/2022/qq_music_2022年度歌单.md
```

脚本会自动调 QQ 音乐公开 cgi 拉全量曲目并产出本文件结构的 yaml。
