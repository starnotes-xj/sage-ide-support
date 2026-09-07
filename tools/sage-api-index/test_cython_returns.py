import tempfile
import unittest
import json
from pathlib import Path

from infer_cython_returns import declarations, infer


class CythonReturnTest(unittest.TestCase):
    def test_scalar_locals_require_all_paths_and_ignore_python_assignments(self):
        source = '''
def count(x):
    cdef unsigned long n = 0
    cdef object temporary
    for item in x:
        n += item
    return n
def mixed(flag):
    cdef int n = 3
    if flag:
        return n
    return None
def fallthrough(flag):
    cdef int n = 0
    if flag:
        return n
def dynamic(x):
    n = x
    return n
@unknown_decorator
def wrapped():
    cdef int n = 0
    return n
'''
        self.assertEqual([(q, t) for q, t, _ in declarations(source)], [('count', 'int')])

    def test_wrapper_conversion_and_scopes(self):
        source = '''
cpdef unsigned long count(object x):
    return x
cdef class Element:
    cpdef bint positive(self):
        return 1
    cpdef double norm(self):
        return 0.5
    cpdef void mutate(self):
        pass
'''
        self.assertEqual([(q, t) for q, t, _ in declarations(source)],
                         [('count', 'int'), ('Element.positive', 'bool'),
                          ('Element.norm', 'float'), ('Element.mutate', 'None')])

    def test_comments_docs_pointers_fused_and_private_are_not_contracts(self):
        source = '''
"""
cpdef int fake():
    pass
"""
# cpdef int also_fake():
cpdef char* pointer():
    pass
cpdef number fused():
    pass
cdef int private():
    pass
cpdef object dynamic():
    pass
if condition:
    cpdef int conditional():
        pass
'''
        self.assertEqual(declarations(source), [])

    def test_def_unconditional_raise_is_noreturn_but_conditional_raise_is_unknown(self):
        source = '''
def abstract_hook(self):
    """An abstract protocol hook."""
    raise NotImplementedError("subclass required")
def conditional_hook(self, enabled):
    if enabled:
        raise NotImplementedError
    return self
class Base:
    def class_hook(self):
        """A class-level abstract hook."""
        raise NotImplementedError
'''
        self.assertEqual(
            [(q, t) for q, t, _ in declarations(source)],
            [('abstract_hook', 'NoReturn'), ('Base.class_hook', 'NoReturn')],
        )

    def test_def_trivial_return_is_syntax_exact_and_branches_are_rejected(self):
        source = '''
def identity(self):
    """Return the receiver unchanged."""
    return self
def empty_payload():
    return []
def conditional(flag):
    if flag:
        return []
    return {}
'''
        self.assertEqual(
            [(q, t) for q, t, _ in declarations(source)],
            [('identity', 'Self'), ('empty_payload', 'list')],
        )

    def test_def_trivial_constructor_uses_builtin_or_unique_class_contract(self):
        source = '''
def as_integer(value):
    return Integer(value)
def as_range(value):
    return range(value)
def dynamic_factory(value):
    return factory(value)
'''
        self.assertEqual(
            [(q, t) for q, t, _ in declarations(source, {'Integer': 'sage.rings.integer.Integer'})],
            [('as_integer', "'sage.rings.integer.Integer'"), ('as_range', 'range')],
        )

    def test_abc_constructor_name_resolves_only_documented_unique_subclass(self):
        source = '''
def make_complex(prec):
    return ComplexField(prec)
def make_dynamic(value):
    return Other(value)
'''
        index = {
            'entries': [
                {
                    'qualifiedName': 'sage.rings.abc.ComplexField',
                    'kind': 'CLASS',
                    'documentation': {
                        'summary': 'Abstract base class for :class:`~sage.rings.complex_mpfr.ComplexField_class`.',
                        'body': 'By design, there is a unique direct subclass.',
                    },
                },
                {
                    'qualifiedName': 'sage.rings.complex_mpfr.ComplexField_class',
                    'kind': 'CLASS',
                    'documentation': {'summary': 'Concrete complex field.'},
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'index.json'
            path.write_text(json.dumps(index), encoding='utf-8')
            root = Path(tmp) / 'sage'
            root.mkdir()
            (root / 'sample.pyx').write_text(source, encoding='utf-8')
            contracts, _ = infer(root, path)
        self.assertEqual(
            contracts['sage.sample.make_complex'],
            "'sage.rings.complex_mpfr.ComplexField_class'",
        )

    def test_direct_receiver_call_uses_one_stable_index_return(self):
        source = '''
class Worker:
    def helper(self):
        return None
    def wrapper(self):
        return self.helper()
    def dynamic(self):
        return self.other()
'''
        index = {
            'entries': [
                {
                    'qualifiedName': 'sage.sample.Worker.helper',
                    'kind': 'METHOD',
                    'signatures': [{'returnType': {'state': 'KNOWN', 'expression': 'list'}}],
                },
                {
                    'qualifiedName': 'sage.sample.Worker.other',
                    'kind': 'METHOD',
                    'signatures': [{'returnType': {'state': 'UNKNOWN'}}],
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'index.json'
            path.write_text(json.dumps(index), encoding='utf-8')
            root = Path(tmp) / 'sage'
            root.mkdir()
            (root / 'sample.pyx').write_text(source, encoding='utf-8')
            contracts, _ = infer(root, path)
        self.assertEqual(contracts['sage.sample.Worker.wrapper'], 'list')
        self.assertNotIn('sage.sample.Worker.dynamic', contracts)

    def test_direct_receiver_property_uses_one_stable_index_return(self):
        source = '''
class Worker:
    def payload(self):
        return self.value
    def dynamic(self):
        return self.other
'''
        index = {
            'entries': [
                {
                    'qualifiedName': 'sage.sample.Worker.value',
                    'kind': 'PROPERTY',
                    'signatures': [{'returnType': {'state': 'KNOWN', 'expression': 'tuple'}}],
                },
                {
                    'qualifiedName': 'sage.sample.Worker.other',
                    'kind': 'PROPERTY',
                    'signatures': [{'returnType': {'state': 'UNKNOWN'}}],
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'index.json'
            path.write_text(json.dumps(index), encoding='utf-8')
            root = Path(tmp) / 'sage'
            root.mkdir()
            (root / 'sample.pyx').write_text(source, encoding='utf-8')
            contracts, _ = infer(root, path)
        self.assertEqual(contracts['sage.sample.Worker.payload'], 'tuple')
        self.assertNotIn('sage.sample.Worker.dynamic', contracts)

    def test_pxd_pyx_conflict_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'sage'
            root.mkdir()
            (root / 'sample.pyx').write_text('cpdef int value():\n    return 1\n', encoding='utf-8')
            (root / 'sample.pxd').write_text('cpdef double value()\n', encoding='utf-8')
            contracts, evidence = infer(root)
            self.assertNotIn('sage.sample.value', contracts)
            self.assertEqual(len(evidence), 2)
            self.assertEqual(len(evidence[0]['sha256']), 64)

    def test_python_and_unique_extension_class_declarations(self):
        source = '''
cpdef inline tuple pair():
    return ()
cpdef list values():
    return []
cpdef UniqueElement element():
    return None
cpdef AmbiguousElement ambiguous():
    return None
'''
        self.assertEqual(
            [(q, t) for q, t, _ in declarations(source, {
                'UniqueElement': 'sage.sample.UniqueElement',
            })],
            [('pair', 'tuple'), ('values', 'list'), ('element', "'sage.sample.UniqueElement'")],
        )

        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / 'index.json'
            index.write_text(json.dumps({'entries': [
                {'qualifiedName': 'sage.sample.UniqueElement', 'kind': 'CLASS'},
                {'qualifiedName': 'sage.one.AmbiguousElement', 'kind': 'CLASS'},
                {'qualifiedName': 'sage.two.AmbiguousElement', 'kind': 'CLASS'},
            ]}), encoding='utf-8')
            root = Path(tmp) / 'sage'
            root.mkdir()
            (root / 'sample.pyx').write_text('cpdef UniqueElement element():\n    return None\n', encoding='utf-8')
            contracts, _ = infer(root, index)
            self.assertEqual(contracts['sage.sample.element'], "'sage.sample.UniqueElement'")


if __name__ == '__main__':
    unittest.main()
