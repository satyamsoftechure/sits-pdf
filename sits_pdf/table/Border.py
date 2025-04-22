from collections import defaultdict
from ..shape.Shapes import Shapes
from ..shape.Shape import Stroke
from ..common import constants
from ..common.share import RectType, rgb_value
from ..common.Collection import BaseCollection


class Border:
    def __init__(
        self,
        border_type="hi",
        border_range: tuple = None,
        borders: tuple = None,
        reference: bool = False,
    ):
        self.border_type = border_type.upper()
        self.finalized = False
        self.is_reference = reference
        self.set_border_range(border_range)
        self.set_boundary_borders(borders)
        self._value = None
        self.width = constants.HIDDEN_W_BORDER
        self.color = 0

    @property
    def is_horizontal(self):
        return "H" in self.border_type

    @property
    def is_vertical(self):
        return "V" in self.border_type

    @property
    def is_top(self):
        return "T" in self.border_type

    @property
    def is_bottom(self):
        return "B" in self.border_type

    @property
    def value(self):
        if self.finalized:
            return self._value
        else:
            avg = (self.LRange + self.URange) / 2.0
            if self.is_top:
                return max(self.URange - 3, avg)
            elif self.is_bottom:
                return min(self.LRange + 3, avg)
            else:
                return avg

    @property
    def centerline(self):
        if self.is_horizontal:
            return (self._LBorder.value, self.value, self._UBorder.value, self.value)
        else:
            return (self.value, self._LBorder.value, self.value, self._UBorder.value)

    def is_valid(self, value: float):
        return (
            (self.LRange - constants.MINOR_DIST)
            <= value
            <= (self.URange + constants.MINOR_DIST)
        )

    def set_border_range(self, border_range: tuple = None):
        if border_range:
            x0, x1 = border_range
        else:
            x0, x1 = -9999, 9999
        self.LRange: float = x0
        self.URange: float = x1
        return self

    def set_boundary_borders(self, borders: tuple = None):
        if borders:
            lower_border, upper_border = borders
        else:
            lower_border, upper_border = None, None
        self._LBorder: Border = lower_border
        self._UBorder: Border = upper_border
        return self

    def get_boundary_borders(self):
        return (self._LBorder, self._UBorder)

    def finalize_by_value(self, value: float):
        if self.finalized or not self.is_valid(value):
            return False

        self._value = value
        self.finalized = True
        self.is_reference = False

        return True

    def finalize_by_stroke(self, stroke: Stroke):
        if self.is_horizontal:
            low_pos, upper_pos = stroke.x0, stroke.x1
            value = stroke.y0
        else:
            low_pos, upper_pos = stroke.y0, stroke.y1
            value = stroke.x0
        if not self.is_valid(value):
            return
        if low_pos > self._LBorder.URange and upper_pos < self._UBorder.LRange:
            return
        if self.finalize_by_value(value):
            self.color = stroke.color
            self.width = stroke.width
            stroke.type = RectType.BORDER
        self._LBorder.finalize_by_value(low_pos)
        self._UBorder.finalize_by_value(upper_pos)

    def to_stroke(self):
        if self.is_reference:
            return None

        stroke = Stroke({"color": self.color, "width": self.width}).update_bbox(
            self.centerline
        )
        stroke.type = RectType.BORDER
        return stroke


class Borders(BaseCollection):
    def finalize(self, strokes: Shapes, fills: Shapes):
        self._add_full_dummy_borders()
        self._finalize_by_strokes(strokes)
        tmp_strokes = []
        for fill in fills:
            if fill.is_determined or fill.color == rgb_value((1, 1, 1)):
                continue

            x0, y0, x1, y1 = fill.bbox
            tmp_strokes.extend(
                [
                    Stroke().update_bbox((x0, y0, x1, y0)),
                    Stroke().update_bbox((x0, y1, x1, y1)),
                    Stroke().update_bbox((x0, y0, x0, y1)),
                    Stroke().update_bbox((x1, y0, x1, y1)),
                ]
            )
        self._finalize_by_strokes(tmp_strokes)
        borders = list(
            filter(
                lambda border: not (border.finalized or border.is_reference),
                self._instances,
            )
        )
        h_borders = list(
            filter(
                lambda border: border.is_horizontal
                and not (border.is_top or border.is_bottom),
                borders,
            )
        )
        self._finalize_by_layout(h_borders)
        v_borders = list(filter(lambda border: border.is_vertical, borders))
        self._finalize_by_layout(v_borders)

    def _finalize_by_strokes(self, strokes: list):
        """Finalize borders by explicit strokes."""
        for stroke in strokes:
            if stroke.is_determined:
                continue

            for border in self._instances:
                if stroke.horizontal != border.is_horizontal:
                    continue

                border.finalize_by_stroke(stroke)

    @staticmethod
    def _finalize_by_layout(borders: list):
        x_points = set()
        for border in borders:
            x_points.add(border.LRange)
            x_points.add(border.URange)

        x_points = list(x_points)
        x_points.sort()
        x_status = []
        for i in range(len(x_points) - 1):
            x = (x_points[i] + x_points[i + 1]) / 2.0
            s = [int(border.is_valid(x)) for border in borders]
            x_status.append((x, s))
        x_status.sort(key=lambda item: sum(item[1]), reverse=True)
        num = len(borders)
        current_status = [0] * num
        for x, status in x_status:
            if sum(current_status) == num:
                break
            duplicated = sum([c1 * c2 for c1, c2 in zip(current_status, status)])
            if duplicated:
                continue
            current_status = [c1 + c2 for c1, c2 in zip(current_status, status)]
            for border, border_status in zip(borders, status):
                if border_status:
                    border.finalize_by_value(int(x))

    def _add_full_dummy_borders(self):
        h_borders = list(filter(lambda border: border.is_horizontal, self._instances))
        v_borders = list(filter(lambda border: border.is_vertical, self._instances))
        raw_borders_map = defaultdict(list)
        h_range_set = set()
        for border in h_borders:
            h_range = (border.LRange, border.URange)
            h_range_set.add(h_range)
            raw_borders_map[border.get_boundary_borders].append(h_range)
        v_borders.sort(key=lambda border: border.value)
        for i in range(len(v_borders) - 1):
            left, right = v_borders[i], v_borders[i + 1]
            left_l_border, left_u_border = left.get_boundary_borders()
            right_l_border, right_u_border = right.get_boundary_borders()
            if left_l_border != right_l_border and left_u_border != right_u_border:
                continue
            lower_bound = max(left_l_border.LRange, right_l_border.LRange)
            upper_bound = min(left_u_border.URange, right_u_border.URange)
            raw_borders = raw_borders_map.get((left, right), [])
            for h_range in h_range_set:
                if h_range in raw_borders:
                    continue
                if h_range[0] > upper_bound or h_range[1] < lower_bound:
                    continue

                h_border = Border("HI", h_range, (left, right), reference=True)
                self._instances.append(h_border)
