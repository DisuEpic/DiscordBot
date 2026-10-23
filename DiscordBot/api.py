import time
import aiohttp
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import quote
from config import API_BASE_URL, API_KEY, log

class BackendClient:
    CACHE_TTL = 120

    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = str(base_url).rstrip("/")
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

        self._config_cache: Dict[str, Any] = {}
        self._config_cache_time: Dict[str, float] = {}
        self._roles_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._roles_cache_time: Dict[str, float] = {}

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"X-Api-Key": self.api_key} if self.api_key else {}
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=4),
                headers=headers,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

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

    async def get_guild_config(self, guild_id: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        if guild_id in self._config_cache and (now - self._config_cache_time.get(guild_id, 0)) < self.CACHE_TTL:
            return self._config_cache[guild_id]

        status, data = await self._request("GET", f"/config/{guild_id}")
        if status == 200 and isinstance(data, dict):
            self._config_cache[guild_id] = data
            self._config_cache_time[guild_id] = now
            return data
        return self._config_cache.get(guild_id) if status is None else None

    async def save_guild_config(self, config_data: Dict[str, Any]) -> bool:
        status, _ = await self._request("POST", "/config", json=config_data)
        if status == 200:
            self._config_cache.pop(config_data.get("guildId"), None)
            return True
        return False

    async def get_roles(self, guild_id: str) -> List[Dict[str, Any]]:
        now = time.time()
        if guild_id in self._roles_cache and (now - self._roles_cache_time.get(guild_id, 0)) < self.CACHE_TTL:
            return self._roles_cache[guild_id]

        status, data = await self._request("GET", f"/roles?guildId={guild_id}")
        if status == 200 and isinstance(data, list):
            self._roles_cache[guild_id] = data
            self._roles_cache_time[guild_id] = now
            return data
        return self._roles_cache.get(guild_id, [])

    async def add_role(self, guild_id: str, category: str, emoji: str, role_id: str, name: str) -> bool:
        payload = {"guildId": guild_id, "category": category, "emoji": emoji, "roleId": role_id, "name": name}
        status, _ = await self._request("POST", "/roles", json=payload)
        if status == 200:
            self._roles_cache.pop(guild_id, None)
            return True
        return False

    async def delete_role(self, guild_id: str, role_id: str) -> bool:
        status, _ = await self._request("DELETE", f"/roles/{guild_id}/{role_id}")
        if status == 200:
            self._roles_cache.pop(guild_id, None)
            return True
        return False

    async def delete_category_roles(self, guild_id: str, category: str) -> bool:
        status, _ = await self._request("DELETE", f"/roles/category/{guild_id}/{quote(category, safe='')}")
        if status == 200:
            self._roles_cache.pop(guild_id, None)
            return True
        return False

api = BackendClient(API_BASE_URL, API_KEY)