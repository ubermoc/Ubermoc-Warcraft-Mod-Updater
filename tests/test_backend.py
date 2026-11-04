# Copyright (c) 2026 ubermoc. All rights reserved. See LICENSE.
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "py_modules"))

from ubermoc_wow import discover, github, installer, toc  # noqa: E402
from ubermoc_wow.service import PLUGIN_NAME, Updater  # noqa: E402

BUILD_INFO = (
    "Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|Version!STRING:0|Product!STRING:0\n"
    "us|1|aaa|12.1.5.70688|wow\n"
    "us|1|bbb|1.60.1.70707|wowf\n"
    "us|1|ccc|5.5.4.1|wow_classic\n"
    "us|1|ddd|1.15.9.1|wow_classic_era\n"
    "us|0|eee|9.9.9.9|wow_old\n"
)


def make_game(root: Path, folder: str, product: str) -> Path:
    path = root / folder
    path.mkdir(parents=True)
    (path / ".flavor.info").write_text(f"Product Flavor!STRING:0\n{product}\n")
    return path


def make_zip(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return path


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)


class Discovery(Base):
    def install(self) -> Path:
        steam = self.tmp / ".local/share/Steam"
        pfx = steam / "steamapps/compatdata/4070966097/pfx"
        root = pfx / "drive_c/Program Files (x86)/World of Warcraft"
        root.mkdir(parents=True)
        (root / ".build.info").write_text(BUILD_INFO)
        return root

    def test_finds_games_with_real_layout_and_no_addons_folder(self):
        root = self.install()
        make_game(root, "_retail_", "wow")
        make_game(root, "_forever_", "wowf")
        (root / "Data").mkdir()
        games = discover.find_games(self.tmp)
        self.assertEqual([g.label for g in games], ["Midnight", "Forever"])
        self.assertEqual(games[0].version, "12.1.5.70688")
        self.assertEqual((games[0].interface, games[0].flavor), (120105, "mainline"))
        self.assertEqual((games[1].interface, games[1].flavor), (16001, "forever"))
        self.assertTrue(games[0].addons_path.endswith("_retail_/Interface/AddOns"))

    def test_classic_labels(self):
        root = self.install()
        make_game(root, "_classic_", "wow_classic")
        make_game(root, "_classic_era_", "wow_classic_era")
        self.assertEqual(
            {g.label: g.flavor for g in discover.find_games(self.tmp)},
            {"Mists Classic": "mists", "Classic Era": "classic"},
        )

    def test_unknown_game_is_still_listed(self):
        root = self.install()
        make_game(root, "_new_thing_", "wow_new")
        self.assertEqual(discover.find_games(self.tmp)[0].label, "New Thing")

    def test_future_retail_is_not_mislabeled(self):
        self.assertEqual(discover.label_for("_retail_", "wow", "13.0.0.1"), "Retail")

    def test_inactive_rows_are_ignored(self):
        self.assertNotIn("wow_old", discover.parse_build_info(BUILD_INFO))

    def test_flavor_ranges_match_the_packager(self):
        cases = {11509: "classic", 20506: "bcc", 30405: "wrath", 38002: "titan", 40402: "cata", 50504: "mists", 120105: "mainline"}
        for interface, flavor in cases.items():
            self.assertEqual(discover.flavor_for("x", interface), flavor)
        self.assertEqual(discover.flavor_for("wowf", 170000), "forever")

    def test_product_db_path_ends_at_its_length_byte(self):
        path = b"C:/Program Files (x86)/World of Warcraft"
        data = b"\x12wow" + bytes([len(path)]) + path + b"*\x05enUS"
        self.assertEqual(discover.product_db_paths(data), [path.decode()])

    def test_custom_install_found_through_product_db(self):
        steam = self.tmp / ".local/share/Steam"
        pfx = steam / "steamapps/compatdata/1/pfx"
        (pfx / "drive_c/ProgramData/Battle.net/Agent").mkdir(parents=True)
        (pfx / "dosdevices").mkdir()
        (pfx / "dosdevices/c:").symlink_to("../drive_c")
        root = pfx / "drive_c/Games/WoW"
        root.mkdir(parents=True)
        (root / ".build.info").write_text(BUILD_INFO)
        make_game(root, "_retail_", "wow")
        path = b"C:/Games/WoW"
        (pfx / "drive_c/ProgramData/Battle.net/Agent/product.db").write_bytes(bytes([len(path)]) + path)
        self.assertEqual([g.label for g in discover.find_games(self.tmp)], ["Midnight"])


