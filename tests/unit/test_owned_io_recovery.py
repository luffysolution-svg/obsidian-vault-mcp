from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from obsidian_vault_mcp.adapters.vault import filesystem as filesystem_module
from obsidian_vault_mcp.adapters.vault.filesystem import (
    VaultFilesystem,
    VaultPathSafetyError,
)


class OwnedIoRecoveryTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows moved-parent regression")
    def test_windows_unlink_cancels_delete_when_parent_moves_before_completion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            literature = vault / "Literature"
            literature.mkdir(parents=True)
            note = literature / "note.md"
            note.write_bytes(b"keep")
            moved_literature = root / "moved-Literature"
            filesystem = VaultFilesystem(vault)
            original_open_relative = filesystem_module._WindowsNative.open_relative
            injected = False

            def move_parent_then_open(
                native: object,
                parent: int,
                name: str,
                **kwargs: object,
            ) -> int:
                nonlocal injected
                if (
                    not injected
                    and name == "note.md"
                    and kwargs.get("relative") == "Literature/note.md"
                ):
                    literature.rename(moved_literature)
                    injected = True
                return original_open_relative(native, parent, name, **kwargs)

            with (
                mock.patch.object(
                    filesystem_module._WindowsNative,
                    "open_relative",
                    new=move_parent_then_open,
                ),
                self.assertRaisesRegex(
                    VaultPathSafetyError,
                    "owned Vault parent moved",
                ),
            ):
                filesystem.unlink_owned("Literature/note.md", missing_ok=False)

            self.assertTrue(injected)
            self.assertFalse(literature.exists())
            self.assertEqual((moved_literature / "note.md").read_bytes(), b"keep")
            self.assertEqual(
                [path.name for path in moved_literature.iterdir()],
                ["note.md"],
            )

    @unittest.skipUnless(os.name == "nt", "Windows moved-parent regression")
    def test_windows_unlink_restores_after_parent_moves_during_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            literature = vault / "Literature"
            literature.mkdir(parents=True)
            note = literature / "note.md"
            note.write_bytes(b"keep")
            moved_literature = root / "moved-Literature"
            filesystem = VaultFilesystem(vault)
            api = filesystem_module._windows_native()
            original_mark_delete = api.mark_delete
            original_close_handle = api.close_handle
            delete_handle: int | None = None
            injected = False

            def remember_delete(handle: int, relative: str) -> None:
                nonlocal delete_handle
                original_mark_delete(handle, relative)
                if relative == "Literature/note.md":
                    delete_handle = handle

            def move_parent_then_close(handle: int) -> bool:
                nonlocal injected
                result = bool(original_close_handle(handle))
                if not injected and handle == delete_handle:
                    literature.rename(moved_literature)
                    injected = True
                return result

            with (
                mock.patch.object(api, "mark_delete", side_effect=remember_delete),
                mock.patch.object(api, "close_handle", side_effect=move_parent_then_close),
                self.assertRaisesRegex(
                    VaultPathSafetyError,
                    "owned Vault parent moved",
                ),
            ):
                filesystem.unlink_owned("Literature/note.md", missing_ok=False)

            self.assertTrue(injected)
            self.assertFalse(literature.exists())
            self.assertEqual((moved_literature / "note.md").read_bytes(), b"keep")
            self.assertEqual(
                [path.name for path in moved_literature.iterdir()],
                ["note.md"],
            )

    @unittest.skipUnless(os.name == "nt", "Windows moved-parent regression")
    def test_windows_rmdir_cancels_delete_when_parent_moves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            literature = vault / "Literature"
            empty = literature / "empty"
            empty.mkdir(parents=True)
            moved_literature = root / "moved-Literature"
            filesystem = VaultFilesystem(vault)
            original_open_relative = filesystem_module._WindowsNative.open_relative
            injected = False

            def move_parent_then_open(
                native: object,
                parent: int,
                name: str,
                **kwargs: object,
            ) -> int:
                nonlocal injected
                if (
                    not injected
                    and name == "empty"
                    and kwargs.get("relative") == "Literature/empty"
                ):
                    literature.rename(moved_literature)
                    injected = True
                return original_open_relative(native, parent, name, **kwargs)

            with (
                mock.patch.object(
                    filesystem_module._WindowsNative,
                    "open_relative",
                    new=move_parent_then_open,
                ),
                self.assertRaisesRegex(
                    VaultPathSafetyError,
                    "owned Vault parent moved",
                ),
            ):
                filesystem.rmdir_owned("Literature/empty", missing_ok=False)

            self.assertTrue(injected)
            self.assertFalse(literature.exists())
            self.assertTrue((moved_literature / "empty").is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows moved-parent regression")
    def test_windows_rmdir_recreates_after_parent_moves_during_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            literature = vault / "Literature"
            empty = literature / "empty"
            empty.mkdir(parents=True)
            moved_literature = root / "moved-Literature"
            filesystem = VaultFilesystem(vault)
            api = filesystem_module._windows_native()
            original_mark_delete = api.mark_delete
            original_close_handle = api.close_handle
            delete_handle: int | None = None
            injected = False

            def remember_delete(handle: int, relative: str) -> None:
                nonlocal delete_handle
                original_mark_delete(handle, relative)
                if relative == "Literature/empty":
                    delete_handle = handle

            def move_parent_after_close(handle: int) -> bool:
                nonlocal injected
                result = bool(original_close_handle(handle))
                if not injected and handle == delete_handle:
                    literature.rename(moved_literature)
                    injected = True
                return result

            with (
                mock.patch.object(api, "mark_delete", side_effect=remember_delete),
                mock.patch.object(api, "close_handle", side_effect=move_parent_after_close),
                self.assertRaisesRegex(
                    VaultPathSafetyError,
                    "owned Vault parent moved",
                ),
            ):
                filesystem.rmdir_owned("Literature/empty", missing_ok=False)

            self.assertTrue(injected)
            self.assertFalse(literature.exists())
            self.assertTrue((moved_literature / "empty").is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows native rename regression")
    def test_windows_postcheck_failure_restores_destination(self) -> None:
        for existed in (False, True):
            with self.subTest(existed=existed), tempfile.TemporaryDirectory() as directory:
                vault = Path(directory) / "vault"
                literature = vault / "Literature"
                literature.mkdir(parents=True)
                note = literature / "note.md"
                if existed:
                    note.write_bytes(b"old")

                filesystem = VaultFilesystem(vault)
                expected_literature = filesystem.root / "Literature"
                original_rename = filesystem_module._WindowsNative.rename_relative
                original_assert = filesystem_module._WindowsNative.assert_path
                primary_completed = False
                failed_postcheck = False

                def observe_primary_rename(
                    native: object,
                    handle: int,
                    destination_parent: int,
                    destination_name: str,
                    *,
                    relative: str,
                ) -> None:
                    nonlocal primary_completed
                    original_rename(
                        native,
                        handle,
                        destination_parent,
                        destination_name,
                        relative=relative,
                    )
                    if relative == "Literature/note.md" and destination_name == "note.md":
                        primary_completed = True

                def fail_after_primary_rename(
                    native: object,
                    handle: int,
                    expected: Path,
                    relative: str,
                ) -> None:
                    nonlocal failed_postcheck
                    if (
                        primary_completed
                        and not failed_postcheck
                        and relative == "Literature/note.md"
                        and expected == expected_literature
                    ):
                        failed_postcheck = True
                        raise VaultPathSafetyError(
                            relative,
                            f"owned Vault parent moved during I/O: {relative}",
                        )
                    original_assert(native, handle, expected, relative)

                with (
                    mock.patch.object(
                        filesystem_module._WindowsNative,
                        "rename_relative",
                        new=observe_primary_rename,
                    ),
                    mock.patch.object(
                        filesystem_module._WindowsNative,
                        "assert_path",
                        new=fail_after_primary_rename,
                    ),
                    self.assertRaisesRegex(
                        VaultPathSafetyError,
                        "owned Vault parent moved",
                    ),
                ):
                    filesystem.atomic_write_bytes_owned(
                        "Literature/note.md",
                        b"new",
                    )

                self.assertTrue(primary_completed)
                self.assertTrue(failed_postcheck)
                if existed:
                    self.assertEqual(note.read_bytes(), b"old")
                    self.assertEqual([path.name for path in literature.iterdir()], ["note.md"])
                else:
                    self.assertFalse(note.exists())
                    self.assertEqual(list(literature.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Windows moved-parent regression")
    def test_windows_moved_parent_is_restored_outside_vault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            literature = vault / "Literature"
            literature.mkdir(parents=True)
            note = literature / "note.md"
            note.write_bytes(b"outside-original")
            staging = vault / "staging"
            staging.mkdir()
            staged = staging / "managed.tmp"
            staged.write_bytes(b"managed-new")
            moved_literature = root / "moved-Literature"

            filesystem = VaultFilesystem(vault)
            original_rename = filesystem_module._WindowsNative.rename_relative
            injected = False

            def move_parent_after_precheck(
                native: object,
                handle: int,
                destination_parent: int,
                destination_name: str,
                *,
                relative: str,
            ) -> None:
                nonlocal injected
                if (
                    not injected
                    and relative == "Literature/note.md"
                    and destination_name == "note.md"
                ):
                    injected = True
                    literature.rename(moved_literature)
                original_rename(
                    native,
                    handle,
                    destination_parent,
                    destination_name,
                    relative=relative,
                )

            with (
                mock.patch.object(
                    filesystem_module._WindowsNative,
                    "rename_relative",
                    new=move_parent_after_precheck,
                ),
                self.assertRaisesRegex(
                    VaultPathSafetyError,
                    "owned Vault parent moved",
                ),
            ):
                filesystem.atomic_replace_owned(
                    "staging/managed.tmp",
                    "Literature/note.md",
                )

            self.assertTrue(injected)
            self.assertFalse(literature.exists())
            self.assertEqual((moved_literature / "note.md").read_bytes(), b"outside-original")
            self.assertEqual(
                [path.name for path in moved_literature.iterdir()],
                ["note.md"],
            )
            self.assertEqual(staged.read_bytes(), b"managed-new")

    @unittest.skipUnless(os.name == "nt", "Windows native rename regression")
    def test_windows_replace_postcheck_failure_restores_both_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            literature = vault / "Literature"
            literature.mkdir(parents=True)
            note = literature / "note.md"
            note.write_bytes(b"old")
            staging = vault / "staging"
            staging.mkdir()
            staged = staging / "managed.tmp"
            staged.write_bytes(b"new")

            filesystem = VaultFilesystem(vault)
            expected_literature = filesystem.root / "Literature"
            original_rename = filesystem_module._WindowsNative.rename_relative
            original_assert = filesystem_module._WindowsNative.assert_path
            primary_completed = False
            failed_postcheck = False

            def observe_primary_rename(
                native: object,
                handle: int,
                destination_parent: int,
                destination_name: str,
                *,
                relative: str,
            ) -> None:
                nonlocal primary_completed
                original_rename(
                    native,
                    handle,
                    destination_parent,
                    destination_name,
                    relative=relative,
                )
                if relative == "Literature/note.md" and destination_name == "note.md":
                    primary_completed = True

            def fail_after_primary_rename(
                native: object,
                handle: int,
                expected: Path,
                relative: str,
            ) -> None:
                nonlocal failed_postcheck
                if (
                    primary_completed
                    and not failed_postcheck
                    and relative == "Literature/note.md"
                    and expected == expected_literature
                ):
                    failed_postcheck = True
                    raise VaultPathSafetyError(
                        relative,
                        f"owned Vault parent moved during I/O: {relative}",
                    )
                original_assert(native, handle, expected, relative)

            with (
                mock.patch.object(
                    filesystem_module._WindowsNative,
                    "rename_relative",
                    new=observe_primary_rename,
                ),
                mock.patch.object(
                    filesystem_module._WindowsNative,
                    "assert_path",
                    new=fail_after_primary_rename,
                ),
                self.assertRaisesRegex(
                    VaultPathSafetyError,
                    "owned Vault parent moved",
                ),
            ):
                filesystem.atomic_replace_owned(
                    "staging/managed.tmp",
                    "Literature/note.md",
                )

            self.assertTrue(primary_completed)
            self.assertTrue(failed_postcheck)
            self.assertEqual(note.read_bytes(), b"old")
            self.assertEqual(staged.read_bytes(), b"new")
            self.assertEqual([path.name for path in literature.iterdir()], ["note.md"])

    def test_posix_replace_compensates_after_postcheck_failure(self) -> None:
        metadata = SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
        assertions = [
            None,
            None,
            None,
            VaultPathSafetyError(
                "Literature/note.md",
                "owned Vault parent moved during I/O: Literature/note.md",
            ),
        ]
        replace = mock.Mock()
        link = mock.Mock()
        unlink = mock.Mock()

        with (
            mock.patch.object(
                filesystem_module,
                "_open_posix_directory_chain",
                side_effect=[10, 20],
            ),
            mock.patch.object(
                filesystem_module,
                "_assert_posix_path",
                side_effect=assertions,
            ),
            mock.patch.object(filesystem_module.os, "stat", return_value=metadata),
            mock.patch.object(filesystem_module.os, "link", link),
            mock.patch.object(filesystem_module.os, "replace", replace),
            mock.patch.object(filesystem_module.os, "unlink", unlink),
            mock.patch.object(filesystem_module.os, "fsync"),
            mock.patch.object(filesystem_module.os, "close"),
            self.assertRaisesRegex(
                VaultPathSafetyError,
                "owned Vault parent moved",
            ),
        ):
            filesystem_module._posix_replace_relative(
                Path("/vault"),
                "staging/managed.tmp",
                "Literature/note.md",
            )

        rollback_name = link.call_args.args[1]
        self.assertRegex(rollback_name, r"^\.ovm-[0-9a-f]{32}\.rollback$")
        self.assertEqual(
            replace.call_args_list,
            [
                mock.call(
                    "managed.tmp",
                    "note.md",
                    src_dir_fd=10,
                    dst_dir_fd=20,
                ),
                mock.call(
                    "note.md",
                    "managed.tmp",
                    src_dir_fd=20,
                    dst_dir_fd=10,
                ),
                mock.call(
                    rollback_name,
                    "note.md",
                    src_dir_fd=20,
                    dst_dir_fd=20,
                ),
            ],
        )
        unlink.assert_not_called()

    def test_posix_unlink_compensates_after_postcheck_failure(self) -> None:
        metadata = SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
        moved = VaultPathSafetyError(
            "Literature/note.md",
            "owned Vault parent moved during I/O: Literature/note.md",
        )
        link = mock.Mock()
        unlink = mock.Mock()

        with (
            mock.patch.object(
                filesystem_module,
                "_open_posix_directory_chain",
                return_value=10,
            ),
            mock.patch.object(
                filesystem_module,
                "_assert_posix_path",
                side_effect=[None, moved],
            ),
            mock.patch.object(filesystem_module.os, "stat", return_value=metadata),
            mock.patch.object(filesystem_module.os, "link", link),
            mock.patch.object(filesystem_module.os, "unlink", unlink),
            mock.patch.object(filesystem_module.os, "fsync"),
            mock.patch.object(filesystem_module.os, "close"),
            self.assertRaisesRegex(
                VaultPathSafetyError,
                "owned Vault parent moved",
            ),
        ):
            filesystem_module._posix_unlink_relative(
                Path("/vault"),
                "Literature/note.md",
                missing_ok=False,
            )

        rollback_name = link.call_args_list[0].args[1]
        self.assertRegex(rollback_name, r"^\.ovm-[0-9a-f]{32}\.rollback$")
        self.assertEqual(
            link.call_args_list,
            [
                mock.call(
                    "note.md",
                    rollback_name,
                    src_dir_fd=10,
                    dst_dir_fd=10,
                    follow_symlinks=False,
                ),
                mock.call(
                    rollback_name,
                    "note.md",
                    src_dir_fd=10,
                    dst_dir_fd=10,
                    follow_symlinks=False,
                ),
            ],
        )
        self.assertEqual(
            unlink.call_args_list,
            [
                mock.call("note.md", dir_fd=10),
                mock.call(rollback_name, dir_fd=10),
            ],
        )

    def test_posix_rmdir_recreates_directory_after_postcheck_failure(self) -> None:
        metadata = SimpleNamespace(st_mode=stat.S_IFDIR | 0o750)
        moved = VaultPathSafetyError(
            "Literature/empty",
            "owned Vault parent moved during I/O: Literature/empty",
        )
        mkdir = mock.Mock()

        with (
            mock.patch.object(
                filesystem_module,
                "_open_posix_directory_chain",
                return_value=10,
            ),
            mock.patch.object(
                filesystem_module,
                "_assert_posix_path",
                side_effect=[None, moved],
            ),
            mock.patch.object(filesystem_module.os, "stat", return_value=metadata),
            mock.patch.object(filesystem_module.os, "rmdir") as rmdir,
            mock.patch.object(filesystem_module.os, "mkdir", mkdir),
            mock.patch.object(filesystem_module.os, "fsync"),
            mock.patch.object(filesystem_module.os, "close"),
            self.assertRaisesRegex(
                VaultPathSafetyError,
                "owned Vault parent moved",
            ),
        ):
            filesystem_module._posix_rmdir_relative(
                Path("/vault"),
                "Literature/empty",
                missing_ok=False,
            )

        rmdir.assert_called_once_with("empty", dir_fd=10)
        mkdir.assert_called_once_with("empty", 0o750, dir_fd=10)


if __name__ == "__main__":
    unittest.main()
