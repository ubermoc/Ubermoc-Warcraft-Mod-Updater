# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
"""Decky backend. Every method runs its work off the event loop and returns a dict."""

import asyncio
from typing import Any, Callable

import decky

from ubermoc_wow import github, installer  # noqa: E402
from ubermoc_wow.service import Updater  # noqa: E402

EXPECTED_ERRORS = (github.GitHubError, installer.InstallError)


class Plugin:
    updater: Updater

    async def _main(self):
        self.updater = Updater(
            decky.DECKY_USER_HOME,
            decky.DECKY_PLUGIN_SETTINGS_DIR,
            decky.DECKY_PLUGIN_RUNTIME_DIR,
            decky.DECKY_PLUGIN_DIR,
        )
        decky.logger.info(f"{decky.DECKY_PLUGIN_NAME} {self.updater.plugin_version()} started")

    async def _unload(self):
        pass

    # No _uninstall here: Decky also runs it when it replaces the plugin for an update.

    async def _run(self, work: Callable[..., Any], *args) -> dict:
        try:
            result = await asyncio.get_running_loop().run_in_executor(None, work, *args)
        except EXPECTED_ERRORS as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            decky.logger.exception(f"{getattr(work, '__name__', 'call')} failed")
            return {"ok": False, "error": f"Something went wrong: {e}"}
        return {"ok": True, "result": result}

    async def list_games(self, rescan: bool = False) -> dict:
        return await self._run(self.updater.list_games, rescan)

    async def list_addons(self, game_id: str) -> dict:
        return await self._run(self.updater.list_addons, game_id)

    async def default_addon(self, game_id: str) -> dict:
        return await self._run(self.updater.default_addon, game_id)

    async def dismiss_default_addon(self, game_id: str) -> dict:
        return await self._run(self.updater.dismiss_default_addon, game_id)

    async def check_addons(self, game_id: str, fresh: bool = False) -> dict:
        return await self._run(self.updater.check_addons, game_id, fresh)

    async def check_repo(self, game_id: str, text: str) -> dict:
        return await self._run(self.updater.check_repo, game_id, text)

    async def save_link(self, game_id: str, key: str, text: str) -> dict:
        return await self._run(self.updater.save_link, game_id, key, text)

    async def remove_link(self, game_id: str, key: str) -> dict:
        return await self._run(self.updater.remove_link, game_id, key)

    async def update_addon(self, game_id: str, key: str) -> dict:
        return await self._run(self.updater.update_addon, game_id, key)

    async def add_addon(self, game_id: str, text: str) -> dict:
        return await self._run(self.updater.add_addon, game_id, text)

    async def check_plugin(self) -> dict:
        return await self._run(self.updater.check_plugin)

    async def prepare_plugin_update(self) -> dict:
        return await self._run(self.updater.prepare_plugin_update)
