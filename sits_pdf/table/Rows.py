from .Row import Row
from ..common.Collection import ElementCollection


class Rows(ElementCollection):
    def restore(self, raws: list):
        for raw in raws:
            row = Row(raw)
            self.append(row)
        return self
