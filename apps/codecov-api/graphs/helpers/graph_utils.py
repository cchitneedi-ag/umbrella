from math import cos, pi, sin

style_n_defs = """
<style>rect.s{mask:url(#mask);}</style>
<defs>
  <pattern id="white" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
    <rect width="2" height="2" transform="translate(0,0)" fill="white"></rect>
  </pattern>
  <mask id="mask">
    <rect x="0" y="0" width="100%" height="100%" fill="url(#white)"></rect>
  </mask>
</defs>
"""


def _squarify(values, left, top, width, height, **kwargs):
    # values should add up to width * height
    if len(values) == 0:
        return []

    if len(values) == 1:
        return _layout(values, left, top, width, height)[0]

    i = 1
    while i < len(values) and _worst_ratio(
        values[:i], left, top, width, height
    ) >= _worst_ratio(values[: (i + 1)], left, top, width, height):
        i += 1

    current = values[:i]
    remaining = values[i:]

    rectangles, leftover_space = _layout(current, left, top, width, height)
    return rectangles + _squarify(remaining, *leftover_space)


def _layout(areas, left, top, width, height, **kwargs):
    layout_area = sum(areas)
    vertical = width >= height
    rectangles = []
    if vertical:
        layout_width = layout_area / height
        rect_top = top
        for area in areas:
            rect_height = area / layout_width
            rectangles.append((left, rect_top, layout_width, rect_height))
            rect_top += rect_height
        leftover_space = (left + layout_width, top, width - layout_width, height)
    else:
        layout_height = layout_area / width
        rect_left = left
        for area in areas:
            rect_width = area / layout_height
            rectangles.append((rect_left, top, rect_width, layout_height))
            rect_left += rect_width
        leftover_space = (left, top + layout_height, width, height - layout_height)
    return rectangles, leftover_space


def _worst_ratio(areas, left, top, width, height, **kwargs):
    rectangles, leftover = _layout(areas, left, top, width, height)
    return max(map(_max_aspect_ratio, rectangles))


def _max_aspect_ratio(rect):
    return max(
        (rect[2] / rect[3]) if rect[3] > 0 else 0,
        (rect[3] / rect[2]) if rect[2] > 0 else 0,
    )


def _svg_rect(x, y, width, height, fill, stroke, stroke_width, _class=None, title=None):
    """http://www.w3schools.com/svg/svg_rect.asp"""
    if title is None:
        return (
            '<rect x="{}" y="{}" width="{}" height="{}" '
            'fill="{}" stroke="{}" stroke-width="{}"{} />'.format(
                x,
                y,
                width,
                height,
                fill,
                stroke,
                stroke_width,
                (f'class="{_class}"' if _class else ""),
            )
        )

    return (
        '<rect x="{0}" y="{1}" width="{2}" height="{3}" '
        'fill="{4}" stroke="{5}" stroke-width="{6}" class="{8} tooltipped" '
        'data-content="{7}">'
        "<title>{7}</title>"
        "</rect>".format(
            x, y, width, height, fill, stroke, stroke_width, title, _class or ""
        )
    )


def _make_svg(width, height, elements, viewPortWidth=None, viewPortHeight=None):
    return (
        '<svg baseProfile="full" width="{}" height="{}" viewBox="0 0 {} {}" version="1.1"\n'
        'xmlns="http://www.w3.org/2000/svg" xmlns:ev="http://www.w3.org/2001/xml-events"\n'
        'xmlns:xlink="http://www.w3.org/1999/xlink">\n'
        "{}\n"
        "{}\n"
        "</svg>".format(
            width,
            height,
            viewPortWidth or width,
            viewPortHeight or height,
            style_n_defs,
            "\n".join(elements),
        )
    )


def _tree_height(tree):
    if not tree:
        return 0

    subtrees = filter(None, (item.get("children", None) for item in tree))

    if not subtrees:
        return 1
    children_map = list(map(_tree_height, subtrees))
    if len(children_map) < 1:
        return 1

    return 1 + max(children_map)


def _svg_polar_rect(
    cx, cy, inner_radius, outer_radius, start, end, fill, stroke, stroke_width
):
    """
    http://www.w3schools.com/svg/svg_circle.asp
    http://www.w3schools.com/svg/svg_path.asp
    """

    # special case: circle
    if inner_radius == 0 and end - start == 1:
        return f'<circle cx="{cx}" cy="{cy}" fill="{fill}" r="{outer_radius}" stroke="{stroke}" stroke-width="{stroke_width}" />'

    in_angle = 2.0 * pi * start
    out_angle = 2.0 * pi * end

    # special case: ring
    if end - start == 1:
        # make a ring using two circles
        # each circle consists of 2 180-degree arcs
        # from (cx - r, cy) to (cx + r, cy) and back

        # outer contour
        d = f"M {cx - outer_radius} {cy} A {outer_radius} {outer_radius} 0 0 0 {cx + outer_radius} {cy} A {outer_radius} {outer_radius} 0 0 0 {cx - outer_radius} {cy} z "
        # inner contour
        d += f"M {cx - inner_radius} {cy} A {inner_radius} {inner_radius} 0 0 0 {cx + inner_radius} {cy} A {inner_radius} {inner_radius} 0 0 0 {cx - inner_radius} {cy} z "

        return f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'

    # start points
    spx_outer = outer_radius * sin(in_angle)
    spy_outer = outer_radius * cos(in_angle)
    spx_inner = inner_radius * sin(out_angle)
    spy_inner = inner_radius * cos(out_angle)

    # target points
    tpx_outer = outer_radius * sin(out_angle)
    tpy_outer = outer_radius * cos(out_angle)
    tpx_inner = inner_radius * sin(in_angle)
    tpy_inner = inner_radius * cos(in_angle)

    large_arc_flag = 1 if end - start > 0.5 else 0

    path_args = f"M {cx + tpx_inner} {cy + tpy_inner} L {cx + spx_outer} {cy + spy_outer} A {outer_radius} {outer_radius} 0 {large_arc_flag} 0 {cx + tpx_outer} {cy + tpy_outer} L {cx + spx_inner} {cy + spy_inner} A {inner_radius} {inner_radius} 0 {large_arc_flag} 1 {cx + tpx_inner} {cy + tpy_inner} z"

    return f'<path d="{path_args}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" />'
