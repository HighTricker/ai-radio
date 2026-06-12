# QQ 音乐 {year} 年度听歌报告样板（example · listening_facts 池字段全集）

> **本文件是占位样板**，展示一份 listening_facts 池所需的完整 yaml 结构。
> 实际使用（无需任何脚本）：把你自己各年的 QQ 音乐年度听歌报告**截图**发给一个多模态大模型（如 Claude），让它**按本文件的字段结构**识别成 `.md`。详见项目根 README「接入你自己的听歌画像」。
> 后端 `backend/services/listening_facts.py` 会读取该文件喂给 LLM 主播作为旁白素材。
>
> **落地时**：把整个 `年度报告截图.example/` 目录复制为 `年度报告截图/`，并去掉文件名里的 `.example` 后缀（后端扫描的是 `年度报告截图/{year}/qq_music_{year}年度听歌报告.md`，不带 `.example`）。
>
> 字段含义见每行注释。**截图缺失对应模块时，请把字段值留 `null` 而非编造**。

> 来源：QQ 音乐 App 内年度听歌报告截图
> 提取方式：多模态大模型识别（如 Claude）
> 用户：<your_qq_music_username>
> 报告主题：<your_yearly_theme>          # 例如「时空韧性的修复者」，每人每年不同
> 抓取时间：YYYY-MM-DD

## 年度宏观统计

```yaml
meta:
  year: 2025                         # 报告年份
  platform: qqmusic
  user: <your_qq_music_username>     # QQ 音乐昵称
  listening_level: 0                 # LV.x，10 以上属高粘性老用户
  account_started: YYYY-MM-DD        # 系统推测的开始日（qq_2.jpg）
  total_hours: 0.0                   # 全年总听歌时长（小时小数，由分钟换算）
  total_songs: 0                     # 全年总歌曲数
  total_days: 0                      # 全年有听歌的天数
  percentile: 0.0                    # 超过百分之多少用户
  genre_count: 0                     # 涉及曲风个数
  favorite_genre: <your_top_genre>   # 最爱曲风
  theme: <your_yearly_theme>         # 年度主题（QQ 音乐生成）
  mbti: null                         # 系统贴的 MBTI 标签（qq_21.jpg 四季歌单页面有则填）
  achievement: null                  # 成就名（如「听歌全勤王者」），无则 null
```

## 年度歌曲 TOP 10

```yaml
top_songs:
  - rank: 1
    title: <your_top1_song_title>
    artists: [<your_top1_artist>]
    play_count: 0                    # 整年播放次数
    listening_minutes: 0             # 整年听该曲累计分钟（年度单曲一般 ≥300 分钟）
    version_note: null               # 多版本时填
  - rank: 2
    title: <your_top2_song_title>
    artists: [<your_top2_artist>]
  # ...
  - rank: 10
    title: <your_top10_song_title>
    artists: ["[?]"]                 # 截图字符模糊或截图未提供时用 "[?]" 占位
```

## 年度艺人 TOP 10

```yaml
top_artists:
  - rank: 1
    name: <your_top1_artist>
    listening_minutes: 0             # 整年听该艺人累计分钟
    note: 年度 No.1                  # 系统给艺人的标签（可空）
    top5_songs:                      # 该艺人在你这听得最多的 5 首
      - { song: <song_1>, plays: 0 }
      - { song: <song_2>, plays: 0 }
      - { song: <song_3>, plays: 0 }
      - { song: <song_4>, plays: 0 }
      - { song: <song_5>, plays: 0 }
  - { rank: 2, name: <your_top2_artist> }
  # ...
  - { rank: 10, name: <your_top10_artist> }
```

## 年度专辑 TOP 5

```yaml
top_albums:
  - rank: 1
    title: <your_top1_album>
    artist: <album_artist>
    listening_minutes: 0
    co_listeners: 0                  # 与多少人听过同一专辑（QQ 音乐统计）
  - { rank: 2, title: <your_top2_album>, artist: <album_artist> }
  # ...
  - { rank: 5, title: <your_top5_album>, artist: <album_artist> }
```

## 月度榜单

