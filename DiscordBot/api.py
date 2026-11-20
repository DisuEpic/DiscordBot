import time
import aiohttp
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import quote
from config import API_BASE_URL, API_KEY, log


class BackendClient:
    CACHE_TTL = 120
    MAX_CACHE_ENTRIES = 3000

    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = str(base_url).rstrip("/")
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

        self._config_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._config_cache_time: Dict[str, float] = {}
        self._roles_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._roles_cache_time: Dict[str, float] = {}

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"X-Api-Key": self.api_key} if self.api_key else {}
            connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=4),
                headers=headers,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _prune_cache(self, data_dict: Dict[str, Any], time_dict: Dict[str, float]):
        if len(data_dict) <= self.MAX_CACHE_ENTRIES:
            return
        now = time.time()
        expired = [k for k, ts in time_dict.items() if (now - ts) >= self.CACHE_TTL]
        for k in expired:
            data_dict.pop(k, None)
            time_dict.pop(k, None)
        # Если всё ещё больше лимита — удаляем самые старые 20%
        if len(data_dict) > self.MAX_CACHE_ENTRIES:
            oldest = sorted(time_dict.items(), key=lambda item: item[1])[: len(data_dict) // 5]
            for k, _ in oldest:
                data_dict.pop(k, None)
                time_dict.pop(k, None)

    async def _request(self, method: str, path: str, **kwargs) -> Tuple[Optional[int], Any]:
        url = f"{self.base_url}{path}"
        try:
            session = await self.get_session()
            async with session.request(method, url, **kwargs) as resp:
                data = None
                if "json" in (resp.content_type or ""):
                    data = await resp.json()
                if resp.status >= 400 and resp.status != 404:
                    log.warning("API %s %s -> %s %s", method, path, resp.status, data)
                return resp.status, data
        except Exception:
            log.exception("API %s %s: запрос не удался", method, path)
            return None, None

    async def health(self) -> bool:
        status, _ = await self._request("GET", "/health")
        return status == 200

    async def verify_user(self, guild_id: str, discord_id: str) -> bool:
        status, _ = await self._request("POST", "/users/verify", json={"guildId": guild_id, "discordId": discord_id})
        return status == 200

    async def unverify_user(self, guild_id: str, discord_id: str) -> bool:
        status, _ = await self._request("POST", "/users/unverify", json={"guildId": guild_id, "discordId": discord_id})
        return status in (200, 404)

    async def update_user_role(self, guild_id: str, discord_id: str, role_id: str, add: bool) -> bool:
        status, _ = await self._request(
            "POST", f"/users/{guild_id}/{discord_id}/roles", json={"roleId": role_id, "add": add}
        )
        return status == 200

    async def update_user_roles_batch(
        self, guild_id: str, discord_id: str, add_role_ids: List[str], remove_role_ids: List[str]
    ) -> bool:
        payload = {"addRoleIds": add_role_ids, "removeRoleIds": remove_role_ids}
        status, _ = await self._request("POST", f"/users/{guild_id}/{discord_id}/roles/batch", json=payload)
        return status == 200

    async def get_user_profile(self, guild_id: str, discord_id: str) -> Optional[Dict[str, Any]]:
        status, data = await self._request("GET", f"/users/{guild_id}/{discord_id}")
        return data if status == 200 else None

    # --- МОДУЛЬНЫЕ НАСТРОЙКИ СЕРВЕРА ---

    def _update_cache(self, guild_id: str, data: Any):
        self._prune_cache(self._config_cache, self._config_cache_time)
        if isinstance(data, dict):
            self._config_cache[guild_id] = data
            self._config_cache_time[guild_id] = time.time()
        else:
            self._config_cache.pop(guild_id, None)
            self._config_cache_time.pop(guild_id, None)

    async def get_guild_config(self, guild_id: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        if guild_id in self._config_cache and (now - self._config_cache_time.get(guild_id, 0)) < self.CACHE_TTL:
            return self._config_cache[guild_id]

        status, data = await self._request("GET", f"/config/{guild_id}")
        if status == 200 and isinstance(data, dict):
            self._prune_cache(self._config_cache, self._config_cache_time)
            self._config_cache[guild_id] = data
            self._config_cache_time[guild_id] = now
            return data

        if status == 404:
            # Негативное кэширование: пустые/ненастроенные серверы не бьют в БД на каждое сообщение
            self._prune_cache(self._config_cache, self._config_cache_time)
            self._config_cache[guild_id] = None
            self._config_cache_time[guild_id] = now
            return None

        return self._config_cache.get(guild_id)

    async def update_general_config(self, guild_id: str, log_channel_id: Optional[str]) -> bool:
        status, data = await self._request(
            "PUT", f"/config/{guild_id}/general", json={"logChannelId": log_channel_id}
        )
        if status == 200:
            self._update_cache(guild_id, data)
            return True
        return False

    async def update_security_config(self, guild_id: str, payload: Dict[str, Any]) -> bool:
        status, data = await self._request("PUT", f"/config/{guild_id}/security", json=payload)
        if status == 200:
            self._update_cache(guild_id, data)
            return True
        return False

    async def update_welcome_config(self, guild_id: str, payload: Dict[str, Any]) -> bool:
        status, data = await self._request("PUT", f"/config/{guild_id}/welcome", json=payload)
        if status == 200:
            self._update_cache(guild_id, data)
            return True
        return False

    async def update_voice_config(self, guild_id: str, payload: Dict[str, Any]) -> bool:
        status, data = await self._request("PUT", f"/config/{guild_id}/voice", json=payload)
        if status == 200:
            self._update_cache(guild_id, data)
            return True
        return False

    async def update_ai_config(self, guild_id: str, payload: Dict[str, Any]) -> bool:
        status, data = await self._request("PUT", f"/config/{guild_id}/ai", json=payload)
        if status == 200:
            self._update_cache(guild_id, data)
            return True
        return False

    async def update_stats_config(self, guild_id: str, payload: Dict[str, Any]) -> bool:
        status, data = await self._request("PUT", f"/config/{guild_id}/stats", json=payload)
        if status == 200:
            self._update_cache(guild_id, data)
            return True
        return False

    async def reset_guild_config(self, guild_id: str) -> bool:
        status, data = await self._request("POST", f"/config/{guild_id}/reset")
        if status == 200:
            self._update_cache(guild_id, data)
            return True
        return False

    # --- РОЛИ ПО КНОПКАМ ---

    async def get_roles(self, guild_id: str) -> List[Dict[str, Any]]:
        now = time.time()
        if guild_id in self._roles_cache and (now - self._roles_cache_time.get(guild_id, 0)) < self.CACHE_TTL:
            return self._roles_cache[guild_id]

        status, data = await self._request("GET", f"/roles?guildId={guild_id}")
        if status == 200 and isinstance(data, list):
            self._prune_cache(self._roles_cache, self._roles_cache_time)
            self._roles_cache[guild_id] = data
            self._roles_cache_time[guild_id] = now
            return data
        return self._roles_cache.get(guild_id, [])

    async def add_role(self, guild_id: str, category: str, emoji: str, role_id: str, name: str) -> bool:
        payload = {"guildId": guild_id, "category": category, "emoji": emoji, "roleId": role_id, "name": name}
        status, _ = await self._request("POST", "/roles", json=payload)
        if status == 200:
            self._roles_cache.pop(guild_id, None)
            self._roles_cache_time.pop(guild_id, None)
            return True
        return False

    async def delete_role(self, guild_id: str, role_id: str) -> bool:
        status, _ = await self._request("DELETE", f"/roles/{guild_id}/{role_id}")
        if status == 200:
            self._roles_cache.pop(guild_id, None)
            self._roles_cache_time.pop(guild_id, None)
            return True
        return False

    async def delete_category_roles(self, guild_id: str, category: str) -> bool:
        status, _ = await self._request("DELETE", f"/roles/category/{guild_id}/{quote(category, safe='')}")
        if status == 200:
            self._roles_cache.pop(guild_id, None)
            self._roles_cache_time.pop(guild_id, None)
            return True
        return False


api = BackendClient(API_BASE_URL, API_KEY)