class Toc(Base):
    def addon(self, name: str, files: dict[str, str]) -> Path:
        path = self.tmp / name
        path.mkdir(exist_ok=True)
        for filename, text in files.items():
            (path / filename).write_text(text, encoding="utf-8")
        return path

    def test_suffix_order(self):
        path = self.addon(
            "Foo",
            {
                "Foo.toc": "## Title: plain",
                "Foo_Mainline.toc": "## Title: family",
                "Foo_Forever.toc": "## Title: forever",
                "Foo_Mists.toc": "## Title: mists",
            },
        )
        self.assertEqual(toc.read_addon(path, "forever").title, "forever")
        self.assertEqual(toc.read_addon(path, "mainline").title, "family")
        self.assertEqual(toc.read_addon(path, "mists").title, "mists")
        self.assertEqual(toc.read_addon(path, "classic").title, "plain")

    def test_bom_and_color_codes(self):
        path = self.addon("Foo", {})
        (path / "Foo.toc").write_bytes(b"\xef\xbb\xbf## Title: |cff00ff00Foo|r Bar\n## Version: 1.2\n")
        addon = toc.read_addon(path, "mainline")
        self.assertEqual((addon.title, addon.version), ("Foo Bar", "1.2"))

    def test_placeholder_version_is_unknown(self):
        path = self.addon("Foo", {"Foo.toc": "## Version: @project-version@\n"})
        self.assertEqual(toc.read_addon(path, "mainline").version, "")

    def test_repo_urls(self):
        self.assertEqual(toc.repo_from_url("https://github.com/owner/name.git"), "owner/name")
        self.assertEqual(toc.repo_from_url("https://github.com/BigWigsMods"), "")
        self.assertEqual(toc.repo_from_url("https://www.wowace.com/projects/bartender4/"), "")
        self.assertEqual(toc.repo_from_url("https://github.com/sponsors/someone"), "")

    def test_folder_without_toc_is_not_an_addon(self):
        (self.tmp / "AddOns/Empty").mkdir(parents=True)
        self.assertEqual(toc.read_addons(self.tmp / "AddOns", "mainline"), [])
        self.assertEqual(toc.read_addons(self.tmp / "Missing", "mainline"), [])

    def test_shared_project_id_groups_and_names_shortest(self):
        a = toc.Addon("BigWigs_Core", "Core", ids=["x-wago-id=1"])
        b = toc.Addon("BigWigs", "BigWigs", "1.0", ids=["x-wago-id=1"])
        c = toc.Addon("Other", "Other")
        rows = toc.build_rows([a, b, c], {}, {"bigwigs": "BigWigsMods/BigWigs"})
        self.assertEqual(rows[0].key, "BigWigs")
        self.assertEqual(rows[0].folders, ["BigWigs", "BigWigs_Core"])
        self.assertEqual((rows[0].repo, rows[0].source), ("BigWigsMods/BigWigs", "catalog"))
        self.assertEqual((rows[1].key, rows[1].repo), ("Other", ""))

    def test_saved_link_beats_detection_and_owns_folders(self):
        a = toc.Addon("Foo", "Foo", repo="toc/repo")
        b = toc.Addon("Foo_Extra", "Extra")
        rows = toc.build_rows([a, b], {"Foo": {"repo": "me/foo", "folders": ["Foo", "Foo_Extra"], "version": "2"}}, {})
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].repo, rows[0].source, rows[0].version), ("me/foo", "link", "2"))

    def test_link_to_deleted_addon_shows_nothing(self):
        self.assertEqual(toc.build_rows([], {"Gone": {"repo": "a/b", "folders": ["Gone"]}}, {}), [])


