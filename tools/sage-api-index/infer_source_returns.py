#!/usr/bin/env python3
"""Infer conservative return contracts from pure-Python Sage sources.

This is deliberately syntax/data driven rather than a method allow-list.  A
contract is emitted only when every reachable explicit return has the same
small, unambiguous shape and the function cannot fall through implicitly.
The output is consumed by :mod:`apply_source_contracts` against the generated
``.pyi`` tree.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Iterable


BUILTIN_CALLS = {
    "all": "bool",
    "any": "bool",
    "ascii": "str",
    "bool": "bool",
    "bin": "str",
    "bytes": "bytes",
    "bytearray": "bytearray",
    "callable": "bool",
    "complex": "complex",
    "dict": "dict",
    "divmod": "tuple",
    "enumerate": "Iterator",
    "filter": "Iterator",
    "float": "float",
    "frozenset": "frozenset",
    "format": "str",
    "hash": "int",
    "hex": "str",
    "int": "int",
    "iter": "Iterator",
    "id": "int",
    "isinstance": "bool",
    "issubclass": "bool",
    "len": "int",
    "list": "list",
    "map": "Iterator",
    "memoryview": "memoryview",
    "oct": "str",
    "object": "object",
    "ord": "int",
    "repr": "str",
    "range": "range",
    "reversed": "Iterator",
    "sorted": "list",
    "set": "set",
    "slice": "slice",
    "str": "str",
    "tuple": "tuple",
    "type": "type",
    "zip": "Iterator",
}


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    module = ".".join(parts)
    # The Sage installation is commonly passed either as ``site-packages``
    # or directly as its ``.../site-packages/sage`` directory.  Preserve the
    # package prefix in the latter form so contracts match generated stubs.
    if root.name == "sage":
        return "sage" if not module else f"sage.{module}"
    return module


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _quote(path: str) -> str:
    return f"'{path}'"


def _union(*values: str) -> str:
    """Build a deterministic, duplicate-free PEP 604 union expression."""
    arms: list[str] = []
    for value in values:
        for arm in value.split(" | "):
            if arm not in arms:
                arms.append(arm)
    return " | ".join(arms)


def _generic_parts(value: str) -> tuple[str, tuple[str, ...]] | None:
    """Split a normalized builtin generic expression structurally."""
    opening = value.find("[")
    if opening <= 0 or not value.endswith("]"):
        return None
    base = value[:opening]
    body = value[opening + 1 : -1]
    if not body:
        return None
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for position, character in enumerate(body):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth < 0:
                return None
        elif character == "," and depth == 0:
            part = body[start:position].strip()
            if not part:
                return None
            parts.append(part)
            start = position + 1
    if quote is not None or depth != 0:
        return None
    part = body[start:].strip()
    if not part:
        return None
    parts.append(part)
    return base, tuple(parts)


def _generic_element(value: str | None) -> str | None:
    """Return the element type of a proven builtin iterable."""
    if value is None:
        return None
    generic = _generic_parts(value)
    if generic is None:
        return None
    base, arguments = generic
    if base in {"list", "set", "frozenset", "Iterator"} and len(arguments) == 1:
        return arguments[0]
    if base == "dict" and len(arguments) == 2:
        return arguments[0]
    if base == "tuple" and arguments:
        finite = [argument for argument in arguments if argument != "..."]
        return _union(*finite) if finite else None
    return None


_CLASS_OBJECT_PREFIX = "@class:"
_FACTORY_RESULT_PREFIX = "@factory:"
_PARENT_ELEMENT_OWNERS_CACHE: dict[int, set[str]] = {}
_STRUCTURAL_SUFFIXES = ("_base", "_generic", "_element", "_parent", "_factory")


def _is_final_class_path(value: str) -> bool:
    if not value.startswith("sage."):
        return False
    final = value.rsplit(".", 1)[-1].lower()
    return not any(final.endswith(suffix) for suffix in _STRUCTURAL_SUFFIXES)


def _safe_factory_result(expression: str | None) -> str | None:
    """Filter a factory ``create_object`` contract to usable result arms.

    UniqueFactory implementations commonly document a union containing both
    concrete backends and a public ``*_generic``/``*_base`` protocol class.
    The latter is useful for inheritance lookup but is not an accurate IDE
    result type.  Keep only builtins and final Sage class paths, preserving a
    finite union when several implementations are genuinely possible.
    """
    if not isinstance(expression, str):
        return None
    builtins = {
        "None", "NoReturn", "Self", "Iterator", "bool", "bytes", "bytearray",
        "complex", "dict", "float", "frozenset", "int", "list", "memoryview",
        "object", "range", "set", "slice", "str", "tuple", "type",
    }
    safe: list[str] = []
    for arm in expression.split(" | "):
        arm = arm.strip()
        if arm in builtins:
            safe.append(arm)
            continue
        if arm.startswith("'") and arm.endswith("'"):
            path = arm[1:-1]
        else:
            path = arm
        if path.startswith("sage.") and _is_final_class_path(path):
            safe.append(_quote(path))
    unique = list(dict.fromkeys(safe))
    return _union(*unique) if unique else None


def _public_type(value: str | None) -> str | None:
    """Hide internal class-object markers from published return contracts."""
    if value is None:
        return None
    # Factory-instance markers are an internal bridge used while following a
    # module-level ``F = Factory(...)`` assignment.  They describe the value
    # produced by calling ``F`` rather than a public return type of the
    # assignment itself; leaking the marker would make the generated index
    # unparsable and would overstate a dynamic factory object as a Sage class.
    if any(arm.startswith(_FACTORY_RESULT_PREFIX) for arm in value.split(" | ")):
        return None
    arms = ["type" if arm.startswith(_CLASS_OBJECT_PREFIX) else arm for arm in value.split(" | ")]
    return _union(*arms)


def _assigned_type(node: ast.AST, analyzer: "_FunctionAnalyzer") -> str | None:
    """Infer assignments while retaining an explicit class-object marker."""
    if isinstance(node, ast.Name):
        resolved = analyzer._resolve_name(node.id)
        canonical = analyzer.class_aliases.get(resolved, resolved) if resolved else None
        if canonical and (canonical in analyzer.classes or canonical in analyzer.known_classes):
            return f"{_CLASS_OBJECT_PREFIX}{canonical}"
    # Preserve element information for materialized builtin containers when
    # they flow through a local variable.  The direct expression contract
    # remains the ordinary builtin shape, but an assignment such as
    # ``items = [1, 'x']`` can safely expose ``list[int | str]`` to a later
    # ``min/max`` or dynamic subscript without any Sage-specific heuristic.
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [analyzer.expr_type(item) for item in node.elts]
        if values and all(value is not None for value in values):
            element_types = [value for value in values if value is not None]
            base = {
                ast.List: "list",
                ast.Tuple: "tuple",
                ast.Set: "set",
            }[type(node)]
            if base == "tuple":
                return f"tuple[{', '.join(element_types)}]"
            return f"{base}[{_union(*element_types)}]"
    if isinstance(node, (ast.ListComp, ast.SetComp)):
        element = analyzer.expr_type(node.elt)
        if element is not None:
            base = "list" if isinstance(node, ast.ListComp) else "set"
            return f"{base}[{element}]"
    if isinstance(node, ast.Dict):
        keys = [analyzer.expr_type(key) for key in node.keys if key is not None]
        values = [analyzer.expr_type(value) for value in node.values]
        if values and all(value is not None for value in values):
            value_types = [value for value in values if value is not None]
            key_types = [key for key in keys if key is not None]
            if key_types and len(key_types) == len(keys):
                return f"dict[{_union(*key_types)}, {_union(*value_types)}]"
            return f"dict[object, {_union(*value_types)}]"
    return analyzer.expr_type(node)


class _FunctionAnalyzer:
    def __init__(
        self,
        module: str,
        imports: dict[str, str],
        classes: set[str],
        owner: str | None,
        class_attributes: dict[str, dict[str, str]] | None = None,
        module_globals: dict[str, str] | None = None,
        known_contracts: dict[str, str] | None = None,
        generic_contracts: dict[str, tuple[str, tuple[int, ...]]] | None = None,
        known_classes: set[str] | None = None,
        class_aliases: dict[str, str] | None = None,
        known_properties: dict[str, str] | None = None,
        known_parameters: dict[str, tuple[str | None, ...]] | None = None,
        class_bases: dict[str, tuple[str, ...]] | None = None,
        known_overloads: dict[str, tuple[tuple[tuple[str | None, ...], str], ...]] | None = None,
        known_constants: dict[str, str] | None = None,
        class_methods: set[str] | None = None,
    ):
        self.module = module
        self.imports = imports
        self.classes = classes
        self.owner = owner
        self.class_attributes = class_attributes or {}
        self.module_globals = module_globals or {}
        self.known_contracts = known_contracts or {}
        self.generic_contracts = generic_contracts or {}
        self.known_classes = known_classes or set()
        self.class_aliases = class_aliases or {}
        self.known_properties = known_properties or {}
        self.known_parameters = known_parameters or {}
        self.class_bases = class_bases or {}
        self.known_overloads = known_overloads or {}
        self.known_constants = known_constants or {}
        self.class_methods = class_methods or set()
        self.locals: dict[str, str | None] = {}

    def _parent_element_owners(self) -> set[str]:
        """Return owners with an indexed parent-element relation member.

        The cache is keyed by the mutable contract-map identity used for one
        inference pass.  This avoids rescanning the large generated index for
        every function while keeping relation evidence scoped to that pass.
        """
        key = id(self.known_contracts)
        owners = _PARENT_ELEMENT_OWNERS_CACHE.get(key)
        if owners is None:
            relation = "sage.type_contracts.ParentElement[Self]"
            owners = {
                qualified.rsplit(".", 1)[0]
                for qualified, contract in self.known_contracts.items()
                if isinstance(contract, str)
                and contract.strip("'") == relation
                and "." in qualified
            }
            _PARENT_ELEMENT_OWNERS_CACHE[key] = owners
        return owners

    def _resolve_name(self, name: str) -> str | None:
        if name in self.imports:
            return self.imports[name]
        local = f"{self.module}.{name}"
        if local in self.classes:
            return local
        if local in self.known_contracts:
            return local
        # ``from sage.all import *`` is intentionally omitted from the AST
        # import map.  The index bridge may still provide a unique, exact
        # symbol alias (including a re-export such as ``sage.all.Poset``).
        # Resolve it only after local/source names so local definitions win.
        alias = self.class_aliases.get(name)
        if alias is not None:
            return alias
        return None

    def _factory_result(self, expression: str | None) -> str | None:
        """Return the public result behind an internal factory marker."""
        if not isinstance(expression, str) or not expression.startswith(_FACTORY_RESULT_PREFIX):
            return None
        result = expression[len(_FACTORY_RESULT_PREFIX):]
        return result or None

    def _receiver_class_path(self, node: ast.AST) -> str | None:
        """Resolve an expression to one concrete class for property lookup."""
        receiver_type = self.expr_type(node)
        if receiver_type == "Self" and self.owner is not None:
            return self.owner
        if receiver_type and receiver_type.startswith("'sage.") and receiver_type.endswith("'"):
            return receiver_type[1:-1]
        if receiver_type and receiver_type.startswith("sage."):
            return receiver_type
        return None

    def _inherited_contract(self, receiver: str, member: str) -> str | None:
        """Resolve one unambiguous member contract from direct source bases."""
        target = f"{receiver}.{member}"
        if target in self.class_methods:
            # An unresolved override must not be replaced by a parent result.
            return None
        candidates = {
            self.known_contracts[f"{parent}.{member}"]
            for parent in self.class_bases.get(receiver, ())
            if f"{parent}.{member}" in self.known_contracts
        }
        return next(iter(candidates)) if len(candidates) == 1 else None

    def _member_contract(self, receiver: str, member: str, seen: set[str] | None = None) -> str | None:
        """Resolve one exact member through a finite class hierarchy."""
        seen = set() if seen is None else seen
        if receiver in seen:
            return None
        seen.add(receiver)
        target = f"{receiver}.{member}"
        direct = self.known_contracts.get(target)
        if direct is not None:
            return direct
        # An unresolved override is a real runtime dispatch boundary.  Do
        # not silently replace it with a parent implementation while walking
        # through a deeper hierarchy; only classes that do not define the
        # member inherit the parent's exact contract.
        if target in self.class_methods:
            return None
        candidates = {
            contract
            for parent in self.class_bases.get(receiver, ())
            for contract in [self._member_contract(parent, member, seen.copy())]
            if contract is not None
        }
        return next(iter(candidates)) if len(candidates) == 1 else None

    def _nested_class_attribute(self, receiver: str, member: str, seen: set[str] | None = None) -> str | None:
        """Resolve a class-valued nested attribute through the source MRO.

        Sage parents frequently expose their element implementation as a
        nested ``element_class`` (or another nested class) rather than as a
        normal constructor contract.  A nested class is a real Python class
        attribute, so it is safe to use when the parsed source/index contains
        exactly one such class and no unresolved method override shadows it.
        Conflicting multiple-inheritance paths remain unresolved.
        """
        seen = set() if seen is None else seen
        if receiver in seen:
            return None
        seen.add(receiver)
        target = f"{receiver}.{member}"
        if target in self.class_methods:
            return None
        if target in self.classes or target in self.known_classes:
            return target
        candidates = {
            nested
            for parent in self.class_bases.get(receiver, ())
            for nested in [self._nested_class_attribute(parent, member, seen.copy())]
            if nested is not None
        }
        return next(iter(candidates)) if len(candidates) == 1 else None

    def _has_method_in_mro(self, receiver: str, member: str, seen: set[str] | None = None) -> bool:
        """Return whether the source MRO explicitly provides ``member``."""
        seen = set() if seen is None else seen
        if receiver in seen:
            return False
        seen.add(receiver)
        if f"{receiver}.{member}" in self.class_methods:
            return True
        return any(
            self._has_method_in_mro(parent, member, seen.copy())
            for parent in self.class_bases.get(receiver, ())
        )

    def _element_class_relation(self, receiver: str) -> str | None:
        """Return the parent-element relation for a concrete ``Element``.

        ``Parent.element_class`` is a runtime-generated class built from the
        receiver's ``Element`` attribute.  When source analysis has proved
        that attribute is one concrete class object, a call through
        ``receiver.element_class(...)`` is therefore an element of that
        parent.  Keep the symbolic relation instead of publishing the
        generated class itself; the IDE can bind it to the receiver's exact
        element factory at the call site.
        """
        attributes = self.class_attributes.get(receiver, {})
        if self._nested_class_attribute(receiver, "element_class") is not None:
            return None
        element = attributes.get("Element")
        if isinstance(element, str) and element.startswith(_CLASS_OBJECT_PREFIX):
            return "'sage.type_contracts.ParentElement[Self]'"
        # A generated Parent descriptor can also be proven from the indexed
        # protocol when the concrete receiver already exposes an exact
        # ``ParentElement[Self]`` member elsewhere in its MRO.  This covers
        # parents such as ``Partitions_n`` whose ``Element`` class is created
        # dynamically and therefore cannot appear as a source assignment.
        # Explicit nested ``element_class`` classes remain ordinary class
        # objects and are handled by the caller before this relation is used.
        if self._member_contract(receiver, "element_class") == "type":
            owners = self._parent_element_owners()
            seen: set[str] = set()

            def has_relation(owner: str) -> bool:
                if owner in seen:
                    return False
                seen.add(owner)
                if owner in owners:
                    return True
                return any(has_relation(parent) for parent in self.class_bases.get(owner, ()))

            if has_relation(receiver):
                return "'sage.type_contracts.ParentElement[Self]'"
        return None

    def _specialize_parent_element_relation(
        self, receiver: str, contract: str
    ) -> str:
        """Resolve a parent-element relation through an exact constructor.

        ``ParentElement[Self]`` is intentionally receiver-relative: for a
        source method on a generic parent it must remain symbolic.  A call on
        an *external exact parent value* (for example ``ZZ.one()``), however,
        has a concrete constructor contract in the generated index.  In that
        case the relation can be specialized to the element class without a
        function-name allow-list.  If no exact constructor is available the
        symbolic relation is retained and the caller remains conservative.
        """
        relation = "'sage.type_contracts.ParentElement[Self]'"
        if contract != relation:
            return contract
        candidates: list[str] = []
        for member in ("__call__", "_element_constructor_"):
            proven = self._member_contract(receiver, member)
            if proven is None or proven == "type":
                continue
            arms = proven.split(" | ")
            if all(
                arm.startswith("'sage.") and arm.endswith("'")
                for arm in arms
            ):
                candidates.append(proven)
        if candidates and len(set(candidates)) == 1:
            return candidates[0]
        return contract

    def _resolve_call(self, node: ast.Call) -> str | None:
        dotted = _dotted(node.func)
        # A factory instance imported from another Sage module is represented
        # in ``known_constants`` by a source-derived ``@factory:...`` marker.
        # Resolve the marker before ordinary name lookup so calls such as
        # ``EllipticCurve(...)`` follow the concrete ``create_object`` union
        # instead of being treated as an untyped CONSTANT.
        if dotted:
            marker = self.known_constants.get(dotted)
            if marker is None and "." not in dotted:
                marker = self.known_constants.get(f"{self.module}.{dotted}")
            factory_result = self._factory_result(marker)
            if factory_result is not None:
                return factory_result
        # A statically indexed Sage value can itself be callable (for
        # example the imported ``ZZ`` parent).  Resolve its exact ``__call__``
        # contract before treating the expression as an ordinary function
        # name.  This is driven solely by the proven value class and member
        # contract, so it also covers aliases and custom callable elements
        # without a symbol/name allow-list.
        callable_type = self.expr_type(node.func)
        if callable_type:
            callable_contracts: list[str] = []
            for arm in callable_type.split(" | "):
                if arm == "Self" and self.owner is not None:
                    receiver = self.owner
                elif arm.startswith("'sage.") and arm.endswith("'"):
                    receiver = arm[1:-1]
                elif arm.startswith("sage."):
                    receiver = arm
                else:
                    callable_contracts = []
                    break
                proven = self._member_contract(receiver, "__call__")
                if proven is None and self._has_method_in_mro(receiver, "__call__"):
                    # Sage Parent.__call__ delegates construction to the
                    # receiver's element constructor.  This fallback is
                    # accepted only when both the callable protocol and the
                    # concrete constructor contract are present in the
                    # source/index; an arbitrary private method is never
                    # treated as a constructor by itself.
                    proven = self._member_contract(receiver, "_element_constructor_")
                if proven is None:
                    callable_contracts = []
                    break
                callable_contracts.append(proven)
            if callable_contracts:
                return _union(*callable_contracts)
        if dotted == "self.__class__.__base__" and self.owner is not None:
            parents = self.class_bases.get(self.owner, ())
            # ``__base__`` is a class object used for implementation
            # dispatch.  An indexed parent with descendants is a structural
            # node, not a stable public result (for example
            # ``structure.parent.Parent``); keep it available for member
            # lookup but do not publish it as this method's return type.
            # A single implementation subclass is not enough to classify a
            # parent as a public dispatch node (many Sage leaf classes have a
            # compatibility wrapper subclass).  Require a stable fan-out in
            # the indexed/source hierarchy before suppressing the class-base
            # result; this keeps ordinary one-child inheritance contracts
            # usable while filtering broad nodes such as ``Parent``.
            has_descendants = (
                sum(parents[0] in declared for declared in self.class_bases.values()) >= 2
                if len(parents) == 1
                else True
            )
            if len(parents) == 1 and _is_final_class_path(parents[0]) and not has_descendants:
                return _quote(parents[0])
        if isinstance(node.func, ast.Attribute):
            receiver = node.func.value
            receiver_type = self.expr_type(receiver)
            method = node.func.attr
            factory_result = self._factory_result(receiver_type)
            if factory_result is not None:
                return factory_result
            if method == "element_class":
                receiver_path = self._receiver_class_path(receiver)
                relation = self._element_class_relation(receiver_path) if receiver_path else None
                if relation is not None:
                    return relation
                # A source class may intentionally define a nested class
                # named ``element_class``.  That is an ordinary class-object
                # constructor and is handled by the class-object branch
                # below; the dynamic Parent descriptor rule must not mask
                # this explicitly proven nested class.
                if relation is None and not (
                    receiver_path
                    and self._nested_class_attribute(receiver_path, method) is not None
                ):
                    # ``Parent.element_class`` is a generated class-valued
                    # descriptor.  Calling it constructs an element, but the
                    # indexed descriptor itself is necessarily annotated as
                    # ``type``.  Never let that descriptor annotation leak
                    # into the result of ``receiver.element_class(...)``:
                    # without a proven ``Element`` implementation the
                    # runtime class is dynamic, so the only sound result is
                    # unresolved.
                    return None
            # Immutable/builtin literal protocols have deterministic result
            # shapes independent of Sage's overloaded element classes.
            if receiver_type in {"str", "bytes"}:
                if method in {"format", "join", "replace", "translate", "strip", "lstrip", "rstrip", "casefold", "lower", "upper", "title", "capitalize", "swapcase", "removeprefix", "removesuffix"}:
                    return receiver_type
                if method in {"split", "rsplit", "splitlines"} and receiver_type == "str":
                    return "list"
                if method == "encode" and receiver_type == "str":
                    return "bytes"
                if method == "decode" and receiver_type == "bytes":
                    return "str"
            if method == "copy" and receiver_type in {"list", "dict", "set", "bytearray"}:
                return receiver_type
            if method == "get" and isinstance(receiver, ast.Dict) and node.args:
                key = node.args[0]
                if isinstance(key, ast.Constant):
                    for literal_key, literal_value in zip(receiver.keys, receiver.values):
                        if isinstance(literal_key, ast.Constant) and literal_key.value == key.value:
                            return self.expr_type(literal_value)
                    if len(node.args) > 1:
                        return self.expr_type(node.args[1])
                    return "None"
            # The Sage classcall protocol is also invoked directly through a
            # class object (``cls.__classcall__(cls, ...)``).  The explicit
            # ``cls`` first argument is the proof that the canonicalized
            # value belongs to this receiver class; ordinary class/factory
            # calls do not receive this shortcut.
            if (
                method == "__classcall__"
                and self.owner is not None
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "cls"
                and _dotted(receiver) in {"cls", "self.__class__"}
            ):
                return "Self"
        # ``copy.copy`` and ``copy.deepcopy`` preserve the copied object's
        # concrete type under Python's copy protocol.  Accept this only when
        # the argument itself is already proven; unknown/dynamic receivers
        # remain fail-closed.
        if dotted in {"copy", "deepcopy", "copy.copy", "copy.deepcopy"} and len(node.args) == 1:
            copied = self.expr_type(node.args[0])
            if copied is not None:
                return copied
        # ``super().method(...)`` is resolved through the statically declared
        # base classes of this owner.  Only a single exact parent contract (or
        # agreeing contracts across all direct bases) is accepted; unresolved
        # and conflicting inheritance remains dynamic.
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name)
            and node.func.value.func.id == "super"
            and self.owner is not None
        ):
            if node.func.attr == "__classcall__":
                # Sage's classcall protocol canonicalizes construction and
                # returns an instance of the current ``cls`` receiver.
                return "Self"
            parent_contracts: set[str] = set()
            for parent in self.class_bases.get(self.owner, ()):
                proven = self._member_contract(parent, node.func.attr)
                if proven is not None:
                    parent_contracts.add(proven)
            if parent_contracts and len(parent_contracts) == 1:
                return next(iter(parent_contracts))
        # A nested receiver call (``self.codomain().zero()`` or
        # ``factory().element()``) can be resolved when the inner call has
        # an exact contract.  Resolve the member through that concrete class
        # before falling back to dotted-name handling below.
        if isinstance(node.func, ast.Attribute):
            receiver_type = self.expr_type(node.func.value)
            if receiver_type:
                receiver_arms = receiver_type.split(" | ")
                resolved_contracts: list[str] = []
                for arm in receiver_arms:
                    if arm == "Self" and self.owner is not None:
                        resolved_receiver = self.owner
                    elif arm.startswith("'sage.") and arm.endswith("'"):
                        resolved_receiver = arm[1:-1]
                    elif arm.startswith("sage."):
                        resolved_receiver = arm
                    else:
                        resolved_receiver = None
                    if resolved_receiver is None:
                        resolved_contracts = []
                        break
                    proven = self._member_contract(resolved_receiver, node.func.attr)
                    if proven is None:
                        resolved_contracts = []
                        break
                    # ``type`` describes a class-valued attribute, not the
                    # instance produced by invoking an arbitrary method.
                    # Keep class-object construction on its explicit branch
                    # and fail closed for stale/broad descriptor contracts.
                    if proven == "type":
                        resolved_contracts = []
                        break
                    proven = self._specialize_parent_element_relation(
                        resolved_receiver, proven
                    )
                    resolved_contracts.append(proven)
                if resolved_contracts and len(resolved_contracts) == len(receiver_arms):
                    return _union(*resolved_contracts)
        if dotted is None:
            return None
        # A class-valued receiver attribute is safe to call only when the
        # source assigned that exact class object (recorded internally by
        # ``_class_attributes``).  This distinguishes explicit element-class
        # factories from arbitrary parent/factory attributes without a name
        # allow-list.
        bits = dotted.split(".")
        if len(bits) == 2:
            class_object: str | None = None
            if bits[0] == "self" and self.owner is not None:
                class_object = self.class_attributes.get(self.owner, {}).get(bits[1])
            elif bits[0] in self.locals:
                class_object = self.locals[bits[0]]
            elif bits[0] in self.module_globals:
                class_object = self.module_globals[bits[0]]
            if class_object and class_object.startswith(_CLASS_OBJECT_PREFIX):
                return _quote(class_object[len(_CLASS_OBJECT_PREFIX):])
        # Resolve a method call on a statically known receiver held in a
        # local or ``self`` attribute.  This is the safe middle ground
        # between a dynamic ``__call__`` guess and a public-base fallback:
        # only an exact Sage class path already present in the source
        # contract map may contribute the member result.  Parent factories,
        # unresolved descriptors, and ``self.attr(...)`` itself are left
        # untouched because their call semantics are runtime-dependent.
        if len(bits) >= 2:
            receiver_name = bits[0]
            receiver_type: str | None = None
            self_attribute_receiver = receiver_name == "self" and len(bits) >= 3
            if self_attribute_receiver and self.owner is not None:
                receiver_type = self.class_attributes.get(self.owner, {}).get(bits[1])
            elif receiver_name in self.locals:
                receiver_type = self.locals[receiver_name]
            elif receiver_name in self.module_globals:
                receiver_type = self.module_globals[receiver_name]
            if receiver_type:
                if receiver_type == "Self" and self.owner is not None:
                    resolved_receiver = self.owner
                elif receiver_type.startswith("'sage.") and receiver_type.endswith("'"):
                    resolved_receiver = receiver_type[1:-1]
                elif receiver_type.startswith("sage."):
                    resolved_receiver = receiver_type
                else:
                    resolved_receiver = None
                if resolved_receiver is not None:
                    member = ".".join(bits[2:] if self_attribute_receiver else bits[1:])
                    proven = self._member_contract(resolved_receiver, member)
                    if proven is not None:
                        if proven == "type":
                            return None
                        proven = self._specialize_parent_element_relation(
                            resolved_receiver, proven
                        )
                        return proven
        # Calling the receiver itself is common for Sage parents and
        # callable element wrappers.  Resolve it only through the receiver's
        # already-proven ``__call__`` contract; absent that exact member,
        # retain the conservative unknown result rather than assuming the
        # call returns ``Self``.
        if dotted == "self" and self.owner is not None:
            proven = self._member_contract(self.owner, "__call__")
            if proven is not None:
                return proven
        if dotted.startswith("self.") and self.owner is not None:
            method_name = dotted.split(".", 1)[1]
            target = f"{self.owner}.{method_name}"
            if target in self.known_contracts:
                return self.known_contracts[target]
            # A direct ``self.method()`` dispatches to the current class only
            # when that class actually defines the member.  If the member is
            # absent, a unique exact contract from statically resolved bases
            # is the same inheritance lookup Python will perform at runtime.
            # Overrides that are present but unresolved deliberately remain
            # UNKNOWN instead of being replaced by a parent result.
            inherited = self._member_contract(self.owner, method_name)
            if inherited is not None:
                if inherited == "type":
                    return None
                return inherited
        # Classcall/constructor helpers conventionally invoke ``cls(...)`` or
        # ``self.__class__(...)``.  The result is the receiver-dependent class,
        # not a public base; represent that dependency as ``Self``.
        if dotted in {"cls", "self.__class__"} and self.owner is not None:
            return "Self"
        if dotted in BUILTIN_CALLS:
            source_position = 1 if dotted == "filter" else 0
            source = self.expr_type(node.args[source_position]) if len(node.args) > source_position else None
            element = _generic_element(source)
            if element is not None:
                if dotted in {"iter", "reversed", "filter"}:
                    return f"Iterator[{element}]"
                if dotted == "sorted":
                    return f"list[{element}]"
                if dotted in {"list", "set", "frozenset"}:
                    return f"{dotted}[{element}]"
                if dotted == "dict":
                    generic = _generic_parts(source or "")
                    if generic is not None and generic[0] == "dict":
                        return source
                if dotted == "enumerate":
                    return f"Iterator[tuple[int, {element}]]"
            if dotted == "zip" and node.args:
                elements = [_generic_element(self.expr_type(argument)) for argument in node.args]
                if all(item is not None for item in elements):
                    return f"Iterator[tuple[{', '.join(item for item in elements if item is not None)}]]"
            return BUILTIN_CALLS[dotted]
        if dotted == "next" and node.args:
            iterator = self.expr_type(node.args[0])
            generic = _generic_parts(iterator) if iterator is not None else None
            if generic is not None and generic[0] == "Iterator" and len(generic[1]) == 1:
                return generic[1][0]
        if dotted == "abs" and node.args:
            operand = self.expr_type(node.args[0])
            if operand == "complex":
                return "float"
            if operand in {"bool", "int", "float"}:
                return operand
        if dotted in {"sum", "prod"} and node.args:
            # The builtin reduction result is provable for a materialized
            # literal or a generator whose element expression is itself
            # proven.  Native numeric promotion follows Python's arithmetic;
            # an explicitly typed same-shape start value also preserves a
            # Sage element under its already-proven closed operation.
            iterable = node.args[0]
            items: list[str | None] | None = None
            if isinstance(iterable, (ast.List, ast.Tuple, ast.Set)):
                items = [self.expr_type(item) for item in iterable.elts]
            elif isinstance(iterable, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
                items = [self.expr_type(iterable.elt)]
            if items is not None and all(item is not None for item in items):
                values = [item for item in items if item is not None]
                start = self.expr_type(node.args[1]) if len(node.args) > 1 else None
                if not values:
                    return start or "int"
                numeric = {"bool", "int", "float", "complex"}
                operands = ([start] if start is not None else []) + values
                if all(item in numeric for item in operands):
                    if "complex" in operands:
                        return "complex"
                    if "float" in operands:
                        return "float"
                    return "int"
                if start is not None and all(item == start for item in values):
                    return start
        if dotted in {"min", "max"} and node.args:
            candidates: list[str] = []
            if len(node.args) == 1:
                if isinstance(node.args[0], (ast.List, ast.Tuple, ast.Set)):
                    candidates = [self.expr_type(item) for item in node.args[0].elts]
                elif isinstance(node.args[0], (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
                    candidates = [self.expr_type(node.args[0].elt)]
                elif self.expr_type(node.args[0]) == "range":
                    return "int"
                else:
                    return None
            else:
                candidates = [self.expr_type(item) for item in node.args]
            if candidates and all(item is not None for item in candidates):
                return _union(*[item for item in candidates if item is not None])
        bits = dotted.split(".")
        if len(bits) == 2:
            receiver_path = None
            if bits[0] == "self" and self.owner is not None:
                receiver_path = self.owner
            elif isinstance(node.func, ast.Attribute):
                receiver_path = self._receiver_class_path(node.func.value)
            if receiver_path is not None:
                nested = self._nested_class_attribute(receiver_path, bits[1])
                if nested is not None:
                    return _quote(nested)
        head = self.imports.get(bits[0])
        if head is not None:
            resolved = ".".join([head, *bits[1:]])
        else:
            resolved = self._resolve_name(bits[0])
            if resolved is not None and len(bits) > 1:
                resolved = ".".join([resolved, *bits[1:]])
        if resolved is None or not resolved.startswith("sage."):
            # A direct call to a source-defined helper has an exact contract
            # when that helper was already proven in the same fixed-point
            # pass.  This is symbol-based (not name allow-list based), and it
            # keeps unresolved/dynamic calls fail-closed.
            if resolved is not None and resolved in self.known_contracts:
                return self.known_contracts[resolved]
            return None
        # A source-defined factory class exposes its exact construction
        # contract through ``create_object``.  Keep only concrete leaves of
        # that contract; abstract/base/generic arms are structural and are
        # deliberately not published as final return types.
        factory_contract = _safe_factory_result(self.known_contracts.get(f"{resolved}.create_object"))
        if factory_contract is not None and resolved in self.classes:
            return _FACTORY_RESULT_PREFIX + factory_contract
        marker = self.known_constants.get(resolved)
        factory_result = self._factory_result(marker)
        if factory_result is not None:
            return factory_result
        overloads = self.known_overloads.get(resolved)
        if overloads and len(overloads) > 1:
            actual = [self.expr_type(argument) for argument in node.args]
            if any(value is not None for value in actual):
                matches: list[str] = []
                for parameters, result in overloads:
                    compatible = True
                    constrained = False
                    for position, value in enumerate(actual):
                        if value is None:
                            continue
                        if position >= len(parameters):
                            compatible = False
                            break
                        expected = parameters[position]
                        if expected is None:
                            continue
                        constrained = True
                        expected_arms = set(expected.split(" | "))
                        actual_arms = set(value.split(" | "))
                        if not (expected_arms & actual_arms):
                            compatible = False
                            break
                    if compatible and constrained:
                        matches.append(result)
                if matches:
                    return _union(*matches)
        generic = self.generic_contracts.get(resolved)
        if generic is not None:
            _, positions = generic
            candidates = [
                self.expr_type(node.args[position])
                for position in positions
                if position < len(node.args)
            ]
            if candidates and all(candidate is not None for candidate in candidates):
                unique = list(dict.fromkeys(candidates))
                if len(unique) == 1:
                    return unique[0]
        if resolved in self.known_contracts:
            return self.known_contracts[resolved]
        # Only a symbol proven to be a class in the parsed Sage sources is a
        # concrete instance constructor.  Sage also has capitalized parent
        # factories (for example ``PolynomialRing``/``MatrixSpace``), so a
        # name-based uppercase heuristic would publish the factory itself as
        # the result and violate the concrete-return contract.
        canonical = self.class_aliases.get(resolved, resolved)
        if canonical in self.classes or canonical in self.known_classes:
            return _quote(canonical)
        return None

    def annotation_type(self, node: ast.AST) -> str | None:
        """Normalize a precise source annotation to a stub expression."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value in {"None", "bool", "bytes", "bytearray", "complex", "dict", "float", "frozenset", "int", "list", "memoryview", "object", "range", "set", "slice", "str", "tuple", "type", "Self", "Iterator", "NoReturn"}:
                return value
            if value.startswith("sage."):
                return _quote(value)
            return None
        if isinstance(node, ast.Name):
            if node.id in {"None", "bool", "bytes", "bytearray", "complex", "dict", "float", "frozenset", "int", "list", "memoryview", "object", "range", "set", "slice", "str", "tuple", "type", "Self", "Iterator", "NoReturn"}:
                return node.id
            resolved = self._resolve_name(node.id)
            if resolved and resolved.startswith("sage."):
                return _quote(resolved)
            return None
        if isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if dotted in {"typing.Iterator", "collections.abc.Iterator", "typing.Iterable", "collections.abc.Iterable"}:
                return "Iterator"
            if dotted in {"typing.NoReturn", "typing_extensions.NoReturn"}:
                return "NoReturn"
            if dotted in {"typing.Self", "typing_extensions.Self"}:
                return "Self"
            if dotted and dotted.startswith("sage."):
                return _quote(dotted)
            return None
        if isinstance(node, ast.Subscript):
            base = self.annotation_type(node.value)
            if base not in {"list", "tuple", "dict", "set", "Iterator"}:
                return None
            # Keep only builtin generic arguments that can be normalized
            # independently.  This preserves useful element information
            # without inventing a Sage parent for a dynamic expression.
            if isinstance(node.slice, ast.Tuple):
                args = [self.annotation_type(item) for item in node.slice.elts]
            else:
                args = [self.annotation_type(node.slice)]
            if any(item is None for item in args):
                return None
            return f"{base}[{', '.join(args)}]"
        return None

    def bind_parameters(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Expose precise source parameter annotations to return inference.

        A direct ``return argument`` is an exact identity contract when the
        argument has a supported annotation.  Existing local assignments take
        precedence, so a reassigned parameter cannot leak its original type.
        """

        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        is_classmethod = any(
            (isinstance(decorator, ast.Name) and decorator.id == "classmethod")
            or (isinstance(decorator, ast.Attribute) and decorator.attr == "classmethod")
            for decorator in node.decorator_list
        )
        for argument in arguments:
            if argument.arg == "self":
                continue
            if argument.annotation is None:
                if node.args.vararg is argument:
                    self.locals.setdefault(argument.arg, "tuple")
                elif node.args.kwarg is argument:
                    self.locals.setdefault(argument.arg, "dict")
                elif is_classmethod and argument.arg == "cls":
                    self.locals.setdefault(argument.arg, "type")
                continue
            inferred = self.annotation_type(argument.annotation)
            if inferred is not None:
                self.locals.setdefault(argument.arg, inferred)

    def bind_external_parameters(
        self, qualified: str, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Bind safe parameter types from a matching generated-index entry."""
        contracts = self.known_parameters.get(qualified)
        if not contracts:
            return
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg is not None:
            arguments.append(node.args.vararg)
        if node.args.kwarg is not None:
            arguments.append(node.args.kwarg)
        public_arguments = [argument for argument in arguments if argument.arg not in {"self", "cls"}]
        for argument, inferred in zip(public_arguments, contracts):
            if inferred is not None:
                self.locals.setdefault(argument.arg, inferred)

    def expr_type(self, node: ast.AST | None) -> str | None:
        # ``return`` without an expression has an explicit AST value of
        # ``None`` and therefore a deterministic Python result.  Treat it as
        # the builtin ``None`` value instead of confusing it with an
        # unresolved expression.
        if node is None:
            return "None"
        if isinstance(node, ast.Constant):
            if node.value is None:
                return "None"
            if isinstance(node.value, bool):
                return "bool"
            if isinstance(node.value, str):
                return "str"
            if isinstance(node.value, bytes):
                return "bytes"
            if isinstance(node.value, complex):
                return "complex"
            if isinstance(node.value, int):
                return "int"
            if isinstance(node.value, float):
                return "float"
            return None
        if isinstance(node, ast.Name):
            if node.id in {"True", "False"}:
                return "bool"
            if node.id == "self" and self.owner is not None:
                return "Self"
            if node.id in self.locals:
                return self.locals[node.id]
            if node.id in self.module_globals:
                return self.module_globals[node.id]
            # Imported constants are indexed under their resolved qualified
            # name (for example ``sage.all.ZZ``), while source code normally
            # refers to the local alias ``ZZ``.  Reuse the exact indexed
            # value class through the import map before treating the name as
            # unresolved; this enables generic receiver-member contracts
            # such as ``ZZ.zero()``/``ZZ.one()`` without a symbol allow-list.
            constant_type = self.known_constants.get(node.id)
            if constant_type is None:
                resolved_constant = self._resolve_name(node.id)
                if resolved_constant is not None:
                    constant_type = self.known_constants.get(resolved_constant)
            if constant_type is not None:
                factory_result = self._factory_result(constant_type)
                if factory_result is not None:
                    return _FACTORY_RESULT_PREFIX + factory_result
                return _quote(constant_type)
            # A bare class symbol is a class object, not an instance produced
            # by calling that class.  Preserve Python's ``type`` contract for
            # this shape; constructor calls are resolved separately in
            # ``_resolve_call`` and retain their concrete Sage instance type.
            resolved = self._resolve_name(node.id)
            if resolved and resolved in self.classes:
                return "type"
            return None
        if isinstance(node, ast.Attribute):
            if node.attr == "__class__":
                return "type"
            if isinstance(node.value, ast.Name) and node.value.id == "self" and self.owner:
                direct = self.class_attributes.get(self.owner, {}).get(node.attr)
                if direct is not None:
                    return direct
            receiver = self._receiver_class_path(node.value)
            if receiver is not None:
                nested = self._nested_class_attribute(receiver, node.attr)
                if nested is not None:
                    return f"{_CLASS_OBJECT_PREFIX}{nested}"
            # Imported Sage modules may expose callable constants (for
            # example ``rings.ZZ``) through an attribute rather than a bare
            # name.  Resolve the dotted module alias first, then reuse only
            # the indexed constant's exact value class.  Unknown/dynamic
            # module attributes remain unresolved.
            dotted = _dotted(node)
            if dotted is not None:
                bits = dotted.split(".")
                resolved = self._resolve_name(bits[0])
                if resolved is not None and len(bits) > 1:
                    resolved = ".".join([resolved, *bits[1:]])
                if resolved is not None:
                    constant_type = self.known_constants.get(resolved)
                    if constant_type is not None:
                        factory_result = self._factory_result(constant_type)
                        if factory_result is not None:
                            return _FACTORY_RESULT_PREFIX + factory_result
                        return _quote(constant_type)
            if receiver is not None:
                direct = self.known_properties.get(f"{receiver}.{node.attr}")
                if direct is not None:
                    return direct
                target = f"{receiver}.{node.attr}"
                if target not in self.class_methods:
                    inherited = {
                        self.known_properties[f"{parent}.{node.attr}"]
                        for parent in self.class_bases.get(receiver, ())
                        if f"{parent}.{node.attr}" in self.known_properties
                    }
                    if len(inherited) == 1:
                        return next(iter(inherited))
            if self.expr_type(node.value) == "type" and node.attr in {"__name__", "__qualname__", "__module__"}:
                return "str"
        if isinstance(node, (ast.List, ast.ListComp)):
            return "list"
        if isinstance(node, (ast.Tuple, ast.GeneratorExp)):
            return "tuple" if isinstance(node, ast.Tuple) else "Iterator"
        if isinstance(node, (ast.Set, ast.SetComp)):
            return "set"
        if isinstance(node, (ast.Dict, ast.DictComp)):
            return "dict"
        if isinstance(node, ast.JoinedStr):
            return "str"
        if isinstance(node, ast.NamedExpr):
            return self.expr_type(node.value)
        if isinstance(node, ast.UnaryOp):
            # Unary arithmetic preserves an already-proven scalar/receiver
            # shape; ``not`` is always the builtin bool result.
            if isinstance(node.op, ast.Not):
                return "bool"
            return self.expr_type(node.operand)
        if isinstance(node, ast.BoolOp):
            # Python ``and``/``or`` return one of their operands rather than
            # coercing the result to bool.  Preserve the exact operand union
            # when every arm is proven; unresolved operands stay unknown.
            values = [self.expr_type(value) for value in node.values]
            if values and all(value is not None for value in values):
                return _union(*[value for value in values if value is not None])
            return None
        if isinstance(node, ast.Compare):
            # Identity and membership comparisons cannot be overloaded into a
            # Sage symbolic value, unlike ``==``/``<`` on symbolic elements.
            if all(isinstance(op, (ast.Is, ast.IsNot, ast.In, ast.NotIn)) for op in node.ops):
                return "bool"
            builtin_scalars = {"bool", "int", "float", "complex", "str", "bytes"}
            left = self.expr_type(node.left)
            comparands = [self.expr_type(item) for item in node.comparators]
            if left in builtin_scalars and all(item in builtin_scalars for item in comparands):
                return "bool"
            return None
        if isinstance(node, ast.Subscript):
            # Resolve only literal containers with a literal integer/key
            # index.  A dynamic ``__getitem__`` depends on runtime parent or
            # slice semantics and must remain unknown; this branch is limited
            # to values whose element is visible in the source itself.
            index = node.slice
            if isinstance(index, ast.Constant):
                if isinstance(node.value, ast.Tuple) and isinstance(index.value, int):
                    position = index.value
                    if position < 0:
                        position += len(node.value.elts)
                    if 0 <= position < len(node.value.elts):
                        return self.expr_type(node.value.elts[position])
                if isinstance(node.value, ast.List) and isinstance(index.value, int):
                    position = index.value
                    if position < 0:
                        position += len(node.value.elts)
                    if 0 <= position < len(node.value.elts):
                        return self.expr_type(node.value.elts[position])
                if isinstance(node.value, ast.Dict):
                    for key, value in zip(node.value.keys, node.value.values):
                        if isinstance(key, ast.Constant) and key.value == index.value:
                            return self.expr_type(value)
            receiver = self._receiver_class_path(node.value)
            if receiver is not None:
                # An indexed Sage object may implement a concrete
                # ``__getitem__`` contract in the generated index.  This is
                # safe for arbitrary keys only when that contract is already
                # exact; dynamic/slice-dependent members remain unknown.
                return self.known_contracts.get(f"{receiver}.__getitem__")
            # An explicitly typed builtin container has a deterministic
            # element contract even when the index is dynamic.  This is
            # parameter/annotation driven, not a Sage class-name heuristic:
            # ``list[T][i]`` and ``dict[K, V][key]`` produce ``T``/``V``;
            # heterogeneous tuples conservatively expose their finite union.
            container = self.expr_type(node.value)
            generic = _generic_parts(container) if container is not None else None
            if generic is not None:
                base, arguments = generic
                if base in {"list", "set", "frozenset"} and len(arguments) == 1:
                    return arguments[0]
                if base == "dict" and len(arguments) == 2:
                    return arguments[1]
                if base == "tuple" and arguments:
                    finite = [argument for argument in arguments if argument != "..."]
                    if finite:
                        return _union(*finite)
            return None
        if isinstance(node, ast.IfExp):
            left = self.expr_type(node.body)
            right = self.expr_type(node.orelse)
            if left is None or right is None:
                return None
            if left == right:
                return left
            # A conditional expression is just as explicit as statement-level
            # branches.  Keep both proven arm shapes (including ``None``)
            # instead of rejecting the whole function or widening it.
            return _union(left, right)
        if isinstance(node, ast.BinOp):
            left = self.expr_type(node.left)
            right = self.expr_type(node.right)
            # Native Python scalar arithmetic has a fixed result type.  Keep
            # this branch limited to builtins so overloaded Sage elements
            # still require a concrete source contract or Self rule.
            if left is not None and right is not None:
                numeric = {"bool", "int", "float", "complex"}
                if left in numeric and right in numeric:
                    if isinstance(node.op, ast.Pow):
                        # Integer powers may become float for a negative
                        # exponent; the value is not known from the type.
                        return None
                    if isinstance(node.op, ast.Div):
                        return "complex" if "complex" in {left, right} else "float"
                    if "complex" in {left, right}:
                        return "complex"
                    if "float" in {left, right}:
                        return "float"
                    return "int"
                if left == right == "str" and isinstance(node.op, ast.Add):
                    return "str"
                if left == right == "bytes" and isinstance(node.op, ast.Add):
                    return "bytes"
            # Closed operations are accepted only when both operands already
            # have the exact same non-builtin shape.  This avoids turning
            # scalar multiplication or mixed-parent arithmetic into ``Self``.
            if left is not None and left == right and left not in {
                "None", "bool", "bytes", "dict", "float", "int", "list", "set", "str", "tuple"
            }:
                return left
            return None
        if isinstance(node, ast.Call):
            # Element implementations commonly normalize an intermediate
            # value through their own parent factory (``self.parent()(...)``).
            # The parent may be dynamically specialized, but Sage's parent
            # protocol guarantees that applying it constructs an element of
            # that receiver's concrete family.  The AST shape itself is the
            # proof: parent objects/functors do not call their own ``parent``
            # factory to produce a value, so no class-name allow-list is
            # needed here.
            if (
                isinstance(node.func, ast.Call)
                and _dotted(node.func.func) == "self.parent"
                and self.owner is not None
            ):
                return "Self"
            # ``type(self)(...)`` is the equivalent explicit spelling used by
            # Sage classes that preserve the concrete receiver type without
            # going through its parent.  Require the exact one-argument
            # ``type(self)`` factory shape; arbitrary ``type(...)`` calls are
            # class queries and must not be treated as constructors.
            if (
                isinstance(node.func, ast.Call)
                and _dotted(node.func.func) == "type"
                and len(node.func.args) == 1
                and isinstance(node.func.args[0], ast.Name)
                and node.func.args[0].id == "self"
                and self.owner is not None
            ):
                return "Self"
            return self._resolve_call(node)
        return None


def _iter_function_body(nodes: Iterable[ast.stmt]) -> Iterable[ast.stmt]:
    """Yield statements while not descending into nested function bodies."""
    for node in nodes:
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.stmt):
                yield from _iter_function_body((child,))