```yaml
monthly:
  "01": { top_artist: <jan_top_artist>, hours: 0.0 }
  "02": { top_artist: <feb_top_artist>, hours: 0.0 }
  "03": { top_artist: <mar_top_artist>, hours: 0.0 }
  "04": { top_artist: <apr_top_artist>, hours: 0.0 }
  "05": { top_artist: <may_top_artist>, hours: 0.0 }
  "06": { top_artist: <jun_top_artist>, hours: 0.0 }
  "07": { top_artist: <jul_top_artist>, hours: 0.0 }
  "08": { top_artist: <aug_top_artist>, hours: 0.0 }
  "09": { top_artist: <sep_top_artist>, hours: 0.0 }
  "10": { top_artist: <oct_top_artist>, hours: 0.0 }
  "11": { top_artist: <nov_top_artist>, hours: 0.0 }
  "12": { top_artist: <dec_top_artist>, hours: 0.0 }
```

## 年度作曲 / 作词

```yaml
yearly_composer:
  name: <composer_name>
  tag: <system_tag>                  # 系统贴的标签，如「情绪的建筑师」
  description: <one_line_description>
  representative_works: [<work_1>, <work_2>, <work_3>]

yearly_lyricist:
  name: <lyricist_name>
  tag: <system_tag>
  description: <one_line_description>
  representative_works: [<work_1>, <work_2>, <work_3>]
```

## 年度三大关键词

```yaml
keywords:
  - word: <keyword_1>
    occurrences: 0                   # 全年出现次数（QQ 音乐统计的歌词词频）
    quote_source:
      song: <quote_song>
      artist: <quote_artist>
      line: "<song_lyric_line>"      # 包含该关键词的代表歌词
  - word: <keyword_2>
    occurrences: 0
    quote_source: { song: <s>, artist: <a>, line: "<l>" }
  - word: <keyword_3>
    occurrences: 0
    quote_source: { song: <s>, artist: <a>, line: "<l>" }
```

## 四季歌单

```yaml
seasons:
  spring: { song: <spring_song>, artist: <artist> }
  summer: { song: <summer_song>, artist: <artist> }
  autumn: { song: <autumn_song>, artist: <artist> }
  winter: { song: <winter_song>, artist: <artist> }
```

## 特别时刻

```yaml
special_moments:
  - date: YYYY-MM-DD
    type: 单曲循环冠军日             # 类型示例：单曲循环冠军日 / 年度最深夜听歌 / 某艺人日
    song: <song_title>
    artist: <artist>
    play_count: 0
  - date: YYYY-MM-DD
    time: "HH:MM"                    # 深夜时刻可加 time 字段
    type: 年度最深夜听歌
    song: <song_title>
    artist: <artist>
```

## 主播叙事素材库（LLM 旁白核心素材池）

> 这部分是给 AI 电台主播写旁白时直接挑用的"颗粒度高、有故事感"的事实点。
> 建议每条用第二人称（你/你的），让旁白能直接念出来；建议至少 8-12 条覆盖不同维度（时长 / 歌曲 / 艺人 / 月份 / 时刻 / 标签 / 主题）。

- "你 {year} 整年泡在音乐里 **X 小时 Y 分钟**，超过了 Z% 的人。"
- "你的年度歌曲是《<top1_song>》<top1_artist>，整整循环了 N 次。"
- "**X 月 Y 日**那天你把《<song>》单曲循环了 N 遍——那一天你在想什么？"
- "**X 月 Y 日凌晨 H 点 M 分**，全世界都睡了，你在听 <artist> 的《<song>》。"
- "<artist> 陪了你整整 X 个月——M1 月、M2 月、M3 月连霸你的月度歌手榜。"
- "你今年 X 次听到了'<keyword>'这个词——你在反复确认什么。"
- "<composer> 包揽了你的年度作词 + 年度作曲。系统说他是你'<tag>'。"
- "你跟 <album> 一起待了 N 小时，全世界还有 M 万人也跟你听同一段旋律。"
- "QQ 音乐说你是 **<mbti> 听众**——<personality_description>。"
- "你听了 N 首歌，跨越 G 个曲风。但你最爱的，永远是 <favorite_genre>。"
- "QQ 音乐叫你**「<theme>」**——<theme_meaning>。"
