import tempfile
import unittest
from pathlib import Path

from app import _archive_destination, _safe_folder_name
from models import get_db, init_db, search_doujinshi
from scan import _migrate_missing_entry


def _insert_item(conn, filepath, filename="Duplicate.zip", event=None, title="Title"):
    cur = conn.execute(
        """INSERT INTO doujinshi
           (filename, filepath, folder, event, circle, author, title, parody, is_dl, category, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (filename, str(filepath), "folder", event, None, None, title, None, 0, "doujin", "archive"),
    )
    conn.commit()
    return cur.lastrowid


class ArchiveDestinationTests(unittest.TestCase):
    def test_archive_destination_sanitizes_event_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "archive"
            folder, dest = _archive_destination(str(root), r"..\outside/name:", "book.zip")

            self.assertEqual(folder, "_outside_name_")
            self.assertEqual(dest.name, "book.zip")
            self.assertTrue(dest.parent.is_relative_to(root.resolve()))

    def test_safe_folder_name_handles_reserved_and_empty_names(self):
        self.assertEqual(_safe_folder_name("CON"), "CON_")
        self.assertEqual(_safe_folder_name("   "), "未分類")


class SearchTests(unittest.TestCase):
    def test_search_ignores_bare_quote_query_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = get_db(Path(tmp) / "test.db")
            try:
                init_db(conn)
                _insert_item(conn, Path(tmp) / "book.zip")

                result = search_doujinshi(conn, query='"', per_page=5)

                self.assertEqual(result["total"], 1)
            finally:
                conn.close()

    def test_search_escapes_embedded_quote_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = get_db(Path(tmp) / "test.db")
            try:
                init_db(conn)
                _insert_item(conn, Path(tmp) / "book.zip", title='foo"bar')

                result = search_doujinshi(conn, query='foo"bar', per_page=5)

                self.assertIn("total", result)
            finally:
                conn.close()


class ScanMigrationTests(unittest.TestCase):
    def test_missing_entry_migrates_only_to_unique_existing_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            conn = get_db(tmp_path / "test.db")
            try:
                init_db(conn)
                old_id = _insert_item(conn, tmp_path / "missing.zip", event="OldEvent")
                conn.execute("INSERT INTO tags (name) VALUES (?)", ("keep",))
                tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", ("keep",)).fetchone()[0]
                conn.execute(
                    "INSERT INTO doujinshi_tags (doujinshi_id, tag_id) VALUES (?, ?)",
                    (old_id, tag_id),
                )

                new_file = tmp_path / "new" / "Duplicate.zip"
                new_file.parent.mkdir()
                new_file.write_text("x", encoding="utf-8")
                new_id = _insert_item(conn, new_file, event="NewEvent")

                migrated, ambiguous = _migrate_missing_entry(conn, old_id, "Duplicate.zip", set())

                self.assertTrue(migrated)
                self.assertFalse(ambiguous)
                new_row = conn.execute("SELECT event FROM doujinshi WHERE id = ?", (new_id,)).fetchone()
                self.assertEqual(new_row["event"], "OldEvent")
                link = conn.execute(
                    "SELECT 1 FROM doujinshi_tags WHERE doujinshi_id = ? AND tag_id = ?",
                    (new_id, tag_id),
                ).fetchone()
                self.assertIsNotNone(link)
            finally:
                conn.close()

    def test_missing_entry_skips_ambiguous_replacements(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            conn = get_db(tmp_path / "test.db")
            try:
                init_db(conn)
                old_id = _insert_item(conn, tmp_path / "missing.zip", event="OldEvent")

                first = tmp_path / "a" / "Duplicate.zip"
                second = tmp_path / "b" / "Duplicate.zip"
                first.parent.mkdir()
                second.parent.mkdir()
                first.write_text("x", encoding="utf-8")
                second.write_text("x", encoding="utf-8")
                first_id = _insert_item(conn, first, event="First")
                second_id = _insert_item(conn, second, event="Second")

                migrated, ambiguous = _migrate_missing_entry(conn, old_id, "Duplicate.zip", set())

                self.assertFalse(migrated)
                self.assertTrue(ambiguous)
                rows = conn.execute(
                    "SELECT id, event FROM doujinshi WHERE id IN (?, ?) ORDER BY id",
                    (first_id, second_id),
                ).fetchall()
                self.assertEqual([r["event"] for r in rows], ["First", "Second"])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
