from __future__ import annotations

import unittest

from sql_safety import validate_read_only_sql


class ValidateReadOnlySQLTests(unittest.TestCase):
    def test_accepts_select_and_removes_trailing_semicolon(self) -> None:
        self.assertEqual(
            validate_read_only_sql("  SELECT * FROM suppliers;  "),
            "SELECT * FROM suppliers",
        )

    def test_accepts_read_only_statement_prefixes(self) -> None:
        for statement in (
            "SELECT 1",
            "WITH supplier_totals AS (SELECT 1) SELECT * FROM supplier_totals",
            "SHOW TABLES",
            "DESCRIBE suppliers",
            "PRAGMA table_info('suppliers')",
        ):
            with self.subTest(statement=statement):
                self.assertEqual(validate_read_only_sql(statement), statement)

    def test_rejects_empty_sql(self) -> None:
        for statement in ("", "  ", None):
            with self.subTest(statement=statement):
                with self.assertRaisesRegex(ValueError, "SQL is empty"):
                    validate_read_only_sql(statement)

    def test_rejects_non_read_only_statement_prefix(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only read-only SQL is allowed"):
            validate_read_only_sql("DROP TABLE suppliers")

    def test_rejects_forbidden_keywords(self) -> None:
        for keyword in (
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "ALTER",
            "CREATE",
            "REPLACE",
            "TRUNCATE",
            "ATTACH",
            "DETACH",
            "COPY",
            "CALL",
        ):
            with self.subTest(keyword=keyword):
                with self.assertRaisesRegex(ValueError, "Forbidden SQL keywords"):
                    validate_read_only_sql(f"SELECT {keyword} FROM suppliers")

    def test_rejects_stacked_statements(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only one SQL statement is allowed"):
            validate_read_only_sql("SELECT 1; SELECT 2")

    def test_allow_multiple_does_not_allow_forbidden_statements(self) -> None:
        self.assertEqual(
            validate_read_only_sql("SELECT 1; SELECT 2", allow_multiple=True),
            "SELECT 1; SELECT 2",
        )
        with self.assertRaisesRegex(ValueError, "Forbidden SQL keywords"):
            validate_read_only_sql(
                "SELECT 1; DROP TABLE suppliers",
                allow_multiple=True,
            )

    def test_rejects_semicolon_inside_a_statement(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only one SQL statement is allowed"):
            validate_read_only_sql("SELECT ';' AS punctuation")


if __name__ == "__main__":
    unittest.main()