def _returns(nodes: Iterable[ast.stmt]) -> tuple[list[ast.Return], bool]:
    returns: list[ast.Return] = []
    has_yield = False

    def walk(node: ast.AST) -> None:
        nonlocal has_yield
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, ast.Return):
            returns.append(node)
            return
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            has_yield = True
        for child in ast.iter_child_nodes(node):
            walk(child)

    for statement in nodes:
        walk(statement)
    return returns, has_yield


def _yields(nodes: Iterable[ast.stmt]) -> list[tuple[ast.AST | None, bool]]:
    """Collect generator expressions without descending into nested scopes."""
    result: list[tuple[ast.AST | None, bool]] = []

    def walk(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, ast.Yield):
            result.append((node.value, False))
            return
        if isinstance(node, ast.YieldFrom):
            result.append((node.value, True))
            return
        for child in ast.iter_child_nodes(node):
            walk(child)

    for statement in nodes:
        walk(statement)
    return result


def _is_property_node(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return whether a source function is declared with ``@property``."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "property":
            return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == "getter":
            return True
    return False


def _may_fall_through(statements: list[ast.stmt]) -> bool:
    """Conservative control-flow check for implicit ``None`` paths."""
    reachable = True
    for statement in statements:
        if not reachable:
            break
        if isinstance(statement, (ast.Return, ast.Raise)):
            reachable = False
        elif isinstance(statement, ast.If):
            body = _may_fall_through(statement.body)
            alternate = _may_fall_through(statement.orelse) if statement.orelse else True
            reachable = body or alternate
        elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While, ast.Match)):
            # A loop may execute zero times and match exhaustiveness is
            # generally data-dependent; leaving these paths unknown is safer
            # than inventing a contract.
            reachable = True
        elif isinstance(statement, (ast.With, ast.AsyncWith)):
            # Context-manager setup does not change the body's return shape;
            # the body itself determines whether an implicit ``None`` path
            # remains.
            reachable = _may_fall_through(statement.body)
        elif isinstance(statement, ast.Try):
            # Model try/except/else/finally without guessing exception types.
            # The normal path reaches ``else`` only when the try body can
            # fall through; every handler contributes an independent path.
            try_reachable = _may_fall_through(statement.body)
            normal_reachable = (
                _may_fall_through(statement.orelse) if try_reachable else False
            ) if statement.orelse else try_reachable
            handler_reachable = any(_may_fall_through(handler.body) for handler in statement.handlers)
            before_finally = normal_reachable or handler_reachable
            if statement.finalbody:
                # A finally block runs on every path.  If it itself returns or
                # raises unconditionally, no successful fallthrough remains;
                # otherwise only paths that reached the try statement can
                # fall through it.
                reachable = before_finally and _may_fall_through(statement.finalbody)
            else:
                reachable = before_finally
    return reachable