class Picking(unittest.TestCase):
    META = {
        "releases": [
            {"name": "X", "version": "1", "filename": "nolib.zip", "nolib": True, "metadata": [{"flavor": "mainline"}]},
            {"name": "X", "version": "1", "filename": "main.zip", "nolib": False, "metadata": [{"flavor": "mainline"}]},
            {"name": "X", "version": "1", "filename": "fe.zip", "nolib": False, "metadata": [{"flavor": "forever"}]},
            {"name": "X", "version": "1", "filename": "wr.zip", "nolib": False, "metadata": [{"flavor": "wrath"}]},
        ]
    }

    def test_metadata_flavors(self):
        self.assertEqual(github.pick_from_metadata(self.META, "mainline")["filename"], "main.zip")
        self.assertEqual(github.pick_from_metadata(self.META, "forever")["filename"], "fe.zip")
        self.assertEqual(github.pick_from_metadata(self.META, "titan")["filename"], "wr.zip")
        self.assertIsNone(github.pick_from_metadata(self.META, "mists"))

    def test_asset_names(self):
        assets = [{"name": n} for n in ("Foo-1.0.zip", "Foo-1.0-classic.zip", "Foo-1.0-forever.zip", "Foo-1.0-nolib.zip", "notes.txt")]
        self.assertEqual(github.pick_asset(assets, "mainline")["name"], "Foo-1.0.zip")
        self.assertEqual(github.pick_asset(assets, "classic")["name"], "Foo-1.0-classic.zip")
        self.assertEqual(github.pick_asset(assets, "forever")["name"], "Foo-1.0-forever.zip")

    def test_addon_name_is_not_a_game_name(self):
        for name in ("TitanPanel-6.0.zip", "ClassicCastbars-1.0.zip", "Cataclysmic-1.zip"):
            self.assertEqual(github.asset_flavor(name), "")
        self.assertEqual(github.pick_asset([{"name": "TitanPanel-6.0.zip"}], "mainline")["name"], "TitanPanel-6.0.zip")

    def test_only_other_games_gives_nothing(self):
        self.assertIsNone(github.pick_asset([{"name": "Foo-classic.zip"}], "mainline"))

    def test_parse_repo(self):
        for text in ("owner/name", " owner/name/ ", "https://github.com/owner/name", "https://github.com/owner/name.git", "github.com/owner/name/releases"):
            self.assertEqual(github.parse_repo(text), "owner/name")
        for text in ("", "name", "a/b/c", "https://example.com/x"):
            with self.assertRaises(github.GitHubError):
                github.parse_repo(text)

    def test_only_github_hosts(self):
        self.assertTrue(github._allowed_host("https://release-assets.githubusercontent.com/x"))
        self.assertFalse(github._allowed_host("https://evil.example/x"))
        self.assertFalse(github._allowed_host("https://github.com.evil.example/x"))
        self.assertFalse(github._allowed_host("http://github.com/x"))


