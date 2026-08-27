from sage.modules.free_module_element import FreeModuleElement


class Matrix:
    def solve_right(self, rhs) -> FreeModuleElement | Matrix: ...