def _implicit_none_is_safe(statements: list[ast.stmt]) -> bool:
    """Whether a fall-through path is an ordinary implicit ``None`` path.

    A straight-line body and conditional blocks have only the Python implicit
    return value when they reach the end.  Loops, ``try``/``except`` and
    ``match`` introduce data-dependent exits or exception paths, so those
    constructs remain conservative and do not widen a Sage contract.
    """

    def walk(node: ast.AST) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return True
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            # A single unconditional return may execute zero times, so the
            # successful function result is the return shape plus implicit
            # None.  Any additional statement, ``else`` block, or nested
            # branch makes the loop data-dependent and stays conservative.
            return len(node.body) == 1 and isinstance(node.body[0], ast.Return) and not node.orelse
        if isinstance(node, (ast.Try, ast.Match)):
            return False
        return all(walk(child) for child in ast.iter_child_nodes(node))

    return all(walk(statement) for statement in statements)


def _always_raises(statements: list[ast.stmt]) -> bool:
    """Recognize a small, deterministic no-return control-flow shape.

    Non-control statements are harmless before a final ``raise``.  Conditional
    branches are accepted only when both explicit branches unconditionally
    raise; loops, try/match and implicit branches remain unknown.
    """

    reachable = True
    saw_terminal = False
    for statement in statements:
        if not reachable:
            break
        if isinstance(statement, ast.Raise):
            reachable = False
            saw_terminal = True
        elif isinstance(statement, ast.If):
            if not statement.orelse or not _always_raises(statement.body) or not _always_raises(statement.orelse):
                return False
            reachable = False
            saw_terminal = True
        elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match, ast.Return)):
            return False
        else:
            # Assignments, docstrings and diagnostic calls do not create a
            # successful return path by themselves.
            continue
    return saw_terminal and not reachable


