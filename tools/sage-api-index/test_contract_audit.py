import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_contracts


ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "audit_contracts.py"


class ContractAuditTest(unittest.TestCase):
    def test_classification_is_conservative_and_typevar_aware(self):
        self.assertEqual("UNKNOWN", audit_contracts.classify_return({"state": "UNKNOWN", "expression": None}))
        self.assertEqual("DYNAMIC", audit_contracts.classify_return({"state": "DYNAMIC", "expression": None}))
        self.assertEqual("BROAD_BUILTIN", audit_contracts.classify_return({"state": "KNOWN", "expression": "list"}))
        self.assertEqual("STRUCTURAL_BASE", audit_contracts.classify_return({"state": "KNOWN", "expression": "sage.foo.Foo_generic"}))
        self.assertEqual("UNION_OR_OPTIONAL", audit_contracts.classify_return({"state": "KNOWN", "expression": "'sage.foo.Foo_generic' | 'sage.foo.Foo_gap'"}))
        self.assertEqual("STRUCTURAL_BASE", audit_contracts.classify_return({"state": "KNOWN", "expression": "'sage.foo.Foo_base' | 'sage.foo.Foo_gap'"}))
        self.assertEqual("TYPE_VARIABLE", audit_contracts.classify_return({"state": "KNOWN", "expression": "T"}, [{"name": "T"}]))
        self.assertEqual("NO_RETURN", audit_contracts.classify_return({"state": "KNOWN", "expression": "NoReturn"}))
        self.assertEqual("CONCRETE", audit_contracts.classify_return({"state": "KNOWN", "expression": "sage.foo.Foo"}))
        self.assertEqual(
            "CONCRETE",
            audit_contracts.classify_return(
                {"state": "KNOWN", "expression": "sage.foo.Foo_generic"},
                structural_leaf_paths={"sage.foo.Foo_generic"},
            ),
        )

    def test_audit_uses_index_hierarchy_to_classify_structural_leaves(self):
        index = {
            "entries": [
                {
                    "qualifiedName": "sage.foo.Foo_generic",
                    "kind": "CLASS",
                    "parents": ["sage.foo.Protocol"],
                },
                {"qualifiedName": "sage.foo.Protocol", "kind": "CLASS", "parents": []},
                {
                    "qualifiedName": "sage.foo.make",
                    "kind": "FUNCTION",
                    "signatures": [
                        {
                            "returnType": {
                                "state": "KNOWN",
                                "expression": "sage.foo.Foo_generic",
                            }
                        }
                    ],
                },
            ]
        }
        report = audit_contracts.audit_index(index)
        self.assertEqual(1, report["counts"]["returnClasses"]["CONCRETE"])
        self.assertNotIn("STRUCTURAL_BASE", report["counts"]["returnClasses"])

    def test_audit_reports_callable_and_source_gaps(self):
        index = {
            "schemaVersion": 1,
            "generator": "test",
            "sageVersion": "10.9",
            "pythonVersion": "3.13",
            "entries": [
                {"qualifiedName": "sage.foo.make", "kind": "FUNCTION", "signatures": [{"parameters": [], "returnType": {"state": "KNOWN", "expression": "sage.foo.Foo"}}], "documentation": {"summary": "make"}},
                {"qualifiedName": "sage.foo.items", "kind": "METHOD", "signatures": [{"parameters": [], "returnType": {"state": "UNKNOWN", "expression": None}}]},
                {"qualifiedName": "sage.foo.dynamic", "kind": "FUNCTION", "signatures": [{"parameters": [], "returnType": {"state": "DYNAMIC", "expression": None}}]},
                {"qualifiedName": "sage.foo.CONST", "kind": "CONSTANT"},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "foo.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text("class Foo:\n    def __repr__(self): ...\n    def make(self) -> Foo: ...\n", encoding="utf-8")
            report = audit_contracts.audit_index(index, source_root=root)
            self.assertEqual(4, report["counts"]["entries"])
            self.assertEqual(3, report["counts"]["callableEntries"])
            self.assertEqual(1, report["counts"]["returnClasses"]["CONCRETE"])
            self.assertEqual(1, report["counts"]["returnClasses"]["UNKNOWN"])
            self.assertEqual(1, report["counts"]["returnClasses"]["DYNAMIC"])
            self.assertEqual(2, report["source"]["functionCount"])
            self.assertEqual(1, report["source"]["missingReturnCount"])
            self.assertEqual({"__repr__": 1}, report["source"]["missingProtocolReturns"])

    def test_cli_writes_deterministic_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = root / "index.json"
            output = root / "audit.json"
            markdown = root / "audit.md"
            index.write_text(json.dumps({"entries": [], "schemaVersion": 1}), encoding="utf-8")
            command = [sys.executable, str(AUDIT), "--index", str(index), "--output", str(output), "--markdown", str(markdown)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            first_text = output.read_text(encoding="utf-8")
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(first_text, output.read_text(encoding="utf-8"))
            self.assertIn("contract quality audit", markdown.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
