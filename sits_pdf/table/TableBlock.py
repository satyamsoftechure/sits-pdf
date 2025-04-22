from .Row import Row
from .Rows import Rows
from ..common.Block import Block
from ..common import docx


class TableBlock(Block):
    def __init__(self, raw: dict = None):
        if raw is None:
            raw = {}
        super().__init__(raw)
        self._rows = Rows(parent=self).restore(raw.get("rows", []))
        self.set_lattice_table_block()

    def __getitem__(self, idx):
        try:
            row = self._rows[idx]
        except IndexError:
            msg = f"Row index {idx} out of range"
            raise IndexError(msg)
        else:
            return row

    def __iter__(self):
        return (row for row in self._rows)

    def __len__(self):
        return len(self._rows)

    @property
    def num_rows(self):
        return len(self._rows)

    @property
    def num_cols(self):
        return len(self._rows[0]) if self.num_rows else 0

    @property
    def text(self):
        return [[cell.text for cell in row] for row in self._rows]

    @property
    def outer_bbox(self):
        x0, y0, x1, y1 = self.bbox
        w0_top, w0_right, w0_bottom, w0_left = self[0][0].border_width
        w1_top, w1_right, w1_bottom, w1_left = self[-1][-1].border_width
        return (
            x0 - w0_left / 2.0,
            y0 - w0_top / 2.0,
            x1 + w1_right / 2.0,
            y1 + w1_bottom / 2.0,
        )

    def append(self, row: Row):
        self._rows.append(row)

    def store(self):
        res = super().store()
        res.update({"rows": self._rows.store()})
        return res

    def assign_blocks(self, blocks: list):
        for row in self._rows:
            for cell in row:
                if not cell:
                    continue
                cell.assign_blocks(blocks)

    def assign_shapes(self, shapes: list):
        for row in self._rows:
            for cell in row:
                if not cell:
                    continue
                cell.assign_shapes(shapes)

    def parse(self, **settings):
        for row in self._rows:
            for cell in row:
                if not cell:
                    continue
                cell.parse(**settings)

    def plot(self, page):
        for row in self._rows:
            for cell in row:
                if not cell:
                    continue
                cell.plot(page)

    def make_docx(self, table):
        docx.indent_table(table, self.left_space)
        for idx_row in range(len(table.rows)):
            self._rows[idx_row].make_docx(table, idx_row)
