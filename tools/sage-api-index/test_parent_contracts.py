import json
import tempfile
import unittest
from pathlib import Path

from propagate_parent_contracts import apply, infer_parent_contracts


class ParentContractTest(unittest.TestCase):
    def test_nearest_unique_parent_contracts_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "index.json"
            index.write_text(
                json.dumps(
                    {
                        "entries": [
                            {"qualifiedName": "sage.sample.Base", "kind": "CLASS", "parents": []},
                            {"qualifiedName": "sage.sample.Child", "kind": "CLASS", "parents": ["sage.sample.Base"]},
                            {
                                "qualifiedName": "sage.sample.Base.ready",
                                "kind": "METHOD",
                                "signatures": [{"returnType": {"state": "KNOWN", "expression": "bool"}}],
                            },
                            {
                                "qualifiedName": "sage.sample.Child.ready",
                                "kind": "METHOD",
                                "signatures": [{"returnType": {"state": "UNKNOWN", "expression": None}}],
                            },
                            {
                                "qualifiedName": "sage.sample.Base.selfish",
                                "kind": "METHOD",
                                "signatures": [{"returnType": {"state": "KNOWN", "expression": "typing.Self"}}],
                            },
                            {
                                "qualifiedName": "sage.sample.Child.selfish",
                                "kind": "METHOD",
                                "signatures": [{"returnType": {"state": "UNKNOWN", "expression": None}}],
                            },
                            {
                                "qualifiedName": "sage.sample.Base.broad",
                                "kind": "METHOD",
                                "signatures": [{
                                    "returnType": {
                                        "state": "KNOWN",
                                        "expression": "sage.structure.element.Element",
                                    }
                                }],
                            },
                            {
                                "qualifiedName": "sage.sample.Child.broad",
                                "kind": "METHOD",
                                "signatures": [{"returnType": {"state": "UNKNOWN", "expression": None}}],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            contracts = infer_parent_contracts(index)
            self.assertEqual(contracts["sage.sample.Child.ready"], "bool")
            self.assertEqual(contracts["sage.sample.Child.selfish"], "typing.Self")
            self.assertNotIn("sage.sample.Child.broad", contracts)

            stub_root = root / "stubs" / "sage"
            stub_root.mkdir(parents=True)
            stub = stub_root / "sample.pyi"
            stub.write_text(
                "class Base:\n    def ready(self): ...\n    def selfish(self): ...\n\n"
                "class Child(Base):\n    def ready(self): ...\n    def selfish(self): ...\n    def broad(self): ...\n",
                encoding="utf-8",
            )
            changed = apply(stub_root.parent, contracts)
            self.assertEqual(changed, ["sage.sample.Child.ready", "sage.sample.Child.selfish"])
            text = stub.read_text(encoding="utf-8")
            self.assertIn("def ready(self) -> bool:", text)
            self.assertIn("def selfish(self) -> Self:", text)
            self.assertNotIn("def broad(self) ->", text)
            self.assertEqual(apply(stub_root.parent, contracts), [])


if __name__ == "__main__":
    unittest.main()
