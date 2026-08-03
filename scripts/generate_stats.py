import os
import json
import base64

def get_font_base64(font_filename):
    font_path = os.path.join(os.path.dirname(__file__), "..", "fonts", font_filename)
    if os.path.exists(font_path):
        with open(font_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

def generate_stats_svg(data):
    bold_b64 = get_font_base64("JBM-Bold.subset.woff2")
    medium_b64 = get_font_base64("JBM-Medium.subset.woff2")
    
    font_style = f"""
        @font-face {{
          font-family: 'JBM Bold';
          src: url(data:font/woff2;base64,{bold_b64}) format('woff2');
          font-weight: 700;
          font-style: normal;
        }}
        @font-face {{
          font-family: 'JBM Medium';
          src: url(data:font/woff2;base64,{medium_b64}) format('woff2');
          font-weight: 500;
          font-style: normal;
        }}
        text {{ font-family: 'JBM Medium', ui-monospace, monospace; }}
        .b {{ font-family: 'JBM Bold', ui-monospace, monospace; }}
    """

    total_contribs = data.get("total_contributions", 0)
    active_days = data.get("active_days", 0)
    best_week = data.get("best_week", 0)
    total_commits = data.get("total_commits", 0)
    total_prs = data.get("total_prs", 0)
    repos_contributed = data.get("repos_contributed", 0)
    
    weekly = data.get("weekly_contributions", [0] * 52)
    if not weekly or len(weekly) == 0:
        weekly = [0] * 52
        
    # Standardize to 52 data points
    if len(weekly) > 52:
        weekly = weekly[-52:]
    elif len(weekly) < 52:
        weekly = [0] * (52 - len(weekly)) + weekly
        
    max_val = max(weekly) if max(weekly) > 0 else 1
    svg_width = 620
    chart_height = 110 # y from 0 to 110
    num_points = len(weekly)
    dx = svg_width / max((num_points - 1), 1)
    
    # Calculate chart points
    points = []
    for i, val in enumerate(weekly):
        x = round(i * dx, 1)
        y = round(chart_height - (val / max_val * chart_height), 1)
        points.append((x, y, val))
        
    # Build smooth cubic Bezier line path
    def get_control_point(p_prev, p_curr, p_next, p_nextnext, tension=0.15):
        # Calculate tangent vectors
        d1 = ((p_next[0] - p_prev[0]) * tension, (p_next[1] - p_prev[1]) * tension)
        d2 = ((p_nextnext[0] - p_curr[0]) * tension, (p_nextnext[1] - p_curr[1]) * tension)
        return (
            (round(p_curr[0] + d1[0], 1), round(p_curr[1] + d1[1], 1)),
            (round(p_next[0] - d2[0], 1), round(p_next[1] - d2[1], 1))
        )

    path_cmds = [f"M {points[0][0]} {points[0][1]}"]
    for i in range(len(points) - 1):
        p0 = points[max(i - 1, 0)]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[min(i + 2, len(points) - 1)]
        
        cp1, cp2 = get_control_point(p0, p1, p2, p3)
        path_cmds.append(f"C {cp1[0]} {cp1[1]}, {cp2[0]} {cp2[1]}, {p2[0]} {p2[1]}")
        
    line_path = " ".join(path_cmds)
    area_path = f"{line_path} L {svg_width} {chart_height} L 0 {chart_height} Z"
    
    # Peak dots (find top 2 peak points)
    sorted_points = sorted(enumerate(points), key=lambda item: item[1][2], reverse=True)
    peak_dots_svg = ""
    seen_x = set()
    peaks_added = 0
    
    for idx, (x, y, val) in sorted_points:
        if val > 0 and peaks_added < 2:
            # ensure peaks aren't too close together
            too_close = any(abs(x - prev_x) < 50 for prev_x in seen_x)
            if not too_close:
                seen_x.add(x)
                peaks_added += 1
                peak_dots_svg += f'''
      <circle cx="{x}" cy="{y}" r="3.5" fill="#B7A9DE" opacity="0.9"/>
      <text x="{x}" y="{y - 8}" text-anchor="middle" font-size="9" fill="#B7A9DE" class="b">{val}</text>'''

    # Month labels
    months = data.get("month_labels", [])
    if not months:
        # Default 12 month labels if empty
        m_names = ["Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"]
        months = [{"index": int(i * 4.33), "month": m_names[i]} for i in range(12)]
        
    month_texts_svg = ""
    for m in months:
        idx = m.get("index", 0)
        x_pos = round(idx * dx, 1)
        if x_pos < svg_width - 25:
            month_texts_svg += f'\n      <text x="{x_pos}" y="126" font-size="9" fill="#555">{m["month"]}</text>'

    svg_content = f'''<svg width="620" height="260" viewBox="0 0 620 260" xmlns="http://www.w3.org/2000/svg">
<defs>
<style>
{font_style}
</style>
<linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0%" stop-color="#B7A9DE" stop-opacity="0.25"/>
  <stop offset="100%" stop-color="#B7A9DE" stop-opacity="0.02"/>
</linearGradient>
</defs>

  <!-- Header stats -->
  <g transform="translate(0,4)">
    <g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="0.05s" dur="0.6s" fill="freeze" />
      <text x="0" y="40" class="b" font-size="42" fill="#E7E3DC">{total_contribs}</text>
      <text x="0" y="60" font-size="11" fill="#8B877E" letter-spacing="0.5">contributions in the last year</text>
    </g>

    <g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="0.15s" dur="0.6s" fill="freeze" />
      <text x="620" y="24" text-anchor="end" class="b" font-size="20" fill="#B7A9DE">{active_days}</text>
      <text x="620" y="40" text-anchor="end" font-size="10" fill="#8B877E">active days</text>
      <text x="620" y="60" text-anchor="end" class="b" font-size="20" fill="#78A6C2">{best_week}</text>
      <text x="620" y="76" text-anchor="end" font-size="10" fill="#8B877E">best week</text>
    </g>
  </g>

  <!-- Chart area: y=95 to y=205 (110px tall), x=0 to x=620 -->
  <g transform="translate(0, 95)">
    <!-- Horizontal grid lines -->
    <g opacity="0"><animate attributeName="opacity" from="0" to="0.3" begin="0.2s" dur="0.5s" fill="freeze" />
      <line x1="0" y1="0" x2="620" y2="0" stroke="#2A2D33" stroke-width="0.5"/>
      <line x1="0" y1="27.5" x2="620" y2="27.5" stroke="#2A2D33" stroke-width="0.5" stroke-dasharray="3 4"/>
      <line x1="0" y1="55" x2="620" y2="55" stroke="#2A2D33" stroke-width="0.5" stroke-dasharray="3 4"/>
      <line x1="0" y1="82.5" x2="620" y2="82.5" stroke="#2A2D33" stroke-width="0.5" stroke-dasharray="3 4"/>
      <line x1="0" y1="110" x2="620" y2="110" stroke="#2A2D33" stroke-width="0.5"/>
    </g>

    <!-- Area fill under line -->
    <path d="{area_path}" fill="url(#areaFill)" opacity="0">
      <animate attributeName="opacity" from="0" to="1" begin="0.6s" dur="0.8s" fill="freeze"/>
    </path>

    <!-- Main line -->
    <path d="{line_path}" fill="none" stroke="#B7A9DE" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" stroke-dasharray="900" stroke-dashoffset="900">
      <animate attributeName="stroke-dashoffset" from="900" to="0" begin="0.3s" dur="1.6s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/>
    </path>

    <!-- Peak dots with commit counts -->
    <g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="1.2s" dur="0.4s" fill="freeze" />{peak_dots_svg}
    </g>

    <!-- Month labels along x-axis -->
    <g opacity="0"><animate attributeName="opacity" from="0" to="1" begin="0.5s" dur="0.5s" fill="freeze" />{month_texts_svg}
    </g>
  </g>

  <!-- Footer stats -->
  <g transform="translate(0,242)" opacity="0"><animate attributeName="opacity" from="0" to="1" begin="0.7s" dur="0.5s" fill="freeze" />
    <text x="0" y="0" font-size="11" fill="#8B877E">{total_commits} commits</text>
    <text x="120" y="0" font-size="11" fill="#8B877E">·</text>
    <text x="140" y="0" font-size="11" fill="#8B877E">{total_prs} pr opened</text>
    <text x="260" y="0" font-size="11" fill="#8B877E">·</text>
    <text x="280" y="0" font-size="11" fill="#8B877E">{repos_contributed} repo contributed to</text>
  </g>
</svg>
'''
    return svg_content

if __name__ == "__main__":
    data_path = os.path.join(os.path.dirname(__file__), "data.json")
    if os.path.exists(data_path):
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        svg = generate_stats_svg(data)
        output_svg_path = os.path.join(os.path.dirname(__file__), "..", "stats.svg")
        with open(output_svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        print("Generated stats.svg successfully!")
