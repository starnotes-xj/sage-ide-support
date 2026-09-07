import json
import tempfile
import unittest
from pathlib import Path

from apply_source_contracts import _valid_annotation, apply
from infer_source_returns import (
    _index_class_aliases,
    _index_constant_types,
    _index_contracts,
    _index_classes,
    _index_overloads,
    _index_parameter_contracts,
    infer,
)


class SourceContractTest(unittest.TestCase):
    def test_relative_imports_resolve_against_module_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sage"
            package = root / "pkg"
            package.mkdir(parents=True)
            (root / "__init__.py").write_text("", encoding="utf-8")
            (package / "__init__.py").write_text(
                "from .helpers import Thing\n\ndef package_make():\n    return Thing()\n",
                encoding="utf-8",
            )
            (package / "helpers.py").write_text(
                "class Thing:\n    pass\n",
                encoding="utf-8",
            )
            (package / "factory.py").write_text(
                "from .helpers import Thing\n\ndef make():\n    return Thing()\n",
                encoding="utf-8",
            )
            (package / "local_factory.py").write_text(
                "def make():\n    from .helpers import Thing\n    return Thing()\n",
                encoding="utf-8",
            )
            contracts = infer(root)
            self.assertEqual(contracts["sage.pkg.package_make"], "'sage.pkg.helpers.Thing'")
            self.assertEqual(contracts["sage.pkg.factory.make"], "'sage.pkg.helpers.Thing'")
            self.assertEqual(contracts["sage.pkg.local_factory.make"], "'sage.pkg.helpers.Thing'")

    def test_imported_module_constant_attribute_uses_exact_value_class(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sage"
            root.mkdir()
            (root / "__init__.py").write_text(
                "import sage.constants as constants\n\ndef value():\n    return constants.ZZ\n",
                encoding="utf-8",
            )
            contracts = infer(
                root,
                known_constants={"sage.constants.ZZ": "sage.rings.integer_ring.IntegerRing_class"},
            )
            self.assertEqual(contracts["sage.value"], "'sage.rings.integer_ring.IntegerRing_class'")

    def test_index_overload_union_is_available_to_source_wrappers(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "index.json"
            index.write_text(
                json.dumps(
                    {
                        "entries": [
                            {"qualifiedName": "sage.a.First", "kind": "CLASS"},
                            {"qualifiedName": "sage.b.Second", "kind": "CLASS"},
                            {
                                "qualifiedName": "sage.factory.make",
                                "kind": "FUNCTION",
                                "signatures": [
                                    {"returnType": {"state": "KNOWN", "expression": "sage.a.First"}},
                                    {"returnType": {"state": "KNOWN", "expression": "sage.b.Second"}},
                                ],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                _index_contracts(index)["sage.factory.make"],
                "'sage.a.First' | 'sage.b.Second'",
            )

    def test_index_parameter_contracts_bind_unannotated_source_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "index.json"
            index.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "qualifiedName": "sage.external.echo",
                                "kind": "FUNCTION",
                                "signatures": [
                                    {
                                        "parameters": [
                                            {"name": "value", "type": {"state": "KNOWN", "expression": "int"}}
                                        ],
                                        "returnType": {"state": "UNKNOWN"},
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(_index_parameter_contracts(index), {"sage.external.echo": ("int",)})

    def test_wildcard_reexport_alias_resolves_exact_callable_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sage"
            root.mkdir()
            (root / "__init__.py").write_text(
                "from sage.all import *\n\ndef make():\n    return matrix([])\n",
                encoding="utf-8",
            )
            index = Path(directory) / "index.json"
            index.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "qualifiedName": "sage.matrix.matrix2.Matrix",
                                "kind": "CLASS",
                            },
                            {
                                "qualifiedName": "sage.all.matrix",
                                "kind": "FUNCTION",
                                "signatures": [
                                    {
                                        "returnType": {
                                            "state": "KNOWN",
                                            "expression": "sage.matrix.matrix2.Matrix",
                                        }
                                    }
                                ],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            aliases = _index_class_aliases(index)
            contracts = infer(root, known_contracts=_index_contracts(index), known_classes={"sage.matrix.matrix2.Matrix"}, class_aliases=aliases)
            self.assertEqual(contracts["sage.make"], "'sage.matrix.matrix2.Matrix'")

    def test_callable_parent_constant_uses_indexed_call_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sage"
            root.mkdir()
            (root / "__init__.py").write_text(
                "from sage.all import *\n\ndef make():\n    return ZZ(1)\n",
                encoding="utf-8",
            )
            index = Path(directory) / "index.json"
            index.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "qualifiedName": "sage.rings.integer_ring.IntegerRing_class",
                                "kind": "CLASS",
                                "parents": [],
                            },
                            {
                                "qualifiedName": "sage.rings.integer.Integer",
                                "kind": "CLASS",
                                "parents": [],
                            },
                            {
                                "qualifiedName": "sage.rings.integer_ring.IntegerRing_class.__call__",
                                "kind": "METHOD",
                                "signatures": [
                                    {
                                        "returnType": {
                                            "state": "KNOWN",
                                            "expression": "sage.rings.integer.Integer",
                                        }
                                    }
                                ],
                            },
                            {
                                "qualifiedName": "sage.all.ZZ",
                                "kind": "CONSTANT",
                                "valueType": {
                                    "state": "KNOWN",
                                    "expression": "sage.rings.integer_ring.IntegerRing_class",
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            aliases = _index_class_aliases(index)
            contracts = infer(
                root,
                known_contracts=_index_contracts(index),
                known_classes={"sage.rings.integer_ring.IntegerRing_class", "sage.rings.integer.Integer"},
                class_aliases=aliases,
            )
            self.assertEqual(contracts["sage.make"], "'sage.rings.integer.Integer'")

    def test_indexed_receiver_uses_exact_getitem_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sage"
            root.mkdir()
            (root / "__init__.py").write_text(
                "class Box:\n    def pick(self, key):\n        return self[key]\n",
                encoding="utf-8",
            )
            contracts = infer(
                root,
                known_contracts={"sage.Box.__getitem__": "int"},
            )
            self.assertEqual(contracts["sage.Box.pick"], "int")

    def test_overload_dispatch_uses_proven_argument_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sage"
            root.mkdir()
            (root / "__init__.py").write_text(
                "from sage.external import make\n\ndef choose(value: int):\n    return make(value)\n",
                encoding="utf-8",
            )
            index = Path(directory) / "index.json"
            index.write_text(
                json.dumps(
                    {
                        "entries": [
                            {"qualifiedName": "sage.a.First", "kind": "CLASS"},
                            {"qualifiedName": "sage.b.Second", "kind": "CLASS"},
                            {
                                "qualifiedName": "sage.external.make",
                                "kind": "FUNCTION",
                                "signatures": [
                                    {
                                        "parameters": [{"type": {"state": "KNOWN", "expression": "int"}}],
                                        "returnType": {"state": "KNOWN", "expression": "sage.a.First"},
                                    },
                                    {
                                        "parameters": [{"type": {"state": "KNOWN", "expression": "str"}}],
                                        "returnType": {"state": "KNOWN", "expression": "sage.b.Second"},
                                    },
                                ],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            contracts = infer(
                root,
                known_contracts=_index_contracts(index),
                known_classes=_index_classes(index),
                known_overloads=_index_overloads(index),
                known_constants=_index_constant_types(index),
            )
            self.assertEqual(contracts["sage.choose"], "'sage.a.First'")

    def test_apply_rejects_structural_base_as_final_contract(self):
        self.assertFalse(_valid_annotation("'sage.sample.Result_base'"))
        self.assertTrue(_valid_annotation("'sage.sample.Result'"))

    def test_infer_requires_a_unique_non_fallthrough_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sage"
            root.mkdir()
            (root / "__init__.py").write_text(
                """
from sage.sample import Thing
from sage.generic import generic
from sage.external import External

DEFAULT_LABEL = "sage"

def literal():
    return (1, 2)

def branch(flag):
    if flag:
        return []
    return []

def fallthrough(flag):
    if flag:
        return []

def mixed(flag):
    if flag:
        return []
    return None

def generated():
    yield 1

def generated_from(values: Iterator[int]):
    yield from values

def annotated() -> list[int]:
    return [1]

def assigned():
    value = tuple()
    return value

def wrapped():
    return literal()

def mutator():
    value = 1

def explicit_none():
    return

def explicit_none_branch(flag):
    if flag:
        return
    return

def impossible():
    raise RuntimeError()

def impossible_branch(flag):
    if flag:
        raise ValueError()
    else:
        raise TypeError()

def maybe_fails(flag):
    if flag:
        raise ValueError()

def echo(value: int):
    return value

def describe(value):
    return f"value={value}"

def builtins_result(value):
    return sorted(value)

def extended_builtins(value):
    return frozenset(value)

def scalar_arithmetic(a: int, b: int):
    return a + b

def scalar_division(a: int, b: int):
    return a / b

def scalar_compare(a: int, b: int):
    return a < b

def boolop_operand(a: int, b: int):
    return a or b

def boolop_union(a: int, b: str):
    return a or b

def boolop_predicate(a: int, b: int):
    return a < b or b < a

def typed_list_item(values: list[int], index: int):
    return values[index]

def typed_dict_item(values: dict[str, int], key: str):
    return values[key]

def typed_tuple_item(values: tuple[int, str], index: int):
    return values[index]

def typed_iterator_item(values: Iterator[int]):
    return next(values)

def typed_iterator(values: list[int]):
    return iter(values)

def typed_reverse(values: tuple[int, str]):
    return reversed(values)

def typed_filter(values: set[int]):
    return filter(bool, values)

def typed_sorted(values: list[int]):
    return sorted(values)

def typed_list(values: Iterator[int]):
    return list(values)

def typed_enumerate(values: list[int]):
    return enumerate(values)

def typed_zip(left: list[int], right: set[str]):
    return zip(left, right)

def vararg_identity(*args):
    return args

def kwarg_identity(**kwargs):
    return kwargs

def first_or_none(values: list[int]):
    for value in values:
        return value

def first_tuple_or_none(values: Iterator[tuple[int, str]]):
    for value in values:
        return value

def while_first_or_none(value: int, enabled: bool):
    while enabled:
        return value

def unsafe_loop(values: list[int]):
    for value in values:
        print(value)
        return value

def class_metadata(value):
    return value.__class__.__name__

def class_object_type(value):
    return value.__class__

def unpacked_value():
    first, second = (1, "second")
    return second

def builtin_selection():
    return min(2, 3)

def builtin_reductions():
    return sum((1 for _ in range(3)))

def builtin_empty_reductions():
    return prod(())

def builtin_generator_selection():
    return max((1 for _ in range(3)))

def builtin_abs(value: complex):
    return abs(value)

def literal_string_format():
    return "value={}".format(1)

def literal_string_split():
    return "a,b".split(",")

def literal_string_join():
    return ",".join(("a", "b"))

def literal_dict_get():
    return {"answer": 42}.get("answer")

def literal_list_copy():
    return [1, 2].copy()

def copied_value(value: int):
    return copy(value)

def builtin_object(value):
    return object()

def builtin_type(value):
    return type(value)

def generic_wrapper(a: int, b: int):
    return generic(a, b)

def external_constructor():
    return External()

def external_property():
    value = External()
    return value.value

def external_echo(value):
    return value

def class_object():
    return Thing

def try_result(flag):
    try:
        if flag:
            return []
        raise ValueError()
    except ValueError:
        return []

def with_result():
    with context_manager:
        return tuple()

def literal_subscript():
    return (1, "name")[1]

def literal_list_subscript():
    return ["first", "second"][0]

def literal_dict_subscript():
    return {"answer": 42}["answer"]

def module_constant():
    return DEFAULT_LABEL

class Holder:
    EMPTY = ()

    def __init__(self):
        self.items = []
        self.count = len(())

    def values(self):
        return self.items

    def size(self):
        return self.count

    def identity(self, value):
        return value is None

    def choose(self, value):
        return self.items if value else self.items

    @classmethod
    def make(cls):
        return cls()

    def class_constant(self):
        return self.EMPTY

class ParameterHolder:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

class Element:
    def normalize(self, value):
        return self.parent()(value)

    def maybe_normalize(self, value):
        return self.parent()(value) if value is not None else None

class Parent:
    def element(self, value):
        return self.parent()(value)

class TypedElement:
    def clone(self, value):
        return type(self)(value)

class Nested:
    def value(self):
        return 7

class Container:
    def __init__(self):
        self.child = Nested()

    def child_value(self):
        return self.child.value()

    def child_alias_value(self):
        child = self.child
        return child.value()

class CallableContainer:
    def __call__(self, value: int):
        return value

    def invoke(self, value):
        return self(value)

class NestedFactory:
    def child(self):
        return Nested()

    def child_value(self):
        return self.child().value()

class Result:
    pass

class ClassIdentity:
    @classmethod
    def identity(cls):
        return cls

class AttributeBase:
    Result = Result

class AttributeChild(AttributeBase):
    def inherited_class_attribute(self):
        return self.Result

class MethodBase:
    def helper(self):
        return []

class MethodChild(MethodBase):
    def wrapped(self):
        return self.helper()

class ExternalMethodBase:
    pass

class ExternalMethodChild(ExternalMethodBase):
    def wrapped(self):
        return self.helper()

class PropertyBase:
    @property
    def value(self):
        return 7

class PropertyChild(PropertyBase):
    def wrapped(self):
        return self.value

class SuperChild(MethodBase):
    def wrapped(self):
        return super().helper()

class BaseFactory:
    pass

class DerivedFactory(BaseFactory):
    def make_base(self):
        return self.__class__.__base__()

class ClassCallChild(MethodBase):
    @classmethod
    def make(cls, value):
        return super().__classcall__(cls, value)

class DirectClassCall:
    @staticmethod
    def __classcall_private__(cls, value):
        return cls.__classcall__(cls, value)

class Factory:
    Result = Result

    def make(self, value):
        return self.Result(value)
""",
                encoding="utf-8",
            )
            (root / "sample.py").write_text(
                """
class Thing:
    pass

def make():
    return Thing()
""",
                encoding="utf-8",
            )
            contracts = infer(
                root,
                known_contracts={"sage.ExternalMethodBase.helper": "int"},
                generic_contracts={"sage.generic.generic": ("T", (0, 1))},
                known_classes={"sage.external.External"},
                known_properties={"sage.external.External.value": "int"},
                # The indexed constructor parameter also feeds class
                # attribute propagation, so a later getter can stay exact.
                known_parameters={
                    "sage.external_echo": ("int",),
                    "sage.ParameterHolder.__init__": ("int",),
                },
            )
            self.assertEqual(contracts["sage.literal"], "tuple")
            self.assertEqual(contracts["sage.branch"], "list")
            self.assertEqual(contracts["sage.generated"], "Iterator[int]")
            self.assertEqual(contracts["sage.generated_from"], "Iterator[int]")
            self.assertEqual(contracts["sage.annotated"], "list[int]")
            self.assertEqual(contracts["sage.assigned"], "tuple")
            self.assertEqual(contracts["sage.wrapped"], "tuple")
            self.assertEqual(contracts["sage.mutator"], "None")
            self.assertEqual(contracts["sage.explicit_none"], "None")
            self.assertEqual(contracts["sage.explicit_none_branch"], "None")
            self.assertEqual(contracts["sage.impossible"], "NoReturn")
            self.assertEqual(contracts["sage.impossible_branch"], "NoReturn")
            self.assertEqual(contracts["sage.maybe_fails"], "None")
            self.assertEqual(contracts["sage.echo"], "int")
            self.assertEqual(contracts["sage.describe"], "str")
            self.assertEqual(contracts["sage.builtins_result"], "list")
            self.assertEqual(contracts["sage.extended_builtins"], "frozenset")
            self.assertEqual(contracts["sage.scalar_arithmetic"], "int")
            self.assertEqual(contracts["sage.scalar_division"], "float")
            self.assertEqual(contracts["sage.scalar_compare"], "bool")
            self.assertEqual(contracts["sage.boolop_operand"], "int")
            self.assertEqual(contracts["sage.boolop_union"], "int | str")
            self.assertEqual(contracts["sage.boolop_predicate"], "bool")
            self.assertEqual(contracts["sage.typed_list_item"], "int")
            self.assertEqual(contracts["sage.typed_dict_item"], "int")
            self.assertEqual(contracts["sage.typed_tuple_item"], "int | str")
            self.assertEqual(contracts["sage.typed_iterator_item"], "int")
            self.assertEqual(contracts["sage.typed_iterator"], "Iterator[int]")
            self.assertEqual(contracts["sage.typed_reverse"], "Iterator[int | str]")
            self.assertEqual(contracts["sage.typed_filter"], "Iterator[int]")
            self.assertEqual(contracts["sage.typed_sorted"], "list[int]")
            self.assertEqual(contracts["sage.typed_list"], "list[int]")
            self.assertEqual(contracts["sage.typed_enumerate"], "Iterator[tuple[int, int]]")
            self.assertEqual(contracts["sage.typed_zip"], "Iterator[tuple[int, str]]")
            self.assertEqual(contracts["sage.ClassIdentity.identity"], "type")
            self.assertEqual(contracts["sage.vararg_identity"], "tuple")
            self.assertEqual(contracts["sage.kwarg_identity"], "dict")
            self.assertEqual(contracts["sage.first_or_none"], "int | None")
            self.assertEqual(contracts["sage.first_tuple_or_none"], "tuple[int, str] | None")
            self.assertEqual(contracts["sage.while_first_or_none"], "int | None")
            self.assertNotIn("sage.unsafe_loop", contracts)
            self.assertEqual(contracts["sage.class_metadata"], "str")
            self.assertEqual(contracts["sage.class_object_type"], "type")
            self.assertEqual(contracts["sage.unpacked_value"], "str")
            self.assertEqual(contracts["sage.builtin_selection"], "int")
            self.assertEqual(contracts["sage.builtin_reductions"], "int")
            self.assertEqual(contracts["sage.builtin_empty_reductions"], "int")
            self.assertEqual(contracts["sage.builtin_generator_selection"], "int")
            self.assertEqual(contracts["sage.builtin_abs"], "float")
            self.assertEqual(contracts["sage.literal_string_format"], "str")
            self.assertEqual(contracts["sage.literal_string_split"], "list")
            self.assertEqual(contracts["sage.literal_string_join"], "str")
            self.assertEqual(contracts["sage.literal_dict_get"], "int")
            self.assertEqual(contracts["sage.literal_list_copy"], "list")
            self.assertEqual(contracts["sage.copied_value"], "int")
            self.assertEqual(contracts["sage.builtin_object"], "object")
            self.assertEqual(contracts["sage.builtin_type"], "type")
            self.assertEqual(contracts["sage.generic_wrapper"], "int")
            self.assertEqual(contracts["sage.external_constructor"], "'sage.external.External'")
            self.assertEqual(contracts["sage.external_property"], "int")
            self.assertEqual(contracts["sage.external_echo"], "int")
            self.assertEqual(contracts["sage.class_object"], "type")
            self.assertEqual(contracts["sage.try_result"], "list")
            self.assertEqual(contracts["sage.with_result"], "tuple")
            self.assertEqual(contracts["sage.literal_subscript"], "str")
            self.assertEqual(contracts["sage.literal_list_subscript"], "str")
            self.assertEqual(contracts["sage.literal_dict_subscript"], "int")
            self.assertEqual(contracts["sage.module_constant"], "str")
            self.assertEqual(contracts["sage.Holder.values"], "list")
            self.assertEqual(contracts["sage.Holder.size"], "int")
            self.assertEqual(contracts["sage.Holder.identity"], "bool")
            self.assertEqual(contracts["sage.Holder.choose"], "list")
            self.assertEqual(contracts["sage.Holder.make"], "Self")
            self.assertEqual(contracts["sage.Holder.class_constant"], "tuple")
            self.assertEqual(contracts["sage.ParameterHolder.get"], "int")
            self.assertEqual(contracts["sage.Element.normalize"], "Self")
            self.assertEqual(contracts["sage.Element.maybe_normalize"], "Self | None")
            self.assertEqual(contracts["sage.Parent.element"], "Self")
            self.assertEqual(contracts["sage.TypedElement.clone"], "Self")
            self.assertEqual(contracts["sage.Container.child_value"], "int")
            self.assertEqual(contracts["sage.Container.child_alias_value"], "int")
            self.assertEqual(contracts["sage.CallableContainer.__call__"], "int")
            self.assertEqual(contracts["sage.CallableContainer.invoke"], "int")
            self.assertEqual(contracts["sage.NestedFactory.child_value"], "int")
            # An explicitly assigned class object is a proven constructor;
            # arbitrary parent/factory attributes remain unresolved.
            self.assertEqual(contracts["sage.Factory.make"], "'sage.Result'")
            self.assertEqual(contracts["sage.AttributeChild.inherited_class_attribute"], "type")
            self.assertEqual(contracts["sage.MethodChild.wrapped"], "list")
            self.assertEqual(contracts["sage.ExternalMethodChild.wrapped"], "int")
            self.assertEqual(contracts["sage.PropertyChild.wrapped"], "int")
            self.assertEqual(contracts["sage.SuperChild.wrapped"], "list")
            self.assertEqual(contracts["sage.DerivedFactory.make_base"], "'sage.BaseFactory'")
            self.assertEqual(contracts["sage.ClassCallChild.make"], "Self")
            self.assertEqual(contracts["sage.DirectClassCall.__classcall_private__"], "Self")
            self.assertEqual(contracts["sage.sample.make"], "'sage.sample.Thing'")
            self.assertEqual(contracts["sage.fallthrough"], "list | None")
            self.assertEqual(contracts["sage.mixed"], "list | None")

    def test_apply_is_idempotent_and_only_targets_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "stubs"
            module = root / "sage"
            module.mkdir(parents=True)
            stub = module / "sample.pyi"
            stub.write_text(
                """class Thing: ...
def literal(): ...
def already() -> str: ...
def skipped(): ...
class Holder:
    @property
    def value(self): ...
""",
                encoding="utf-8",
            )
            contracts = {
                "sage.sample.literal": "tuple",
                "sage.sample.already": "int",
                "sage.sample.skipped": "list",
                "sage.sample.Holder.value": "int",
            }
            index = root / "index.json"
            index.write_text(
                json.dumps(
                    {
                        "entries": [
                            {"qualifiedName": "sage.sample.literal", "kind": "FUNCTION", "signatures": [{"returnType": {"state": "UNKNOWN"}}]},
                            {"qualifiedName": "sage.sample.already", "kind": "FUNCTION", "signatures": [{"returnType": {"state": "KNOWN"}}]},
                            {"qualifiedName": "sage.sample.Holder.value", "kind": "PROPERTY", "signatures": [{"returnType": {"state": "UNKNOWN"}}]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            changed = apply(root, contracts, index)
            self.assertEqual(changed, ["sage.sample.literal", "sage.sample.Holder.value"])
            self.assertIn("def literal() -> tuple:", stub.read_text(encoding="utf-8"))
            self.assertIn("def value(self) -> int:", stub.read_text(encoding="utf-8"))
            self.assertEqual(apply(root, contracts, index), [])

    def test_apply_accepts_proven_exact_union_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "stubs"
            module = root / "sage"
            module.mkdir(parents=True)
            stub = module / "sample.pyi"
            stub.write_text("def choose(flag): ...\n", encoding="utf-8")
            index = root / "index.json"
            index.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "qualifiedName": "sage.sample.choose",
                                "kind": "FUNCTION",
                                "signatures": [{"returnType": {"state": "UNKNOWN"}}],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            changed = apply(root, {"sage.sample.choose": "list | 'sage.sample.Result'"}, index)
            self.assertEqual(changed, ["sage.sample.choose"])
            self.assertIn("def choose(flag) -> list | 'sage.sample.Result':", stub.read_text(encoding="utf-8"))

            stub.write_text("def maybe(flag): ...\n", encoding="utf-8")
            index.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "qualifiedName": "sage.sample.maybe",
                                "kind": "FUNCTION",
                                "signatures": [{"returnType": {"state": "UNKNOWN"}}],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            changed = apply(root, {"sage.sample.maybe": "None | tuple"}, index)
            self.assertEqual(changed, ["sage.sample.maybe"])
            self.assertIn("def maybe(flag) -> None | tuple:", stub.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
