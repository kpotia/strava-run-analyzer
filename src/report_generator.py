import os
import json
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from src.analysis_engine import format_pace, format_time, haversine

def render_run_report(activity, metrics, points, template_dir, output_path):
    """
    Renders the Jinja2 HTML report template for an individual activity.
    Saves the output to the specified path.
    """
    # 1. Calculate cumulative distance for each point
    cumulative_dist = 0.0
    distances = [0.0]
    for i in range(1, len(points)):
        cumulative_dist += haversine(points[i-1]['lat'], points[i-1]['lon'], points[i]['lat'], points[i]['lon'])
        distances.append(round(cumulative_dist / 1000, 3))
    
    # 2. Extract series
    elevations = [round(pt['ele'], 1) for pt in points]
    
    # Pace calculation from velocity_smooth (m/s)
    paces = []
    for pt in points:
        vel = pt.get('velocity', 0.0)
        if vel > 0.5:  # Over 1.8 km/h
            pace = round(16.6667 / vel, 2)
            if pace > 15.0:  # Cap to avoid visual graph spikes
                pace = 15.0
        else:
            pace = 15.0
        paces.append(pace)
        
    # Heartrate
    has_hr = any('heartrate' in pt for pt in points)
    heartrates = [pt.get('heartrate', 0) for pt in points] if has_hr else []

    # 3. Downsample to keep page size small (~300 points)
    target_size = 300
    
    def downsample(lst):
        if len(lst) <= target_size:
            return lst
        step = len(lst) / target_size
        return [lst[int(i * step)] for i in range(target_size)]
        
    ds_distances = downsample(distances)
    ds_elevations = downsample(elevations)
    ds_paces = downsample(paces)
    ds_heartrates = downsample(heartrates) if has_hr else []

    # Format date for UI
    # E.g. '2026-06-12T10:00:00Z'
    dt_str = activity.get('start_date_local', '')
    activity['start_date_local_formatted'] = dt_str
    activity['start_time_local'] = ''
    if dt_str:
        try:
            # Parse ISO format
            t_str = dt_str.replace('Z', '')
            parsed_dt = datetime.fromisoformat(t_str)
            activity['start_date_local_formatted'] = parsed_dt.strftime('%B %d, %Y')
            activity['start_time_local'] = parsed_dt.strftime('%H:%M:%S')
        except Exception:
            pass

    # 4. Render template
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('report_template.html')
    
    html_content = template.render(
        activity=activity,
        metrics=metrics,
        format_pace=format_pace,
        format_time=format_time,
        distances_json=json.dumps(ds_distances),
        elevations_json=json.dumps(ds_elevations),
        paces_json=json.dumps(ds_paces),
        heartrates_json=json.dumps(ds_heartrates)
    )
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    print(f"Individual report generated at {output_path}")

def render_dashboard(runs, stats, template_dir, output_path):
    """
    Renders the Jinja2 HTML dashboard template listing all runs.
    Saves the output to the specified path.
    """
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('dashboard_template.html')
    
    html_content = template.render(
        runs=runs,
        stats=stats,
        format_pace=format_pace,
        format_time=format_time
    )
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    print(f"Dashboard index generated at {output_path}")