class Installing(Base):
    def setUp(self):
        super().setUp()
        self.addons = self.tmp / "game/Interface/AddOns"

    def good_zip(self) -> Path:
        return make_zip(
            self.tmp / "a.zip",
            {"Foo/Foo.toc": "## Version: 2\n", "Foo/new.lua": "new", "Foo_Extra/Foo_Extra_Mainline.toc": "", "README.md": "x"},
        )

    def test_creates_missing_addons_folder(self):
        self.assertEqual(installer.install_zip(self.good_zip(), self.addons), ["Foo", "Foo_Extra"])
        self.assertTrue((self.addons / "Foo/new.lua").is_file())
        self.assertFalse((self.addons / "README.md").exists())
        self.assertEqual([p.name for p in (self.tmp / "game/Interface").iterdir()], ["AddOns"])

    def test_replaces_old_files_and_removes_stale_folders(self):
        (self.addons / "Foo").mkdir(parents=True)
        (self.addons / "Foo/old.lua").write_text("old")
        (self.addons / "Foo_Gone").mkdir()
        (self.addons / "Unrelated").mkdir()
        installer.install_zip(self.good_zip(), self.addons, ["Foo_Gone"])
        self.assertFalse((self.addons / "Foo/old.lua").exists())
        self.assertFalse((self.addons / "Foo_Gone").exists())
        self.assertTrue((self.addons / "Unrelated").exists())

    def test_replaces_folder_of_different_case(self):
        (self.addons / "FOO").mkdir(parents=True)
        installer.install_zip(self.good_zip(), self.addons)
        self.assertEqual(sorted(p.name for p in self.addons.iterdir()), ["Foo", "Foo_Extra"])

    def test_failed_swap_restores_everything(self):
        (self.addons / "Foo").mkdir(parents=True)
        (self.addons / "Foo/old.lua").write_text("old")
        (self.addons / "Foo_Extra").mkdir()
        (self.addons / "Foo_Extra/old.lua").write_text("old2")
        real_replace = os.replace
        calls = []

        def failing(src, dst):
            calls.append(src)
            if len(calls) == 4:  # both moved aside, Foo placed, then Foo_Extra fails
                raise OSError("disk full")
            return real_replace(src, dst)

        with mock.patch("ubermoc_wow.installer.os.replace", failing):
            with self.assertRaises(installer.InstallError):
                installer.install_zip(self.good_zip(), self.addons)
        self.assertEqual((self.addons / "Foo/old.lua").read_text(), "old")
        self.assertEqual((self.addons / "Foo_Extra/old.lua").read_text(), "old2")
        self.assertFalse((self.addons / "Foo/new.lua").exists())
        self.assertEqual([p.name for p in (self.tmp / "game/Interface").iterdir()], ["AddOns"])

    def test_rejects_path_escape(self):
        for name in ("../evil/evil.toc", "/abs/x.toc", "Foo/../../x.toc", "C:/x.toc", "Foo\\x.toc"):
            path = self.tmp / "bad.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr(zipfile.ZipInfo(name), "x")
            with self.assertRaises(installer.InstallError):
                installer.check_zip(path)

    def test_rejects_symlink(self):
        path = self.tmp / "bad.zip"
        info = zipfile.ZipInfo("Foo/link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("Foo/Foo.toc", "")
            z.writestr(info, "/etc/passwd")
        with self.assertRaises(installer.InstallError):
            installer.check_zip(path)

    def test_rejects_source_archive_layout(self):
        path = make_zip(self.tmp / "src.zip", {"Foo-1.0/Foo.toc": ""})
        with self.assertRaises(installer.InstallError):
            installer.check_zip(path)

    def test_rejects_non_zip(self):
        path = self.tmp / "x.zip"
        path.write_text("not a zip")
        with self.assertRaises(installer.InstallError):
            installer.check_zip(path)

    def test_game_running_detection(self):
        procs = {
            "1": ["C:\\Program Files (x86)\\World of Warcraft\\_retail_\\WoW.exe", "-launcherlogin"],
            "2": ["C:\\Program Files (x86)\\World of Warcraft\\World of Warcraft Launcher.exe"],
            "3": ["./Utils/WowVoiceProxy.exe"],
        }
        with mock.patch("os.listdir", return_value=list(procs)), mock.patch.object(installer, "_cmdline", lambda p: procs[p]):
            self.assertTrue(installer.game_running("_retail_"))
            self.assertFalse(installer.game_running("_forever_"))


class Service(Base):
    def setUp(self):
        super().setUp()
        self.plugin = self.tmp / "plugin"
        self.plugin.mkdir()
        (self.plugin / "package.json").write_text('{"version": "0.1.0"}')
        (self.plugin / "catalog.json").write_text('{"Foo": "cat/foo"}')
        self.addons = self.tmp / "AddOns"
        self.game = discover.Game("g1", "Midnight", "_retail_", "wow", "12.1.5.1", 120105, "mainline", str(self.tmp), str(self.addons))
        self.up = Updater(str(self.tmp), str(self.tmp / "settings"), str(self.tmp / "runtime"), str(self.plugin))
        self.up._games = [self.game]
        self.release = github.Release("cat/foo", "Foo", "v2", "foo.zip", "https://github.com/x")

    def installed(self, version="1.0", folder="Foo"):
        (self.addons / folder).mkdir(parents=True, exist_ok=True)
        (self.addons / folder / f"{folder}.toc").write_text(f"## Title: {folder}\n## Version: {version}\n")

    def fake_download(self, files):
        def download(url, dest, limit=0):
            make_zip(Path(dest), files)

        return mock.patch.object(github, "download", download)

    def lookup(self):
        return mock.patch.object(github, "lookup", return_value=self.release)

    def test_status_states(self):
        self.installed("1.0")
        with self.lookup():
            self.assertEqual(self.up.check_addons("g1")["Foo"]["state"], "update")
        self.installed("v2")
        with self.lookup():
            self.assertEqual(self.up.check_addons("g1", True)["Foo"]["state"], "current")
        self.installed("@project-version@")
        with self.lookup():
            self.assertEqual(self.up.check_addons("g1", True)["Foo"]["state"], "unknown")

    def test_release_lookups_are_cached(self):
        self.installed()
        with self.lookup() as lookup:
            self.up.check_addons("g1")
            self.up.check_addons("g1")
            self.assertEqual(lookup.call_count, 1)

    def test_no_release_is_a_status_not_a_crash(self):
        self.installed()
        with mock.patch.object(github, "lookup", side_effect=github.NoRelease("none")):
            self.assertEqual(self.up.check_addons("g1")["Foo"], {"state": "unavailable", "message": "none"})

    def test_update_then_link_survives_in_store(self):
        self.installed("1.0")
        files = {"Foo/Foo.toc": "## Version: @project-version@\n", "Foo_Extra/Foo_Extra.toc": ""}
        with self.lookup(), self.fake_download(files), mock.patch.object(installer, "game_running", return_value=False):
            self.up.update_addon("g1", "Foo")
            rows = self.up.list_addons("g1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["folders"], ["Foo", "Foo_Extra"])
            self.assertEqual(self.up.check_addons("g1")["Foo"]["state"], "current")

    def test_release_without_the_addon_changes_nothing(self):
        self.installed("1.0")
        with self.lookup(), self.fake_download({"Other/Other.toc": ""}), mock.patch.object(installer, "game_running", return_value=False):
            with self.assertRaises(installer.InstallError):
                self.up.update_addon("g1", "Foo")
        self.assertTrue((self.addons / "Foo/Foo.toc").exists())
        self.assertFalse((self.addons / "Other").exists())

    def test_refuses_while_game_runs(self):
        self.installed()
        with mock.patch.object(installer, "game_running", return_value=True):
            with self.assertRaisesRegex(installer.InstallError, "Close Midnight"):
                self.up.update_addon("g1", "Foo")

    def test_add_new_addon_into_empty_game(self):
        self.release.repo = "me/new"
        with self.lookup(), self.fake_download({"New/New.toc": "## Title: New\n"}), mock.patch.object(installer, "game_running", return_value=False):
            self.up.add_addon("g1", "me/new")
        rows = self.up.list_addons("g1")
        self.assertEqual((rows[0]["key"], rows[0]["repo"], rows[0]["source"]), ("New", "me/new", "link"))

    def test_remove_only_unlinks(self):
        self.installed()
        (self.addons / "Bar").mkdir()
        (self.addons / "Bar/Bar.toc").write_text("")
        with self.lookup():
            self.up.save_link("g1", "Bar", "me/bar")
        self.assertEqual(next(r for r in self.up.list_addons("g1") if r["key"] == "Bar")["source"], "link")
        self.assertTrue(self.up.remove_link("g1", "Bar"))
        self.assertTrue((self.addons / "Bar/Bar.toc").exists())
        self.assertEqual(next(r for r in self.up.list_addons("g1") if r["key"] == "Bar")["repo"], "")

    def test_default_addon_offered_only_on_midnight_and_forever(self):
        for product, offered in (("wow", True), ("wowf", True), ("wowt", False), ("wow_classic", False), ("wow_classic_era", False)):
            self.game.product = product
            self.assertEqual(bool(self.up.default_addons("g1")), offered, product)

    def test_default_addon_not_offered_once_installed(self):
        self.assertEqual([a["repo"] for a in self.up.default_addons("g1")], ["ubermoc/Ubermoc-UI", "ubermoc/Ubermoc-Forever"])
        self.installed("1.0", "ubermocui")
        self.assertEqual([a["repo"] for a in self.up.default_addons("g1")], ["ubermoc/Ubermoc-Forever"])
        self.installed("1.0", "ubermocforever")
        self.assertEqual(self.up.default_addons("g1"), [])

    def test_saved_links_to_the_old_ubermocui_repo_move_to_the_new_one(self):
        self.up.store.set_link("g1", "UbermocUI", {"repo": "ubermoc/UbermocUI", "folders": ["UbermocUI"], "owned": ["UbermocUI"], "version": "1.0.103"})
        self.up.store.set_link("g1", "Other", {"repo": "me/other", "folders": [], "owned": [], "version": "1"})
        reopened = Updater(str(self.tmp), str(self.tmp / "settings"), str(self.tmp / "runtime"), str(self.plugin))
        links = reopened.store.links("g1")
        self.assertEqual((links["UbermocUI"]["repo"], links["UbermocUI"]["version"]), ("ubermoc/Ubermoc-UI", "1.0.103"))
        self.assertEqual(links["Other"]["repo"], "me/other")
        self.assertIn("ubermoc/Ubermoc-UI", (self.tmp / "settings/links.json").read_text())

    def test_not_now_is_remembered_per_game(self):
        other = discover.Game("g2", "Forever", "_forever_", "wowf", "1.60.1.1", 16001, "forever", str(self.tmp), str(self.tmp / "Other"))
        self.up._games.append(other)
        self.up.dismiss_default_addon("g1", "UbermocUI")
        self.assertEqual([a["folder"] for a in self.up.default_addons("g1")], ["UbermocForever"])
        self.assertEqual(len(self.up.default_addons("g2")), 2)
        reopened = Updater(str(self.tmp), str(self.tmp / "settings"), str(self.tmp / "runtime"), str(self.plugin))
        reopened._games = [self.game]
        self.assertEqual([a["folder"] for a in reopened.default_addons("g1")], ["UbermocForever"])
        reopened.dismiss_default_addon("g1", "UbermocForever")
        self.assertEqual(reopened.default_addons("g1"), [])

    def test_dismissing_keeps_saved_links(self):
        self.installed()
        with self.lookup():
            self.up.save_link("g1", "Foo", "me/foo")
        self.up.dismiss_default_addon("g1", "UbermocUI")
        self.assertEqual(self.up.store.links("g1")["Foo"]["repo"], "me/foo")

    def test_damaged_links_file_is_kept_aside(self):
        (self.tmp / "settings").mkdir()
        (self.tmp / "settings/links.json").write_text("{broken")
        self.assertEqual(self.up.store.links("g1"), {})
        self.assertTrue((self.tmp / "settings/links.bad").exists())

    def plugin_zip(self, path: Path, name=PLUGIN_NAME, skip=()):
        files = {f"{PLUGIN_NAME}/plugin.json": json.dumps({"name": name}), f"{PLUGIN_NAME}/main.py": "", f"{PLUGIN_NAME}/dist/index.js": ""}
        return make_zip(path, {k: v for k, v in files.items() if not any(k.endswith(s) for s in skip)})

    def test_plugin_version_compare(self):
        with mock.patch.object(github, "latest_release", return_value={"tag_name": "v0.10.0"}):
            info = self.up.check_plugin()
        self.assertEqual((info["current"], info["latest"], info["available"]), ("0.1.0", "0.10.0", True))
        with mock.patch.object(github, "latest_release", return_value=None):
            self.assertFalse(self.up.check_plugin()["available"])

    def test_plugin_update_overwrites_files_in_place(self):
        self.up.plugin_dir = self.tmp / "plugin_dir"
        (self.up.plugin_dir / "dist").mkdir(parents=True)
        (self.up.plugin_dir / "dist/index.js").write_text("old")
        (self.up.plugin_dir / "keep.txt").write_text("keep")
        zip_path = self.plugin_zip(self.tmp / "u.zip")
        make_zip(zip_path, {f"{PLUGIN_NAME}/plugin.json": json.dumps({"name": PLUGIN_NAME}), f"{PLUGIN_NAME}/main.py": "new", f"{PLUGIN_NAME}/dist/index.js": "new"})
        release = {"tag_name": "v9.9.9", "assets": [{"name": "Ubermoc-Warcraft-Mod-Updater.zip", "browser_download_url": "x"}]}
        with mock.patch.object(github, "latest_release", return_value=release), mock.patch.object(github, "download", lambda url, dest, limit=0: Path(dest).write_bytes(zip_path.read_bytes())):
            self.assertEqual(self.up.install_plugin_update(), {"version": "9.9.9"})
        self.assertEqual((self.up.plugin_dir / "dist/index.js").read_text(), "new")
        self.assertEqual((self.up.plugin_dir / "main.py").read_text(), "new")
        self.assertEqual((self.up.plugin_dir / "keep.txt").read_text(), "keep")

    def test_installed_newer_than_latest_is_current(self):
        self.installed("v3")
        with self.lookup():
            self.assertEqual(self.up.check_addons("g1", True)["Foo"]["state"], "current")

    def test_play_info_points_at_the_prefix_the_game_lives_in(self):
        self.game.exe = "/steam/compatdata/42/pfx/drive_c/WoW/_retail_/Wow.exe"
        self.game.prefix, self.game.prefix_appid = "/steam/compatdata/42", 42
        info = self.up.play_info("g1")
        self.assertEqual((info["exe"], info["prefix"], info["prefix_appid"], info["shortcut"]), (self.game.exe, "/steam/compatdata/42", 42, 0))
        self.up.save_shortcut("g1", 123)
        self.assertEqual(self.up.play_info("g1")["shortcut"], 123)
        self.assertEqual(Updater(str(self.tmp), str(self.tmp / "settings"), str(self.tmp / "runtime"), str(self.plugin)).store.shortcut("g1"), 123)

    def test_play_needs_a_wow_exe_in_a_steam_prefix(self):
        self.game.exe = ""
        with self.assertRaises(github.GitHubError):
            self.up.play_info("g1")

    def test_games_remember_their_prefix_and_exe(self):
        root = self.tmp / "compatdata/777/pfx/drive_c/Program Files (x86)/World of Warcraft"
        game_dir = root / "_retail_"
        game_dir.mkdir(parents=True)
        (root / ".build.info").write_text("Branch!STRING:0|Product!STRING:0|Version!STRING:0\nus|wow|12.1.5.70688\n")
        (game_dir / ".flavor.info").write_text("Product Flavor!STRING:0\nwow\n")
        (game_dir / "Wow.exe").write_text("")
        game = discover.games_in_root(root)[0]
        self.assertEqual((game.prefix, game.prefix_appid), (str(self.tmp / "compatdata/777"), 777))
        self.assertEqual(game.exe, str(game_dir / "Wow.exe"))
        (game_dir / "Wow.exe").unlink()
        self.assertEqual(discover.games_in_root(root)[0].exe, "")

    def test_root_plugin_hands_addon_files_back_to_the_game_owner(self):
        calls = []
        folder = self.tmp / "tree"
        (folder / "sub").mkdir(parents=True)
        (folder / "sub/a.lua").write_text("")
        with mock.patch.object(installer.os, "geteuid", return_value=0), mock.patch.object(installer.os, "chown", lambda p, u, g: calls.append(("d", str(p)))), mock.patch.object(installer.os, "lchown", lambda p, u, g: calls.append(("f", str(p)))):
            installer._hand_back(folder, self.tmp)
        self.assertEqual({p for _, p in calls}, {str(folder), str(folder / "sub"), str(folder / "sub/a.lua")})
        with mock.patch.object(installer.os, "geteuid", return_value=1000), mock.patch.object(installer.os, "chown", side_effect=AssertionError):
            installer._hand_back(folder, self.tmp)

    def test_plugin_zip_checks(self):
        self.up._check_plugin_zip(self.plugin_zip(self.tmp / "ok.zip"))
        for bad in (self.plugin_zip(self.tmp / "b1.zip", name="Other"), self.plugin_zip(self.tmp / "b2.zip", skip=("index.js",))):
            with self.assertRaises(github.GitHubError):
                self.up._check_plugin_zip(bad)
        (self.tmp / "b3.zip").write_bytes(io.BytesIO(b"nope").getvalue())
        with self.assertRaises(github.GitHubError):
            self.up._check_plugin_zip(self.tmp / "b3.zip")


if __name__ == "__main__":
    unittest.main()
