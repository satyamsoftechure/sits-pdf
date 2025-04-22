from .Cell import Cell
from ..common.Collection import ElementCollection


class Cells(ElementCollection):
    def restore(self, raws:list):
        for raw in raws:
            cell = Cell(raw)
            self.append(cell)
        return self
    
    def append(self, cell:Cell):
        self._instances.append(cell)
        self._update_bbox(cell)
        cell.parent = self._parent
