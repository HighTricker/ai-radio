"""环境感知：地点 + 天气 + 缓存。

V3 #1 任务。链路：
- 优先用前端 Geolocation 拿的 lat/lon（用户授权后才有）
- 没有时走 IP 定位兜底（ip-api.com，免 key；VPN 环境下定位会偏到出口节点）
- 拿到坐标后调和风天气 (QWeather) 实况接口
- 缓存到 data/cache/today.json，按「坐标 0.1 度 + 小时」分桶，1h 内复用避免刷接口

QWeather 限制：免费 1000 次/天，足够 30 分钟刷一次。未配置 key 时静默降级，
只返回地点和时间，前端会自动隐藏天气段。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

from services.config import AI_RADIO_DIR, load_config

logger = logging.getLogger(__name__)

CACHE_PATH = AI_RADIO_DIR / "data" / "cache" / "today.json"
CACHE_TTL_SEC = 60 * 60  # 1 小时

# 和风天气 endpoint。
# 旧用户：devapi.qweather.com（免费）/ api.qweather.com（付费）
# 2024 改版后新用户：每个项目分配专属 host，形如 xxx.re.qweatherapi.com
# 通过 config.credentials.qweather_api_host 覆盖；未配置时 fallback 到 devapi
DEFAULT_QWEATHER_HOST = "devapi.qweather.com"


def _qweather_host() -> str:
    try:
        cfg = load_config()
    except Exception:
        return DEFAULT_QWEATHER_HOST
    h = (cfg.get("credentials", {}) or {}).get("qweather_api_host", "")
    if isinstance(h, str):
        h = h.strip()
        # 跳过 example 模板里未替换的占位符（请在此填入… / <…>），回退默认 host
        if h and not h.startswith("请") and not h.startswith("<"):
            return h.replace("https://", "").replace("http://", "").rstrip("/")
    return DEFAULT_QWEATHER_HOST


def _qweather_geo_url() -> str:
    """新版用户走专属 host 下的 /geo/v2/city/lookup；旧用户回退老域名。"""
    host = _qweather_host()
    if host == DEFAULT_QWEATHER_HOST:
        return "https://geoapi.qweather.com/v2/city/lookup"
    return f"https://{host}/geo/v2/city/lookup"


def _qweather_now_url() -> str:
    return f"https://{_qweather_host()}/v7/weather/now"
# IP 定位兜底（HTTPS 收费版才支持，免费版只有 HTTP）
IP_API = "http://ip-api.com/json/?lang=zh-CN&fields=status,country,regionName,city,lat,lon,query"

# 给天气接口和 IP 定位单独留一个 client，绕开 v2rayN TUN 拦截全靠 NO_PROXY
# main.py 已把网易云域名加入 NO_PROXY；这里我们追加和风/ip-api 域名
import os
_EXTRA_NO_PROXY = "devapi.qweather.com,geoapi.qweather.com,ip-api.com"
if _EXTRA_NO_PROXY not in os.environ.get("NO_PROXY", ""):
    os.environ["NO_PROXY"] = (os.environ.get("NO_PROXY", "") + "," + _EXTRA_NO_PROXY).strip(",")
    os.environ["no_proxy"] = os.environ["NO_PROXY"]


class EnvironmentError(Exception):
    """环境感知调用失败的统一异常（路由层会包成 degraded 字段）"""


def _read_location_override() -> dict | None:
    """读 settings.location_override；存在且格式合法返回标准 location dict，否则 None。

    用户在配置面板搜索 + 选定城市后写入此字段。VPN/LAN IP 场景下绕开浏览器 Geolocation。
    """
    try:
        cfg = load_config()
    except Exception:
        return None
    raw = (cfg.get("settings", {}) or {}).get("location_override")
    if not isinstance(raw, dict):
        return None
    try:
        lat = float(raw.get("lat"))
        lon = float(raw.get("lon"))
    except (TypeError, ValueError):
        return None
    return {
        "lat": lat,
        "lon": lon,
        "city": (raw.get("city") or "").strip(),
        "region": (raw.get("region") or "").strip(),
        "source": "manual",
    }


def _qweather_key() -> str | None:
    """读 config.credentials.qweather_api_key；不存在或占位符返回 None。"""
    try:
        cfg = load_config()
    except Exception:
        return None
    val = (cfg.get("credentials", {}) or {}).get("qweather_api_key", "")
    if not isinstance(val, str):
        return None
    val = val.strip()
    if not val or val.startswith("请"):
        return None
    return val


def _cache_key(lat: float, lon: float) -> str:
    """坐标精度 0.1 度（约 11 km）+ 小时维度的缓存键。"""
    return f"{round(lat, 1)},{round(lon, 1)}|{datetime.now().strftime('%Y-%m-%d-%H')}"


def _read_cache(key: str) -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    entry = data.get(key)
    if not entry:
        return None
    ts = entry.get("ts", 0)
    if datetime.now().timestamp() - ts > CACHE_TTL_SEC:
        return None
    return entry


def _write_cache(key: str, payload: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[key] = {**payload, "ts": datetime.now().timestamp()}
    # 顺手清掉过期项（避免文件无限增长）
    cutoff = datetime.now().timestamp() - CACHE_TTL_SEC * 2
    data = {k: v for k, v in data.items() if isinstance(v, dict) and v.get("ts", 0) > cutoff}
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def locate_by_ip() -> dict:
    """IP 兜底定位。VPN TUN 模式下返回的是出口节点位置，不一定准。"""
    try:
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            resp = client.get(IP_API)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise EnvironmentError(f"IP 定位失败：{type(e).__name__}: {e}")
    if data.get("status") != "success":
        raise EnvironmentError(f"IP 定位返回异常：{data}")
    return {
        "lat": float(data["lat"]),
        "lon": float(data["lon"]),
        "city": data.get("city") or "",
        "region": data.get("regionName") or data.get("country") or "",
        "source": "ip",
    }


def search_city(name: str, api_key: str, limit: int = 5) -> list[dict]:
    """正查：通过和风 GeoAPI 把城市名解析成 [{city, region, country, lat, lon}, ...]。

    给前端「手动指定位置」功能用——VPN/LAN IP 环境下浏览器 Geolocation 不可用时的兜底。
    """
    try:
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            resp = client.get(
                _qweather_geo_url(),
                params={"location": name, "key": api_key, "number": limit, "lang": "zh"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise EnvironmentError(f"城市搜索失败：{type(e).__name__}: {e}")
    code = data.get("code")
    if code == "404":
        return []
    if code != "200":
        raise EnvironmentError(f"和风 GeoAPI 异常：code={code}")
    results: list[dict] = []
    for loc in (data.get("location") or []):
        try:
            results.append({
                "city": loc.get("name", "") or "",
                "region": loc.get("adm2") or loc.get("adm1") or "",
                "country": loc.get("country", "") or "",
                "lat": float(loc.get("lat", "0")),
                "lon": float(loc.get("lon", "0")),
            })
        except Exception:
            continue
    return results


def lookup_city(lat: float, lon: float, api_key: str) -> dict:
    """用和风 GeoAPI 反查行政区（QWeather 的 location 参数是「经度,纬度」顺序）。"""
    try:
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            resp = client.get(
                _qweather_geo_url(),
                params={"location": f"{lon:.4f},{lat:.4f}", "key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise EnvironmentError(f"地名反查失败：{type(e).__name__}: {e}")
    if data.get("code") != "200":
        raise EnvironmentError(f"和风 GeoAPI 异常：code={data.get('code')}")
    locs = data.get("location") or []
    if not locs:
        raise EnvironmentError("和风 GeoAPI 未返回地名")
    top = locs[0]
    return {
        "city": top.get("name", ""),
        "region": top.get("adm2") or top.get("adm1") or "",
    }


def fetch_weather(lat: float, lon: float, api_key: str) -> dict:
    """和风实况：text/temp/icon。失败统一抛 EnvironmentError，路由层降级为不显示天气。"""
    try:
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            resp = client.get(
                _qweather_now_url(),
                params={"location": f"{lon:.4f},{lat:.4f}", "key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise EnvironmentError(f"天气接口失败：{type(e).__name__}: {e}")
    if data.get("code") != "200":
        raise EnvironmentError(f"和风天气异常：code={data.get('code')}")
    now = data.get("now") or {}
    return {
        "text": now.get("text", ""),         # 例：晴 / 多云 / 小雨
        "temp": now.get("temp", ""),         # 字符串数字，例："28"
        "icon": now.get("icon", ""),         # 例："100"，对应天气图标编号
        "humidity": now.get("humidity", ""),
        "wind_dir": now.get("windDir", ""),
    }


def get_environment(lat: float | None = None, lon: float | None = None) -> dict:
    """主入口。

    - 收到前端的 lat/lon → 直接用，反查地名 + 拉天气
    - 没收到 → IP 兜底定位 → 拉天气
    - 命中缓存 → 不打天气接口
    - 没配 qweather_api_key → 只返回地点 + 当前时间，weather=None
    """
    # 拿坐标 + 地名
    # 优先级：settings.location_override > URL 参数 lat/lon > IP 兜底
    # B003 修复：用户主动设置的位置永远赢过浏览器自动定位（避免 race condition：
    # geolocation 异步授权 6s 内用户已在面板手动选了城市，回调不该覆盖手动选择）。
    # 用户要切回 geolocation 自动定位时，clearLocation 清掉 override 即可。
    location: dict
    override = _read_location_override()
    if override:
        location = override
    elif lat is not None and lon is not None:
        location = {"lat": float(lat), "lon": float(lon), "source": "geolocation"}
    else:
        location = locate_by_ip()

    api_key = _qweather_key()

    # 反查地名（仅 geolocation 时；ip-api 自带 city/region）
    if location["source"] == "geolocation":
        if api_key:
            try:
                geo = lookup_city(location["lat"], location["lon"], api_key)
                location.update(geo)
            except EnvironmentError as e:
                logger.warning(f"地名反查降级：{e}")
                location.update({"city": "", "region": ""})
        else:
            location.update({"city": "", "region": ""})

    # 天气：先查缓存
    weather: dict | None = None
    cache_hit = False
    if api_key:
        ck = _cache_key(location["lat"], location["lon"])
        cached = _read_cache(ck)
        if cached and cached.get("weather"):
            weather = cached["weather"]
            cache_hit = True
        else:
            try:
                weather = fetch_weather(location["lat"], location["lon"], api_key)
                _write_cache(ck, {"weather": weather, "location": location})
            except EnvironmentError as e:
                logger.warning(f"天气获取降级：{e}")
                weather = None

    return {
        "location": location,
        "weather": weather,
        "time": datetime.now().isoformat(timespec="seconds"),
        "weather_configured": bool(api_key),
        "cache_hit": cache_hit,
    }
