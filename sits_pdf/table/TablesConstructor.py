from ..common import constants
from ..common.Element import Element
from ..common.Collection import Collection
from ..layout.Blocks import Blocks
from ..shape.Shapes import Shapes
from ..text.Lines import Lines
from .TableStructure import TableStructure
from .Border import Border, Borders
from .Cell import Cell


class TablesConstructor:
    def __init__(self, parent):
        self._parent = parent
        self._blocks = parent.blocks
        self._shapes = parent.shapes

    def lattice_tables(
        self,
        connected_border_tolerance: float,
        min_border_clearance: float,
        max_border_width: float,
    ):
        if not self._shapes:
            return

        def remove_overlap(instances: list):
            fun = lambda a, b: a.bbox.contains(b.bbox) or b.bbox.contains(a.bbox)
            groups = Collection(instances).group(fun)
            unique_groups = []
            for group_instances in groups:
                if len(group_instances) == 1:
                    instance = group_instances[0]
                else:
                    sorted_group = sorted(
                        group_instances, key=lambda instance: instance.bbox.get_area()
                    )
                    instance = sorted_group[-1]

                unique_groups.append(instance)

            return unique_groups

        grouped_strokes = self._shapes.table_strokes.group_by_connectivity(
            dx=connected_border_tolerance, dy=connected_border_tolerance
        )
        grouped_strokes = remove_overlap(grouped_strokes)
        fills = self._shapes.table_fillings
        tables = Blocks()
        settings = {
            "min_border_clearance": min_border_clearance,
            "max_border_width": max_border_width,
        }
        for strokes in grouped_strokes:
            group_fills = fills.contained_in_bbox(strokes.bbox)
            table = (
                TableStructure(strokes, **settings).parse(group_fills).to_table_block()
            )
            if table:
                table.set_lattice_table_block()
                tables.append(table)
        self._blocks.assign_to_tables(tables)
        self._shapes.assign_to_tables(tables)

    def stream_tables(
        self,
        min_border_clearance: float,
        max_border_width: float,
        line_separate_threshold: float,
    ):
        table_strokes = self._shapes.table_strokes
        table_fillings = self._shapes.table_fillings
        tables_lines = self._blocks.collect_stream_lines(
            table_fillings, line_separate_threshold
        )
        X0, Y0, X1, Y1 = self._parent.bbox

        def top_bottom_boundaries(y0, y1):
            y_lower, y_upper = Y0, Y1
            for block in self._blocks:
                if block.bbox.y1 < y0:
                    y_lower = block.bbox.y1
                if block.bbox.y0 > y1:
                    y_upper = block.bbox.y0
                    break
            return y_lower, y_upper

        tables = Blocks()
        settings = {
            "min_border_clearance": min_border_clearance,
            "max_border_width": max_border_width,
        }

        for table_lines in tables_lines:
            if not table_lines:
                continue
            x0 = min([rect.bbox.x0 for rect in table_lines])
            y0 = min([rect.bbox.y0 for rect in table_lines])
            x1 = max([rect.bbox.x1 for rect in table_lines])
            y1 = max([rect.bbox.y1 for rect in table_lines])
            y0_margin, y1_margin = top_bottom_boundaries(y0, y1)
            inner_bbox = (x0, y0, x1, y1)
            outer_bbox = (X0, y0_margin, X1, y1_margin)
            outer_borders = TablesConstructor._outer_borders(inner_bbox, outer_bbox)
            rect = Element().update_bbox(outer_bbox)
            explicit_strokes = table_strokes.contained_in_bbox(rect.bbox)
            explicit_shadings, _ = table_fillings.split_with_intersection(
                rect.bbox, threshold=constants.FACTOR_A_FEW
            )
            if not (
                explicit_shadings or explicit_strokes
            ) and TablesConstructor._is_simple_structure(table_lines):
                continue
            strokes = self._stream_strokes(
                table_lines, outer_borders, explicit_strokes, explicit_shadings
            )
            if not strokes:
                continue
            strokes.sort_in_reading_order()
            table = (
                TableStructure(strokes, **settings)
                .parse(explicit_shadings)
                .to_table_block()
            )
            if (
                isinstance(self._parent, Cell)
                and table.num_cols * table.num_rows == 1
                and table[0][0].bg_color is None
            ):
                continue

            table.set_stream_table_block()
            tables.append(table)
        self._blocks.assign_to_tables(tables)
        self._shapes.assign_to_tables(tables)

    @staticmethod
    def _is_simple_structure(lines: Lines):
        num = len(lines.group_by_columns())
        if num == 1:
            return True
        elif num == 2:
            return len(lines.group_by_physical_rows()) == len(lines.group_by_rows())
        else:
            return False

    @staticmethod
    def _stream_strokes(
        lines: Lines,
        outer_borders: tuple,
        explicit_strokes: Shapes,
        explicit_shadings: Shapes,
    ):
        borders = Borders()
        borders.extend(outer_borders)
        inner_borders = TablesConstructor._inner_borders(lines, outer_borders)
        borders.extend(inner_borders)
        borders.finalize(explicit_strokes, explicit_shadings)
        res = Shapes()
        for border in borders:
            res.append(border.to_stroke())

        return res

    @staticmethod
    def _outer_borders(inner_bbox, outer_bbox):
        x0, y0, x1, y1 = inner_bbox
        X0, Y0, X1, Y1 = outer_bbox
        top = Border("HT", border_range=(Y0, y0), reference=False)
        bottom = Border("HB", border_range=(y1, Y1), reference=False)
        left = Border("VL", border_range=(X0, x0), reference=False)
        right = Border("VR", border_range=(x1, X1), reference=False)
        top.set_boundary_borders((left, right))
        bottom.set_boundary_borders((left, right))
        left.set_boundary_borders((top, bottom))
        right.set_boundary_borders((top, bottom))

        return (top, bottom, left, right)

    @staticmethod
    def _inner_borders(lines: Lines, outer_borders: tuple):
        cols_lines = lines.group_by_columns()
        group_lines = [
            col_lines.group_by_rows(factor=constants.FACTOR_A_FEW)
            for col_lines in cols_lines
        ]
        col_num = len(cols_lines)
        is_reference = col_num <= 2
        if col_num >= 2:
            for border in outer_borders:
                border.is_reference = False
        borders = Borders()
        right = None
        TOP, BOTTOM, LEFT, RIGHT = outer_borders
        for i in range(col_num):
            left = LEFT if i == 0 else right
            if i == col_num - 1:
                right = RIGHT
            else:
                x0 = cols_lines[i].bbox.x1
                x1 = cols_lines[i + 1].bbox.x0
                right = Border(
                    border_type="VI",
                    border_range=(x0, x1),
                    borders=(TOP, BOTTOM),
                    reference=False,
                )
                borders.append(right)
            rows_lines = group_lines[i]
            row_num = len(rows_lines)
            if row_num == 1:
                continue
            bottom = None
            for j in range(row_num):
                top = TOP if j == 0 else bottom
                if j == row_num - 1:
                    bottom = BOTTOM
                else:
                    y0 = rows_lines[j].bbox.y1
                    y1 = rows_lines[j + 1].bbox.y0
                    bottom = Border(
                        border_type="HI",
                        border_range=(y0, y1),
                        borders=(left, right),
                        reference=is_reference,
                    )
                    borders.append(bottom)
                borders_ = TablesConstructor._inner_borders(
                    rows_lines[j], (top, bottom, left, right)
                )
                borders.extend(borders_)

        return borders