def _local_types(statements: list[ast.stmt], analyzer: _FunctionAnalyzer) -> bool:
    """Collect simple local assignments used by ``return value``.

    A name is usable only when every assignment seen in the function has the
    same inferred shape.  Unknown or conflicting assignments invalidate that
    name instead of guessing from one branch.
    """
    values: dict[str, set[str]] = {}

    def record(target: ast.AST, value: ast.AST | None) -> None:
        if isinstance(target, ast.Name):
            inferred = _assigned_type(value, analyzer) if value is not None else None
            values.setdefault(target.id, set()).add(inferred or "<unknown>")
            return
        if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
            if len(target.elts) != len(value.elts):
                return
            for target_item, value_item in zip(target.elts, value.elts):
                record(target_item, value_item)

    def walk(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, ast.Assign):
            for target in node.targets:
                record(target, node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            record(node.target, node.value)
        for child in ast.iter_child_nodes(node):
            walk(child)

    for statement in statements:
        walk(statement)
    for name, inferred in values.items():
        if len(inferred) == 1 and "<unknown>" not in inferred:
            analyzer.locals[name] = next(iter(inferred))
    return True


def _loop_types(statements: list[ast.stmt], analyzer: _FunctionAnalyzer) -> None:
    """Bind simple ``for target in Iterable[T]`` loop variables."""
    def walk(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            iterable = analyzer.expr_type(node.iter)
            element = _generic_element(iterable)
            if element is None and iterable == "range":
                element = "int"
            if element is not None and isinstance(node.target, ast.Name):
                analyzer.locals[node.target.id] = element
            for child in node.body:
                walk(child)
            for child in node.orelse:
                walk(child)
            return
        for child in ast.iter_child_nodes(node):
            walk(child)

    for statement in statements:
        walk(statement)


def _imports(
    tree: ast.Module,
    module_name: str | None = None,
    *,
    package_module: bool = False,
) -> dict[str, str]:
    """Collect imports with Python-accurate relative-module resolution.

    Sage's pure-Python sources use relative imports heavily.  ``ast`` keeps
    the leading-dot level separately from ``ImportFrom.module``; preserving
    that level here lets source contracts resolve the same concrete symbol
    that Python binds at runtime.  ``package_module`` is true for an
    ``__init__.py`` module, whose current package is the module itself rather
    than its parent.
    """
    result: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                result[name] = alias.name
        elif isinstance(node, ast.ImportFrom) and (node.module or node.level):
            module = node.module or ""
            if node.level and module_name:
                parts = module_name.split(".")
                package_parts = parts if package_module else parts[:-1]
                trim = max(node.level - 1, 0)
                if trim:
                    package_parts = package_parts[:-trim] if trim <= len(package_parts) else []
                module = ".".join([*package_parts, module] if module else package_parts)
            for alias in node.names:
                if alias.name == "*":
                    continue
                result[alias.asname or alias.name] = (
                    f"{module}.{alias.name}" if module else alias.name
                )
    return result


def _imports_from_body(
    statements: Iterable[ast.stmt],
    module_name: str,
    *,
    package_module: bool = False,
) -> tuple[dict[str, str], set[str]]:
    """Collect imports local to one function body.

    Function-local imports are common in Sage modules with circular
    dependencies.  A conflicting alias across branches is removed instead
    of guessed; callers can then fall back to the enclosing module imports.
    Nested function/class scopes are deliberately excluded.
    """
    candidates: dict[str, set[str]] = {}

    def record(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                candidates.setdefault(name, set()).add(alias.name)
        elif isinstance(node, ast.ImportFrom) and (node.module or node.level):
            module = node.module or ""
            if node.level:
                parts = module_name.split(".")
                package_parts = parts if package_module else parts[:-1]
                trim = max(node.level - 1, 0)
                if trim:
                    package_parts = package_parts[:-trim] if trim <= len(package_parts) else []
                module = ".".join([*package_parts, module] if module else package_parts)
            for alias in node.names:
                if alias.name == "*":
                    continue
                target = f"{module}.{alias.name}" if module else alias.name
                candidates.setdefault(alias.asname or alias.name, set()).add(target)
        for child in ast.iter_child_nodes(node):
            record(child)

    for statement in statements:
        record(statement)
    return (
        {name: next(iter(values)) for name, values in candidates.items() if len(values) == 1},
        {name for name, values in candidates.items() if len(values) > 1},
    )


def _class_names(files: list[tuple[Path, str, ast.Module]]) -> set[str]:
    result: set[str] = set()
    for _, module, tree in files:
        def visit(node: ast.AST, owner: str | None = None) -> None:
            if isinstance(node, ast.ClassDef):
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                result.add(qualified)
                for child in node.body:
                    visit(child, qualified)
                return
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, owner)

        visit(tree)
    return result


def _class_attributes(
    files: list[tuple[Path, str, ast.Module]],
    classes: set[str],
    module_globals: dict[str, dict[str, str]],
    known_contracts: dict[str, str] | None = None,
    generic_contracts: dict[str, tuple[str, tuple[int, ...]]] | None = None,
    known_classes: set[str] | None = None,
    class_aliases: dict[str, str] | None = None,
    known_properties: dict[str, str] | None = None,
    known_parameters: dict[str, tuple[str | None, ...]] | None = None,
    known_constants: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """Infer stable ``self.attr`` shapes from simple assignments.

    Only literal/container/builtin/constructor expressions accepted by
    :meth:`_FunctionAnalyzer.expr_type` are retained, and conflicting writes
    invalidate the attribute.  Constructor arguments and dynamic descriptors
    therefore remain unknown instead of becoming guessed parent types.
    """

    result: dict[str, dict[str, str]] = {}
    for path, module, tree in files:
        imports = _imports(tree, module, package_module=path.name == "__init__.py")

        def visit(node: ast.AST, owner: str | None = None) -> None:
            if isinstance(node, ast.ClassDef):
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                stable: dict[str, str] = {}
                # A short fixed point resolves simple chains such as
                # ``self.items = []`` followed by ``self.values = self.items``.
                for _ in range(len(node.body) + 1):
                    values: dict[str, set[str]] = {}
                    for child in node.body:
                        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            continue
                        child_imports = dict(imports)
                        local_imports, ambiguous_imports = _imports_from_body(
                            child.body, module, package_module=path.name == "__init__.py"
                        )
                        for name in ambiguous_imports:
                            child_imports.pop(name, None)
                        child_imports.update(local_imports)
                        analyzer = _FunctionAnalyzer(
                            module,
                            child_imports,
                            classes,
                            qualified,
                            {qualified: stable},
                            module_globals.get(module),
                            known_contracts,
                            generic_contracts,
                            known_classes,
                            class_aliases,
                            known_properties,
                            known_parameters=known_parameters,
                            known_constants=known_constants,
                        )
                        analyzer.bind_parameters(child)
                        analyzer.bind_external_parameters(f"{qualified}.{child.name}", child)

                        def walk(statement: ast.AST) -> None:
                            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                                return
                            if isinstance(statement, ast.Assign):
                                targets = statement.targets
                                value = statement.value
                            elif isinstance(statement, ast.AnnAssign):
                                targets = [statement.target]
                                value = statement.value
                            else:
                                targets = []
                                value = None
                            if targets and value is not None:
                                inferred = _assigned_type(value, analyzer)
                                if inferred is not None:
                                    for target in targets:
                                        if (
                                            isinstance(target, ast.Attribute)
                                            and isinstance(target.value, ast.Name)
                                            and target.value.id == "self"
                                        ):
                                            values.setdefault(target.attr, set()).add(inferred)
                            for nested in ast.iter_child_nodes(statement):
                                walk(nested)

                        for statement in child.body:
                            walk(statement)
                    # Class-level constants are also visible through
                    # ``self.NAME`` and obey the same conflict checks.
                    analyzer = _FunctionAnalyzer(
                        module,
                        imports,
                        classes,
                        qualified,
                        {qualified: stable},
                        module_globals.get(module),
                        known_contracts,
                        generic_contracts,
                        known_classes,
                        class_aliases,
                        known_properties,
                        known_parameters=known_parameters,
                        known_constants=known_constants,
                    )
                    for statement in node.body:
                        if isinstance(statement, ast.Assign):
                            targets, value = statement.targets, statement.value
                        elif isinstance(statement, ast.AnnAssign):
                            targets, value = [statement.target], statement.value
                        else:
                            continue
                        if value is None:
                            continue
                        inferred = _assigned_type(value, analyzer)
                        if inferred is None:
                            continue
                        for target in targets:
                            if isinstance(target, ast.Name):
                                values.setdefault(target.id, set()).add(inferred)
                    updated = {
                        name: next(iter(inferred))
                        for name, inferred in values.items()
                        if len(inferred) == 1
                    }
                    if updated == stable:
                        break
                    stable = updated
                if stable:
                    result[qualified] = stable
                for child in node.body:
                    if isinstance(child, ast.ClassDef):
                        visit(child, qualified)
                return
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, owner)

        visit(tree)
    return result


def _module_globals(
    files: list[tuple[Path, str, ast.Module]],
    classes: set[str],
    known_contracts: dict[str, str] | None = None,
    generic_contracts: dict[str, tuple[str, tuple[int, ...]]] | None = None,
    known_classes: set[str] | None = None,
    class_aliases: dict[str, str] | None = None,
    known_properties: dict[str, str] | None = None,
    known_constants: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """Infer stable module constants used by trivial wrapper functions."""

    result: dict[str, dict[str, str]] = {}
    for path, module, tree in files:
        imports = _imports(tree, module, package_module=path.name == "__init__.py")
        analyzer = _FunctionAnalyzer(
            module,
            imports,
            classes,
            None,
            known_contracts=known_contracts,
            generic_contracts=generic_contracts,
            known_classes=known_classes,
            class_aliases=class_aliases,
            known_properties=known_properties,
            known_constants=known_constants,
        )
        values: dict[str, set[str]] = {}
        for statement in tree.body:
            if isinstance(statement, ast.Assign):
                targets, value = statement.targets, statement.value
            elif isinstance(statement, ast.AnnAssign):
                targets, value = [statement.target], statement.value
            else:
                continue
            inferred = _assigned_type(value, analyzer) if value is not None else None
            if inferred is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    values.setdefault(target.id, set()).add(inferred)
        stable = {name: next(iter(items)) for name, items in values.items() if len(items) == 1}
        if stable:
            result[module] = stable
    return result


def _class_bases(
    files: list[tuple[Path, str, ast.Module]], classes: set[str]
) -> dict[str, tuple[str, ...]]:
    """Resolve statically named class bases for attribute inheritance."""
    result: dict[str, tuple[str, ...]] = {}
    for path, module, tree in files:
        imports = _imports(tree, module, package_module=path.name == "__init__.py")

        def visit(node: ast.AST, owner: str | None = None) -> None:
            if isinstance(node, ast.ClassDef):
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                bases: list[str] = []
                for base in node.bases:
                    dotted = _dotted(base)
                    if dotted is None:
                        continue
                    bits = dotted.split(".")
                    resolved = imports.get(bits[0])
                    if resolved is None:
                        resolved = f"{module}.{bits[0]}"
                    if len(bits) > 1:
                        resolved = ".".join([resolved, *bits[1:]])
                    if resolved in classes:
                        bases.append(resolved)
                result[qualified] = tuple(dict.fromkeys(bases))
                for child in node.body:
                    visit(child, qualified)
                return
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, owner)

        visit(tree)
    return result


def _class_methods(files: list[tuple[Path, str, ast.Module]]) -> set[str]:
    """Collect methods explicitly defined by each parsed class."""
    result: set[str] = set()
    for _, module, tree in files:
        def visit(node: ast.AST, owner: str | None = None) -> None:
            if isinstance(node, ast.ClassDef):
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        result.add(f"{qualified}.{child.name}")
                    elif isinstance(child, ast.ClassDef):
                        visit(child, qualified)
                return
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, owner)

        visit(tree)
    return result


def _inherit_class_attributes(
    attributes: dict[str, dict[str, str]],
    bases: dict[str, tuple[str, ...]],
) -> dict[str, dict[str, str]]:
    """Add only unambiguous class attributes inherited from proven bases."""
    result = {owner: dict(values) for owner, values in attributes.items()}
    for _ in range(len(bases) + 1):
        changed = False
        for owner, parent_names in bases.items():
            current = result.setdefault(owner, {})
            for name in set().union(*(set(result.get(parent, {})) for parent in parent_names)):
                if name in current:
                    continue
                inherited = {result[parent][name] for parent in parent_names if name in result.get(parent, {})}
                if len(inherited) == 1 and all(name in result.get(parent, {}) for parent in parent_names):
                    current[name] = next(iter(inherited))
                    changed = True
        if not changed:
            break
    return {owner: values for owner, values in result.items() if values}


_INDEX_PAYLOAD_CACHE: dict[str, dict] = {}


def _read_index_payload(index: Path | None) -> dict:
    if index is None:
        return {}
    key = str(index.resolve())
    if key not in _INDEX_PAYLOAD_CACHE:
        try:
            _INDEX_PAYLOAD_CACHE[key] = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _INDEX_PAYLOAD_CACHE[key] = {}
    return _INDEX_PAYLOAD_CACHE[key]


def _index_contracts(index: Path | None) -> dict[str, str]:
    """Load only exact, reusable return contracts from a generated index.

    This is a read-only bridge for source wrappers whose receiver is a method
    implemented in Cython or another generated stub.  Ambiguous overloads,
    type variables and broad structural expressions are ignored.  When every
    overload agrees on a finite set of exact builtin/concrete Sage classes,
    that set is retained as a precise union for source-wrapper propagation.
    """
    payload = _read_index_payload(index)
    builtins = {
        "None", "NoReturn", "Self", "Iterator", "bool", "bytes", "bytearray",
        "complex", "dict", "float", "frozenset", "int", "list", "memoryview",
        "object", "range", "set", "slice", "str", "tuple", "type",
    }
    class_names = {
        entry.get("qualifiedName")
        for entry in payload.get("entries", [])
        if entry.get("kind") == "CLASS"
        and isinstance(entry.get("qualifiedName"), str)
        and _is_final_class_path(entry.get("qualifiedName", ""))
    }
    def normalize_arm(arm: str) -> str | None:
        """Normalize one exact index arm usable by source propagation.

        ``typing.Self`` is the spelling emitted by stubgen for a receiver-
        preserving contract.  Sage's relation contracts (for example
        ``ParentElement[Self]`` and ``CodomainElement[Self]``) are likewise
        exact symbolic relationships, not public base classes.  Accept only
        the structural ``*Element[Self]`` form from the dedicated contract
        namespace; unconstrained type variables and arbitrary generics stay
        fail-closed.
        """
        arm = arm.strip().replace("typing.Self", "Self").replace("typing.NoReturn", "NoReturn")
        if arm in builtins or arm == "Self":
            return arm
        if arm in class_names:
            return _quote(arm)
        relation_prefix = "sage.type_contracts."
        if arm.startswith(relation_prefix) and re.fullmatch(
            r"sage\.type_contracts\.[A-Za-z_][A-Za-z0-9_]*Element\[Self\]", arm
        ):
            return _quote(arm)
        return None

    result: dict[str, str] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") not in {"FUNCTION", "METHOD"}:
            continue
        qualified = entry.get("qualifiedName")
        if not isinstance(qualified, str):
            continue
        expressions = {
            signature.get("returnType", {}).get("expression")
            for signature in entry.get("signatures", [])
            if signature.get("returnType", {}).get("state") == "KNOWN"
        }
        if not expressions or any(not isinstance(expression, str) for expression in expressions):
            continue
        arms = [
            arm.strip()
            for expression in sorted(expressions)
            for arm in expression.split(" | ")
        ]
        normalized = [normalize_arm(arm) for arm in arms]
        if arms and all(arm is not None for arm in normalized):
            result[qualified] = _union(*[arm for arm in normalized if arm is not None])
    return result


def _index_factory_contracts(index: Path | None) -> dict[str, str]:
    """Load only concrete arms from indexed ``create_object`` contracts.

    Factory ``create_object`` methods intentionally document both concrete
    implementations and a structural protocol/base class. Ordinary index
    contracts remain fail-closed; this narrow bridge is consumed only while
    resolving a module-level ``Factory(...)`` binding, where the structural
    arm is not a possible final IDE type.
    """
    payload = _read_index_payload(index)
    class_names = {
        entry.get("qualifiedName")
        for entry in payload.get("entries", [])
        if entry.get("kind") == "CLASS"
        and isinstance(entry.get("qualifiedName"), str)
    }
    result: dict[str, str] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") not in {"FUNCTION", "METHOD"}:
            continue
        qualified = entry.get("qualifiedName")
        if not isinstance(qualified, str) or not qualified.endswith(".create_object"):
            continue
        owner = qualified[: -len(".create_object")]
        if owner not in class_names:
            continue
        expressions = {
            signature.get("returnType", {}).get("expression")
            for signature in entry.get("signatures", [])
            if signature.get("returnType", {}).get("state") == "KNOWN"
        }
        if len(expressions) != 1:
            continue
        expression = next(iter(expressions))
        safe = _safe_factory_result(expression)
        if safe is not None:
            result[qualified] = safe
    return result


def _index_classes(index: Path | None) -> set[str]:
    """Return Sage class paths from an index for exact constructor calls."""
    payload = _read_index_payload(index)
    return {
        entry["qualifiedName"]
        for entry in payload.get("entries", [])
        if entry.get("kind") == "CLASS"
        and isinstance(entry.get("qualifiedName"), str)
        and _is_final_class_path(entry["qualifiedName"])
    }


def _index_class_bases(index: Path | None) -> dict[str, tuple[str, ...]]:
    """Load indexed inheritance edges for source classes with Cython bases.

    Pure-Python Sage classes frequently inherit from extension classes whose
    implementation is present only in the generated ``.pyi`` tree.  The
    source-only MRO is therefore incomplete at exactly the call sites where
    wrappers delegate to parent protocols.  These edges are used exclusively
    for member lookup; the returned member contract still has to be an exact
    indexed contract (or a symbolic relation such as ``ParentElement``).
    """
    payload = _read_index_payload(index)
    result: dict[str, tuple[str, ...]] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") != "CLASS":
            continue
        qualified = entry.get("qualifiedName")
        if not isinstance(qualified, str) or not qualified.startswith("sage."):
            continue
        parents = tuple(
            parent
            for parent in entry.get("parents", [])
            if isinstance(parent, str) and parent.startswith("sage.")
        )
        if parents:
            result[qualified] = parents
    return result


def _index_class_aliases(index: Path | None) -> dict[str, str]:
    """Resolve aliases for one indexed class or exact callable contract."""
    payload = _read_index_payload(index)
    class_entries = {
        entry.get("qualifiedName"): entry
        for entry in payload.get("entries", [])
        if entry.get("kind") == "CLASS"
        and isinstance(entry.get("qualifiedName"), str)
        and _is_final_class_path(entry.get("qualifiedName", ""))
    }
    children: set[str] = set()
    for entry in class_entries.values():
        for parent in entry.get("parents", []):
            if isinstance(parent, str):
                children.add(parent)
    targets: dict[str, set[str]] = {}
    for entry in class_entries.values():
        canonical = entry.get("qualifiedName")
        if not isinstance(canonical, str):
            continue
        for alias in entry.get("aliases", []):
            if isinstance(alias, str) and alias.startswith("sage."):
                targets.setdefault(alias, set()).add(canonical)
        # A short class name is safe only when it identifies one concrete
        # leaf class.  Public protocol/base classes with indexed subclasses
        # are deliberately excluded from this unqualified fallback.
        if canonical not in children:
            short = canonical.rsplit(".", 1)[-1]
            targets.setdefault(short, set()).add(canonical)
    # Re-exported functions in ``sage.all`` are common in pure-Python Sage
    # modules, where a star import is not recoverable from the AST.  Bridge
    # only callable entries whose return contract is already exact (builtin
    # or concrete class/finite union); unknown, dynamic and structural
    # contracts never become aliases here.
    exact_contracts = _index_contracts(index)
    callable_targets: dict[str, set[str]] = {}
    preferred_all_targets: dict[str, set[str]] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") not in {"FUNCTION", "ALIAS"}:
            continue
        qualified = entry.get("qualifiedName")
        if not isinstance(qualified, str):
            continue
        target = qualified if qualified in exact_contracts else None
        if target is None:
            aliases = entry.get("aliases", [])
            if isinstance(aliases, list):
                candidates = [alias for alias in aliases if isinstance(alias, str) and alias in exact_contracts]
                if len(candidates) == 1:
                    target = candidates[0]
        if target is None:
            continue
        if qualified.startswith("sage.all."):
            short = qualified.rsplit(".", 1)[-1]
            callable_targets.setdefault(short, set()).add(target)
            callable_targets.setdefault(qualified, set()).add(target)
            preferred_all_targets.setdefault(short, set()).add(target)
        # A unique non-re-exported function name is also safe to resolve for
        # modules that imported it directly but whose import was elided by a
        # generated source wrapper.
        short = qualified.rsplit(".", 1)[-1]
        callable_targets.setdefault(short, set()).add(target)
    # Ring/parent constants (``ZZ``, ``QQ`` and friends) are callable Sage
    # objects even though they are indexed as CONSTANT rather than FUNCTION.
    # Resolve a constant to its concrete ``__call__`` contract by walking the
    # indexed parent graph.  No constant-name list is used; absent or
    # conflicting call contracts remain unresolved.
    class_parents: dict[str, tuple[str, ...]] = {
        entry.get("qualifiedName"): tuple(
            parent for parent in entry.get("parents", []) if isinstance(parent, str)
        )
        for entry in payload.get("entries", [])
        if entry.get("kind") == "CLASS" and isinstance(entry.get("qualifiedName"), str)
    }

    def call_contract(class_path: str, seen: set[str] | None = None) -> tuple[str, str] | None:
        seen = seen or set()
        if class_path in seen:
            return None
        seen.add(class_path)
        direct = exact_contracts.get(f"{class_path}.__call__")
        if direct is not None:
            return class_path, direct
        inherited = [
            result
            for parent in class_parents.get(class_path, ())
            if (result := call_contract(parent, seen.copy())) is not None
        ]
        if inherited and len({value[1] for value in inherited}) == 1:
            return inherited[0][0], inherited[0][1]
        return None

    for entry in payload.get("entries", []):
        if entry.get("kind") != "CONSTANT":
            continue
        qualified = entry.get("qualifiedName")
        if not isinstance(qualified, str):
            continue
        value_type = entry.get("valueType", {})
        class_path = value_type.get("expression") if isinstance(value_type, dict) else None
        if not isinstance(class_path, str) or not class_path.startswith("sage."):
            continue
        resolved = call_contract(class_path)
        if resolved is None:
            continue
        target = f"{resolved[0]}.__call__"
        short = qualified.rsplit(".", 1)[-1]
        callable_targets.setdefault(short, set()).add(target)
        callable_targets.setdefault(qualified, set()).add(target)
    for alias, values in callable_targets.items():
        preferred = preferred_all_targets.get(alias)
        if preferred and len(preferred) == 1:
            targets.setdefault(alias, set()).update(preferred)
            continue
        if len(values) == 1:
            targets.setdefault(alias, set()).update(values)
    return {alias: next(iter(values)) for alias, values in targets.items() if len(values) == 1}


def _index_generic_contracts(index: Path | None) -> dict[str, tuple[str, tuple[int, ...]]]:
    """Load exact same-parameter TypeVar return contracts from the index."""
    payload = _read_index_payload(index)
    result: dict[str, tuple[str, tuple[int, ...]]] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") not in {"FUNCTION", "METHOD"}:
            continue
        qualified = entry.get("qualifiedName")
        if not isinstance(qualified, str):
            continue
        signatures = entry.get("signatures", [])
        if not isinstance(signatures, list) or not signatures:
            continue
        descriptors: list[tuple[str, tuple[int, ...]]] = []
        for signature in signatures:
            if not isinstance(signature, dict):
                descriptors = []
                break
            return_type = signature.get("returnType", {})
            type_parameters = signature.get("typeParameters", [])
            if not isinstance(return_type, dict) or return_type.get("state") != "KNOWN":
                descriptors = []
                break
            variable = return_type.get("expression")
            if not isinstance(variable, str) or not isinstance(type_parameters, list):
                descriptors = []
                break
            if not any(item.get("name") == variable for item in type_parameters if isinstance(item, dict)):
                descriptors = []
                break
            parameters = signature.get("parameters", [])
            positions: list[int] = []
            for position, parameter in enumerate(parameters):
                if not isinstance(parameter, dict) or parameter.get("variadic"):
                    continue
                parameter_type = parameter.get("type", {})
                if isinstance(parameter_type, dict) and parameter_type.get("state") == "KNOWN" and parameter_type.get("expression") == variable:
                    positions.append(position)
            if not positions:
                descriptors = []
                break
            descriptors.append((variable, tuple(positions)))
        if descriptors and len(set(descriptors)) == 1:
            result[qualified] = descriptors[0]
    return result


def _index_properties(index: Path | None) -> dict[str, str]:
    """Load exact property contracts for concrete Sage receivers only."""
    payload = _read_index_payload(index)
    builtins = {
        "None", "NoReturn", "Self", "Iterator", "bool", "bytes", "bytearray",
        "complex", "dict", "float", "frozenset", "int", "list", "memoryview",
        "object", "range", "set", "slice", "str", "tuple", "type",
    }
    class_names = {
        entry.get("qualifiedName")
        for entry in payload.get("entries", [])
        if entry.get("kind") == "CLASS"
        and isinstance(entry.get("qualifiedName"), str)
        and _is_final_class_path(entry.get("qualifiedName", ""))
    }
    result: dict[str, str] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") != "PROPERTY":
            continue
        qualified = entry.get("qualifiedName")
        if not isinstance(qualified, str) or not qualified.startswith("sage."):
            continue
        expressions = {
            signature.get("returnType", {}).get("expression")
            for signature in entry.get("signatures", [])
            if signature.get("returnType", {}).get("state") == "KNOWN"
        }
        if len(expressions) != 1:
            continue
        expression = next(iter(expressions))
        if isinstance(expression, str):
            arms = [arm.strip() for arm in expression.split(" | ")]
            if arms and all(arm in builtins or arm in class_names for arm in arms):
                result[qualified] = _union(
                    *[arm if arm in builtins else _quote(arm) for arm in arms]
                )
    return result


def _index_parameter_contracts(index: Path | None) -> dict[str, tuple[str | None, ...]]:
    """Load safe positional parameter types from unambiguous signatures."""
    payload = _read_index_payload(index)
    builtins = {
        "None", "NoReturn", "Self", "Iterator", "bool", "bytes", "bytearray",
        "complex", "dict", "float", "frozenset", "int", "list", "memoryview",
        "object", "range", "set", "slice", "str", "tuple", "type",
    }
    class_names = {
        entry.get("qualifiedName")
        for entry in payload.get("entries", [])
        if entry.get("kind") == "CLASS"
        and isinstance(entry.get("qualifiedName"), str)
        and _is_final_class_path(entry.get("qualifiedName", ""))
    }
    result: dict[str, tuple[str | None, ...]] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") not in {"FUNCTION", "METHOD"}:
            continue
        qualified = entry.get("qualifiedName")
        signatures = entry.get("signatures", [])
        if not isinstance(qualified, str) or not isinstance(signatures, list) or len(signatures) != 1:
            continue
        parameters = signatures[0].get("parameters", [])
        if not isinstance(parameters, list):
            continue
        normalized: list[str | None] = []
        for parameter in parameters:
            if not isinstance(parameter, dict) or parameter.get("variadic"):
                normalized.append(None)
                continue
            type_info = parameter.get("type", {})
            expression = type_info.get("expression") if isinstance(type_info, dict) else None
            if not isinstance(expression, str):
                normalized.append(None)
                continue
            arms = [arm.strip() for arm in expression.split(" | ")]
            if not arms or not all(arm in builtins or arm in class_names for arm in arms):
                normalized.append(None)
                continue
            normalized.append(_union(*[arm if arm in builtins else _quote(arm) for arm in arms]))
        if any(value is not None for value in normalized):
            result[qualified] = tuple(normalized)
    return result


def _index_overloads(
    index: Path | None,
) -> dict[str, tuple[tuple[tuple[str | None, ...], str], ...]]:
    """Load complete exact overloads for argument-sensitive dispatch."""
    payload = _read_index_payload(index)
    builtins = {
        "None", "NoReturn", "Self", "Iterator", "bool", "bytes", "bytearray",
        "complex", "dict", "float", "frozenset", "int", "list", "memoryview",
        "object", "range", "set", "slice", "str", "tuple", "type",
    }
    class_names = {
        entry.get("qualifiedName")
        for entry in payload.get("entries", [])
        if entry.get("kind") == "CLASS"
        and isinstance(entry.get("qualifiedName"), str)
        and _is_final_class_path(entry.get("qualifiedName", ""))
    }

    def normalize(expression: object) -> str | None:
        if not isinstance(expression, str):
            return None
        arms = [arm.strip() for arm in expression.split(" | ")]
        if not arms or not all(arm in builtins or arm in class_names for arm in arms):
            return None
        return _union(*[arm if arm in builtins else _quote(arm) for arm in arms])

    result: dict[str, tuple[tuple[tuple[str | None, ...], str], ...]] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") not in {"FUNCTION", "METHOD"}:
            continue
        qualified = entry.get("qualifiedName")
        signatures = entry.get("signatures", [])
        if not isinstance(qualified, str) or not isinstance(signatures, list) or len(signatures) < 2:
            continue
        overloads: list[tuple[tuple[str | None, ...], str]] = []
        valid = True
        for signature in signatures:
            if not isinstance(signature, dict):
                valid = False
                break
            return_info = signature.get("returnType", {})
            returned = normalize(return_info.get("expression") if isinstance(return_info, dict) else None)
            if not isinstance(return_info, dict) or return_info.get("state") != "KNOWN" or returned is None:
                valid = False
                break
            parameters = signature.get("parameters", [])
            if not isinstance(parameters, list):
                valid = False
                break
            normalized_parameters: list[str | None] = []
            for parameter in parameters:
                if not isinstance(parameter, dict) or parameter.get("variadic"):
                    normalized_parameters.append(None)
                    continue
                type_info = parameter.get("type", {})
                expression = type_info.get("expression") if isinstance(type_info, dict) else None
                normalized_parameters.append(normalize(expression))
            overloads.append((tuple(normalized_parameters), returned))
        if valid and overloads:
            result[qualified] = tuple(overloads)
    return result


def _index_constant_types(index: Path | None) -> dict[str, str]:
    """Expose concrete value types of indexed callable Sage constants."""
    payload = _read_index_payload(index)
    result: dict[str, str] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") != "CONSTANT":
            continue
        qualified = entry.get("qualifiedName")
        value_type = entry.get("valueType", {})
        expression = value_type.get("expression") if isinstance(value_type, dict) else None
        if not isinstance(qualified, str) or not isinstance(expression, str) or not expression.startswith("sage."):
            continue
        short = qualified.rsplit(".", 1)[-1]
        result.setdefault(short, expression)
        result.setdefault(qualified, expression)
    return result


def _factory_bindings(
    files: list[tuple[Path, str, ast.Module]],
    classes: set[str],
    known_contracts: dict[str, str],
    class_bases: dict[str, tuple[str, ...]],
) -> dict[str, str]:
    """Map ``Factory(...)`` assignments to their proven object contracts.

    Sage exposes most public constructors as module-level instances of
    ``UniqueFactory`` (for example ``EllipticCurve`` and ``FiniteField``), so
    generated stubs represent them as CONSTANTs rather than functions.  The
    factory class's ``create_object`` method is the source-level contract for
    the callable instance.  Recording that relation once lets every imported
    use site follow the concrete implementation union without a constructor
    name allow-list.
    """
    def is_unique_factory(owner: str) -> bool:
        pending = [owner]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            if current.rsplit(".", 1)[-1] == "UniqueFactory":
                return True
            pending.extend(class_bases.get(current, ()))
        return False

    bindings: dict[str, str] = {}
    for path, module, tree in files:
        imports = _imports(tree, module, package_module=path.name == "__init__.py")
        for statement in tree.body:
            if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
                continue
            called = _dotted(statement.value.func)
            if not called:
                continue
            bits = called.split(".")
            resolved = imports.get(bits[0])
            if resolved is None:
                resolved = f"{module}.{bits[0]}"
            if len(bits) > 1:
                resolved = ".".join([resolved, *bits[1:]])
            if resolved not in classes:
                continue
            # ``create_object`` is also used by ordinary Sage classes as an
            # internal helper. Only classes proven to inherit UniqueFactory
            # expose a callable factory instance at module scope.
            if not is_unique_factory(resolved):
                continue
            result = _safe_factory_result(known_contracts.get(f"{resolved}.create_object"))
            if result is None:
                continue
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    bindings[f"{module}.{target.id}"] = _FACTORY_RESULT_PREFIX + result
    # Short names are used only when one defining module owns the binding;
    # colliding factory names remain qualified and therefore fail closed.
    short_values: dict[str, set[str]] = {}
    for qualified, value in bindings.items():
        short_values.setdefault(qualified.rsplit(".", 1)[-1], set()).add(value)
    for short, values in short_values.items():
        if len(values) == 1:
            bindings[short] = next(iter(values))
    return bindings


def infer(
    source_root: Path,
    known_contracts: dict[str, str] | None = None,
    generic_contracts: dict[str, tuple[str, tuple[int, ...]]] | None = None,
    known_classes: set[str] | None = None,
    class_aliases: dict[str, str] | None = None,
    known_properties: dict[str, str] | None = None,
    known_parameters: dict[str, tuple[str | None, ...]] | None = None,
    known_overloads: dict[str, tuple[tuple[tuple[str | None, ...], str], ...]] | None = None,
    known_constants: dict[str, str] | None = None,
    known_bases: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, str]:
    files: list[tuple[Path, str, ast.Module]] = []
    for path in sorted(source_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        files.append((path, _module_name(path, source_root), tree))
    classes = _class_names(files)
    source_bases = _class_bases(files, classes)
    indexed_bases = known_bases or {}
    # Add only absent/indexed edges.  Source-resolved bases remain first in
    # MRO order, while Cython/extension parents fill the gaps for delegated
    # member lookup.  Conflicting paths are handled by the existing
    # unique-contract checks and consequently remain unresolved.
    class_bases = {
        owner: tuple(
            dict.fromkeys((*source_bases.get(owner, ()), *indexed_bases.get(owner, ())))
        )
        for owner in set(source_bases) | set(indexed_bases)
        # Keep indexed-only owners as well: a source class may inherit through
        # several extension-class layers before reaching ``Parent``.  These
        # edges are used solely for member lookup and never become a public
        # return type by themselves.
        if owner in classes or owner in indexed_bases
    }
    external_contracts = known_contracts or {}
    external_generic_contracts = generic_contracts or {}
    external_classes = known_classes or set()
    external_class_aliases = class_aliases or {}
    external_properties = known_properties or {}
    external_parameters = known_parameters or {}
    external_overloads = known_overloads or {}
    external_constants = known_constants or {}
    # Merge source-defined factory instances with indexed constant types.
    # This is internal evidence only; marker values are consumed by the
    # analyzer and never emitted as public return expressions.
    external_constants = dict(external_constants)
    external_constants.update(_factory_bindings(files, classes, external_contracts, class_bases))
    factory_constants = {
        name: value
        for name, value in external_constants.items()
        if isinstance(value, str) and value.startswith(_FACTORY_RESULT_PREFIX)
    }
    module_globals = _module_globals(
        files,
        classes,
        external_contracts,
        external_generic_contracts,
        external_classes,
        external_class_aliases,
        external_properties,
        external_constants,
    )
    class_attributes = _class_attributes(
        files,
        classes,
        module_globals,
        external_contracts,
        external_generic_contracts,
        external_classes,
        external_class_aliases,
        external_properties,
        external_parameters,
        factory_constants,
    )
    class_methods = _class_methods(files)
    class_attributes = _inherit_class_attributes(class_attributes, class_bases)
    contracts: dict[str, str] = {}
    # Keep one mutable lookup table for the whole pass.  Rebuilding a copy of
    # the large generated index for every function would turn fixed-point
    # propagation into quadratic work; source proofs are inserted here as
    # they become available and shadow the external seed naturally.
    visible_contracts = dict(external_contracts)
    visible_properties = dict(external_properties)

    def publish(qualified: str, annotation: str, *, property_node: bool = False) -> None:
        contracts[qualified] = annotation
        visible_contracts[qualified] = annotation
        if property_node:
            visible_properties[qualified] = annotation
    function_nodes: list[tuple[str, str | None, ast.FunctionDef | ast.AsyncFunctionDef, dict[str, str]]] = []
    for path, module, tree in files:
        imports = _imports(tree, module, package_module=path.name == "__init__.py")

        def visit(node: ast.AST, owner: str | None = None) -> None:
            if isinstance(node, ast.ClassDef):
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                for child in node.body:
                    visit(child, qualified)
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Nested local functions are not public stub members.
                body = list(node.body)
                returns, has_yield = _returns(body)
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                function_imports = dict(imports)
                local_imports, ambiguous_imports = _imports_from_body(
                    body, module, package_module=path.name == "__init__.py"
                )
                for name in ambiguous_imports:
                    function_imports.pop(name, None)
                function_imports.update(local_imports)
                function_nodes.append((qualified, owner, node, function_imports))
                property_node = _is_property_node(node)
                if has_yield:
                    generator_type = "Iterator"
                    yield_nodes = _yields(body)
                    if yield_nodes:
                        analyzer = _FunctionAnalyzer(
                            module,
                            function_imports,
                            classes,
                            owner,
                            class_attributes,
                            module_globals.get(module),
                            visible_contracts,
                            external_generic_contracts,
                            external_classes,
                            external_class_aliases,
                            visible_properties,
                            external_parameters,
                            class_bases,
                            external_overloads,
                            external_constants,
                            class_methods=class_methods,
                        )
                        _local_types(body, analyzer)
                        analyzer.bind_parameters(node)
                        _loop_types(body, analyzer)
                        analyzer.bind_external_parameters(qualified, node)
                        yielded: list[str | None] = []
                        for value, from_iterator in yield_nodes:
                            inferred = analyzer.expr_type(value)
                            if from_iterator:
                                inferred = _generic_element(inferred)
                            yielded.append(_public_type(inferred))
                        if yielded and all(value is not None for value in yielded):
                            generator_type = f"Iterator[{_union(*[value for value in yielded if value is not None])}]"
                    publish(qualified, generator_type, property_node=property_node)
                elif _always_raises(body):
                    publish(qualified, "NoReturn", property_node=property_node)
                elif returns:
                    analyzer = _FunctionAnalyzer(
                        module,
                        function_imports,
                        classes,
                        owner,
                        class_attributes,
                        module_globals.get(module),
                        visible_contracts,
                        external_generic_contracts,
                        external_classes,
                        external_class_aliases,
                        visible_properties,
                        external_parameters,
                        class_bases,
                        external_overloads,
                        external_constants,
                        class_methods=class_methods,
                    )
                    _local_types(body, analyzer)
                    analyzer.bind_parameters(node)
                    _loop_types(body, analyzer)
                    analyzer.bind_external_parameters(qualified, node)
                    source_annotation = analyzer.annotation_type(node.returns) if node.returns is not None else None
                    if source_annotation is not None:
                        publish(qualified, source_annotation, property_node=property_node)
                    elif returns and (
                        not _may_fall_through(body) or _implicit_none_is_safe(body)
                    ):
                        inferred = [_public_type(analyzer.expr_type(r.value)) for r in returns]
                        if _may_fall_through(body) and _implicit_none_is_safe(body):
                            inferred.append("None")
                        # A non-fallthrough body reaches one of these explicit
                        # returns.  Preserve every independently proven
                        # expression shape as an exact union instead of
                        # discarding a parameter/branch-sensitive factory.
                        # ``expr_type`` is deliberately fail-closed, so an
                        # unresolved arm still prevents publication.
                        if inferred and all(value is not None for value in inferred):
                            unique = list(dict.fromkeys(inferred))
                            publish(
                                qualified,
                                unique[0] if len(unique) == 1 else _union(*unique),
                                property_node=property_node,
                            )
                elif not returns:
                    # Python's implicit fall-through value is exactly None.
                    # This is safe for functions with no explicit return at
                    # all (generators were handled above); a function that
                    # raises on some paths still has None as its successful
                    # return value.
                    publish(qualified, "None", property_node=property_node)
                return
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, owner)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visit(child, owner)

        for node in tree.body:
            visit(node)

    # Re-evaluate stable receiver attributes after direct method contracts are
    # known.  For example, ``__init__`` may assign ``self._value = self.value``
    # where ``value`` was proven above.  Conflicting or dynamic assignments
    # remain omitted by ``_class_attributes``.
    class_attributes = _class_attributes(
        files,
        classes,
        module_globals,
        visible_contracts,
        external_generic_contracts,
        external_classes,
        external_class_aliases,
        visible_properties,
        external_parameters,
        factory_constants,
    )
    class_attributes = _inherit_class_attributes(class_attributes, class_bases)

    # Make uniquely inherited source contracts visible to child receivers.
    # This is safe only when the child does not define an override and every
    # statically resolved base agrees on the same return expression.
    defined_functions = {qualified for qualified, _, _, _ in function_nodes}
    for _ in range(len(class_bases) + 1):
        added_inherited = 0
        methods_by_owner: dict[str, dict[str, str]] = {}
        for qualified, value in contracts.items():
            owner, _, method = qualified.rpartition(".")
            if owner in classes:
                methods_by_owner.setdefault(owner, {})[method] = value
        for child, parent_names in class_bases.items():
            if not parent_names:
                continue
            method_names = set().union(*(set(methods_by_owner.get(parent, {})) for parent in parent_names))
            for method in method_names:
                child_name = f"{child}.{method}"
                if child_name in defined_functions or child_name in contracts:
                    continue
                inherited = {methods_by_owner.get(parent, {}).get(method) for parent in parent_names}
                if len(inherited) == 1 and None not in inherited:
                    publish(child_name, next(iter(inherited)))
                    added_inherited += 1
        if not added_inherited:
            break

    # Resolve wrappers after direct contracts are known.  This remains
    # parameter-independent: a function that returns ``self.helper()`` or a
    # same-module helper inherits only that helper's already-proved contract.
    # Iterate to a fixed point so short chains are covered without a whitelist.
    for _ in range(len(function_nodes) + 1):
        added = 0
        for qualified, owner, node, imports in function_nodes:
            if qualified in contracts or not node.body:
                continue
            returns, has_yield = _returns(node.body)
            if has_yield or not returns:
                continue
            if _may_fall_through(list(node.body)) and not _implicit_none_is_safe(list(node.body)):
                continue
            module = owner.rsplit(".", 1)[0] if owner else qualified.rsplit(".", 1)[0]
            analyzer = _FunctionAnalyzer(
                module,
                imports,
                classes,
                owner,
                class_attributes,
                module_globals.get(module),
                visible_contracts,
                external_generic_contracts,
                external_classes,
                external_class_aliases,
                visible_properties,
                external_parameters,
                class_bases,
                external_overloads,
                external_constants,
                class_methods=class_methods,
            )
            _local_types(list(node.body), analyzer)
            analyzer.bind_parameters(node)
            _loop_types(list(node.body), analyzer)
            analyzer.bind_external_parameters(qualified, node)
            inferred = [_public_type(analyzer.expr_type(result.value)) for result in returns]
            if _may_fall_through(list(node.body)) and _implicit_none_is_safe(list(node.body)):
                inferred.append("None")
            if inferred and all(value is not None for value in inferred):
                unique = list(dict.fromkeys(inferred))
                publish(
                    qualified,
                    unique[0] if len(unique) == 1 else _union(*unique),
                    property_node=_is_property_node(node),
                )
                added += 1
        if not added:
            break
    return contracts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--index", type=Path, help="Optional generated index supplying exact receiver-member contracts.")
    args = parser.parse_args()
    index = args.index.resolve() if args.index else None
    known_contracts = _index_contracts(index)
    # Keep factory filtering scoped to ``create_object``. Do not broaden the
    # general index bridge: unrelated source wrappers returning a structural
    # class must remain UNKNOWN rather than inheriting a guessed leaf type.
    known_contracts.update(_index_factory_contracts(index))
    contracts = infer(
        args.source_root.resolve(),
        known_contracts,
        _index_generic_contracts(index),
        _index_classes(index),
        _index_class_aliases(index),
        _index_properties(index),
        _index_parameter_contracts(index),
        _index_overloads(index),
        _index_constant_types(index),
        _index_class_bases(index),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contracts, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sourceFiles": len(list(args.source_root.rglob('*.py'))), "contracts": len(contracts)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
