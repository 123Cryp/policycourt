import ast
import io
import os
import re
import tokenize
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class ContractFileTests(unittest.TestCase):
    def setUp(self):
        self.source = read("contract.py")

    def test_two_header_lines_then_code(self):
        lines = self.source.splitlines()
        self.assertEqual(lines[0], "# v0.2.16")
        self.assertTrue(lines[1].startswith('# { "Depends": "py-genlayer:'))
        self.assertFalse(lines[2].startswith("#"))

    def test_no_comments_or_docstrings_after_header(self):
        for tok in tokenize.generate_tokens(io.StringIO(self.source).readline):
            if tok.type == tokenize.COMMENT:
                self.assertLessEqual(tok.start[0], 2, f"comment on line {tok.start[0]}")
        for node in ast.walk(ast.parse(self.source)):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                self.assertIsNone(ast.get_docstring(node), getattr(node, "name", "module"))

    def test_decorators_cover_every_public_method(self):
        tree = ast.parse(self.source)
        cls = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PolicyCourt"][0]
        for fn in cls.body:
            if isinstance(fn, ast.FunctionDef) and not fn.name.startswith("_") and fn.name != "__init__":
                self.assertTrue(fn.decorator_list, fn.name)

    def test_no_persian_in_any_deliverable(self):
        persian = re.compile("[؀-ۿ]")
        for name in ["contract.py", "index.html", "README.md", "SECURITY_REVIEW.md"]:
            if os.path.exists(os.path.join(ROOT, name)):
                self.assertIsNone(persian.search(read(name)), name)


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.html = read("index.html")

    def test_every_contract_call_exists_in_the_contract(self):
        contract = read("contract.py")
        defined = set(re.findall(r"def ([a-z_]+)\(", contract))
        reads = set(re.findall(r'view\("([a-z_]+)"', self.html))
        writes = set(re.findall(r'fn: "([a-z_]+)"', self.html))
        self.assertGreaterEqual(len(reads), 10)
        self.assertGreaterEqual(len(writes), 12)
        self.assertEqual((reads | writes) - defined, set())

    def test_every_write_method_is_reachable_from_the_ui(self):
        contract = read("contract.py")
        writes = set(re.findall(r"@gl\.public\.write(?:\.payable)?\n    def ([a-z_]+)\(", contract))
        used = set(re.findall(r'fn: "([a-z_]+)"', self.html))
        self.assertEqual(writes - used, set())

    def test_transactions_need_confirmation_and_block_duplicates(self):
        self.assertIn("confirmTx(", self.html)
        self.assertIn("if (busy.has(key)) return null;", self.html)
        self.assertIn('status: "FINALIZED"', self.html)

    def test_accessibility_basics(self):
        for needle in ['class="skip"', 'aria-live="polite"', "prefers-reduced-motion", "showModal()", "aria-invalid", ":focus-visible"]:
            self.assertIn(needle, self.html)

    def test_every_action_the_contract_can_offer_has_a_button(self):
        contract = read("contract.py")
        offered = set(re.findall(r'actions\.append\("([a-z_]+)"\)', contract))
        for name in offered - {"file_appeal"}:
            self.assertIn(name, self.html, name)
        self.assertIn("file_appeal", self.html)

    def test_contract_data_is_never_injected_as_html(self):
        self.assertNotIn("innerHTML", self.html)
        self.assertNotIn("insertAdjacentHTML", self.html)

    def test_no_private_key_persistence(self):
        self.assertNotIn("localStorage.setItem(\"policycourt.key", self.html)

    def test_tabular_numbers_are_not_page_wide(self):
        body_rule = re.search(r"\nbody\{[^}]*\}", self.html).group(0)
        self.assertNotIn("tnum", body_rule)
        self.assertNotIn("tabular-nums", body_rule)
        self.assertIn("text-size-adjust:100%", self.html)
        self.assertNotIn('type="date"', self.html)

    def test_mobile_and_dark_mode(self):
        self.assertIn("viewport-fit=cover", self.html)
        self.assertIn("prefers-color-scheme: dark", self.html)


if __name__ == "__main__":
    unittest.main()
