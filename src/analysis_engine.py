import math
from datetime import datetime, timedelta
import os
import json

# Configuration
PAUSE_THRESHOLD_SECONDS = 60  # Threshold to detect pauses/stops
FATIGUE_THRESHOLD = 45  # seconds/km above average for 2+ consecutive km

def streams_to_trackpoints(streams, activity_start_time):
    """
    Transform Strava stream data into trackpoints.
    """
    if 'latlng' not in streams or 'time' not in streams:
        return []
        
    latlng = streams['latlng']['data']
    time_offsets = streams['time']['data']
    
    # Optional fields
    altitude = streams['altitude']['data'] if 'altitude' in streams else [0.0] * len(latlng)
    heartrate = streams['heartrate']['data'] if 'heartrate' in streams else None
    cadence = streams['cadence']['data'] if 'cadence' in streams else None
    velocity = streams['velocity_smooth']['data'] if 'velocity_smooth' in streams else None

    try:
        t_str = activity_start_time.replace('Z', '+00:00')
        start_time = datetime.fromisoformat(t_str)
    except Exception:
        start_time = datetime.utcnow()

    points = []
    for i in range(len(latlng)):
        pt = {
            'lat': latlng[i][0],
            'lon': latlng[i][1],
            'ele': altitude[i] if i < len(altitude) else 0.0,
            'time': start_time + timedelta(seconds=time_offsets[i])
        }
        if heartrate and i < len(heartrate):
            pt['heartrate'] = heartrate[i]
        if cadence and i < len(cadence):
            pt['cadence'] = cadence[i]
        if velocity and i < len(velocity):
            pt['velocity'] = velocity[i]
        points.append(pt)
        
    return points

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate great-circle distance between two lat/lon points in meters.
    Uses the Haversine formula.
    """
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def calculate_metrics(points):
    """
    Calculate running metrics from track points.
    """
    if len(points) < 2:
        return None

    metrics = {}

    # --- Accumulators ---
    total_distance = 0.0
    total_elevation_gain = 0.0
    total_elevation_loss = 0.0
    moving_time = timedelta(0)
    elapsed_time = timedelta(0)

    segment_distances = []
    segment_times = []
    segment_elevations = []

    pauses = []
    pause_start = None

    break_analysis = {'segments': [], 'breaks': []}
    active_run_segment = None

    # Heart rate and cadence accumulators
    heartrates = []
    cadences = []

    # --- Process each segment ---
    for i in range(1, len(points)):
        p1, p2 = points[i-1], points[i]

        # Distance
        dist = haversine(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
        total_distance += dist
        segment_distances.append(dist)

        # Elevation
        ele_delta = p2['ele'] - p1['ele']
        if ele_delta > 0:
            total_elevation_gain += ele_delta
        else:
            total_elevation_loss += abs(ele_delta)
        segment_elevations.append(ele_delta)

        # Heart rate and cadence
        if 'heartrate' in p2:
            heartrates.append(p2['heartrate'])
        if 'cadence' in p2:
            cadences.append(p2['cadence'])

        # Time handling
        if p1['time'] and p2['time']:
            dt = p2['time'] - p1['time']
            elapsed_time += dt

            if dt.total_seconds() > PAUSE_THRESHOLD_SECONDS:
                if pause_start is None:
                    pause_start = p1['time']

                if active_run_segment is not None:
                    active_run_segment['end_time'] = p1['time'].isoformat()
                    active_run_segment['avg_pace_min_km'] = (
                        round((active_run_segment['moving_time_seconds'] / 60) / (active_run_segment['distance_m'] / 1000), 2)
                        if active_run_segment['distance_m'] > 0 and active_run_segment['moving_time_seconds'] > 0 else None
                    )
                    active_run_segment['distance_km'] = round(active_run_segment['distance_m'] / 1000, 3)
                    break_analysis['segments'].append(active_run_segment)
                    active_run_segment = None

                break_analysis['breaks'].append({
                    'start': p1['time'].isoformat(),
                    'end': p2['time'].isoformat(),
                    'duration_seconds': dt.total_seconds()
                })
            else:
                if pause_start is not None:
                    pause_end = p1['time']
                    pauses.append({
                        'start': pause_start.isoformat(),
                        'end': pause_end.isoformat(),
                        'duration_seconds': (pause_end - pause_start).total_seconds()
                    })
                    pause_start = None

                moving_time += dt
                segment_times.append(dt)

                if active_run_segment is None:
                    active_run_segment = {
                        'start_time': p1['time'].isoformat(),
                        'end_time': p2['time'].isoformat(),
                        'distance_m': 0.0,
                        'moving_time_seconds': 0,
                        'elapsed_time_seconds': 0,
                        'elevation_gain_m': 0.0,
                        'elevation_loss_m': 0.0,
                        'avg_pace_min_km': None,
                        'distance_km': 0.0
                    }

                active_run_segment['distance_m'] += dist
                if ele_delta > 0:
                    active_run_segment['elevation_gain_m'] += ele_delta
                else:
                    active_run_segment['elevation_loss_m'] += abs(ele_delta)

                active_run_segment['moving_time_seconds'] += int(dt.total_seconds())
                active_run_segment['elapsed_time_seconds'] += int(dt.total_seconds())
                active_run_segment['end_time'] = p2['time'].isoformat()
        else:
            segment_times.append(None)

    # Close any open pause at end
    if pause_start is not None and points[-1]['time']:
        pauses.append({
            'start': pause_start.isoformat(),
            'end': points[-1]['time'].isoformat(),
            'duration_seconds': (points[-1]['time'] - pause_start).total_seconds()
        })

    if active_run_segment is not None:
        active_run_segment['avg_pace_min_km'] = (
            round((active_run_segment['moving_time_seconds'] / 60) / (active_run_segment['distance_m'] / 1000), 2)
            if active_run_segment['distance_m'] > 0 and active_run_segment['moving_time_seconds'] > 0 else None
        )
        active_run_segment['distance_km'] = round(active_run_segment['distance_m'] / 1000, 3)
        break_analysis['segments'].append(active_run_segment)

    # --- Basic metrics ---
    metrics['total_distance_km'] = round(total_distance / 1000, 3)
    metrics['total_elevation_gain_m'] = round(total_elevation_gain, 1)
    metrics['total_elevation_loss_m'] = round(total_elevation_loss, 1)
    metrics['elapsed_time_seconds'] = int(elapsed_time.total_seconds())
    metrics['moving_time_seconds'] = int(moving_time.total_seconds())
    metrics['pause_time_seconds'] = metrics['elapsed_time_seconds'] - metrics['moving_time_seconds']
    metrics['pause_count'] = len(pauses)
    metrics['pauses'] = pauses

    # Heart rate & Cadence metrics
    if heartrates:
        metrics['avg_heartrate'] = round(sum(heartrates) / len(heartrates), 1)
        metrics['max_heartrate'] = max(heartrates)
    else:
        metrics['avg_heartrate'] = None
        metrics['max_heartrate'] = None

    if cadences:
        metrics['avg_cadence'] = round(sum(cadences) / len(cadences), 1)
    else:
        metrics['avg_cadence'] = None

    # Average pace (min/km)
    if total_distance > 0 and moving_time.total_seconds() > 0:
        metrics['avg_pace_min_km'] = round((moving_time.total_seconds() / 60) / (total_distance / 1000), 2)
    else:
        metrics['avg_pace_min_km'] = None

    # --- Per-km Splits ---
    splits = []
    current_split_dist = 0.0
    current_split_time = timedelta(0)
    current_split_gain = 0.0
    current_split_loss = 0.0
    current_split_hrs = []
    current_split_cadences = []

    for i in range(1, len(points)):
        p1, p2 = points[i-1], points[i]
        dist = segment_distances[i-1]
        dt = segment_times[i-1] if i-1 < len(segment_times) else None
        ele_delta = segment_elevations[i-1]

        current_split_dist += dist
        if dt:
            current_split_time += dt
        if ele_delta > 0:
            current_split_gain += ele_delta
        else:
            current_split_loss += abs(ele_delta)

        if 'heartrate' in p2:
            current_split_hrs.append(p2['heartrate'])
        if 'cadence' in p2:
            current_split_cadences.append(p2['cadence'])

        if current_split_dist >= 1000:
            split_pace = (current_split_time.total_seconds() / 60) / (current_split_dist / 1000)
            splits.append({
                'km': len(splits) + 1,
                'distance_m': round(current_split_dist, 1),
                'time_seconds': int(current_split_time.total_seconds()),
                'pace_min_km': round(split_pace, 2),
                'elevation_gain_m': round(current_split_gain, 1),
                'elevation_loss_m': round(current_split_loss, 1),
                'avg_heartrate': round(sum(current_split_hrs) / len(current_split_hrs), 1) if current_split_hrs else None,
                'avg_cadence': round(sum(current_split_cadences) / len(current_split_cadences), 1) if current_split_cadences else None
            })
            current_split_dist = 0.0
            current_split_time = timedelta(0)
            current_split_gain = 0.0
            current_split_loss = 0.0
            current_split_hrs = []
            current_split_cadences = []

    # Handle remaining partial split
    if current_split_dist > 0:
        split_pace = (current_split_time.total_seconds() / 60) / (current_split_dist / 1000)
        splits.append({
            'km': len(splits) + 1,
            'distance_m': round(current_split_dist, 1),
            'time_seconds': int(current_split_time.total_seconds()),
            'pace_min_km': round(split_pace, 2),
            'elevation_gain_m': round(current_split_gain, 1),
            'elevation_loss_m': round(current_split_loss, 1),
            'avg_heartrate': round(sum(current_split_hrs) / len(current_split_hrs), 1) if current_split_hrs else None,
            'avg_cadence': round(sum(current_split_cadences) / len(current_split_cadences), 1) if current_split_cadences else None,
            'partial': True
        })

    metrics['splits'] = splits
    metrics['break_analysis'] = break_analysis
    metrics['segment_count'] = len(break_analysis['segments'])
    metrics['break_count'] = len(break_analysis['breaks'])

    # --- Half-Split Analysis ---
    if len(splits) >= 2:
        mid = len(splits) // 2
        first_half_dist = sum(s['distance_m'] for s in splits[:mid]) / 1000
        first_half_time = sum(s['time_seconds'] for s in splits[:mid])
        second_half_dist = sum(s['distance_m'] for s in splits[mid:]) / 1000
        second_half_time = sum(s['time_seconds'] for s in splits[mid:])

        first_half_pace = (first_half_time / 60) / first_half_dist if first_half_dist > 0 else 0
        second_half_pace = (second_half_time / 60) / second_half_dist if second_half_dist > 0 else 0

        metrics['first_half_pace'] = round(first_half_pace, 2)
        metrics['second_half_pace'] = round(second_half_pace, 2)
        metrics['split_delta_seconds'] = round((second_half_pace - first_half_pace) * first_half_dist, 0) if first_half_dist > 0 else 0
        metrics['negative_split'] = second_half_pace < first_half_pace
    else:
        metrics['first_half_pace'] = None
        metrics['second_half_pace'] = None
        metrics['split_delta_seconds'] = None
        metrics['negative_split'] = None

    # --- Fatigue Onset Detection ---
    if len(splits) >= 3:
        avg_pace = metrics['avg_pace_min_km']
        fatigue_start = None
        for i, split in enumerate(splits):
            if split['pace_min_km'] > avg_pace + (FATIGUE_THRESHOLD / 60):
                if fatigue_start is None:
                    fatigue_start = i
            else:
                if fatigue_start is not None and i - fatigue_start >= 2:
                    metrics['fatigue_onset_km'] = fatigue_start + 1
                    metrics['fatigue_pace_drop'] = round(splits[fatigue_start]['pace_min_km'] - avg_pace, 2)
                    break
                fatigue_start = None
        else:
            if fatigue_start is not None and len(splits) - fatigue_start >= 2:
                metrics['fatigue_onset_km'] = fatigue_start + 1
                metrics['fatigue_pace_drop'] = round(splits[fatigue_start]['pace_min_km'] - avg_pace, 2)
            else:
                metrics['fatigue_onset_km'] = None
                metrics['fatigue_pace_drop'] = None
    else:
        metrics['fatigue_onset_km'] = None
        metrics['fatigue_pace_drop'] = None

    # --- Pacing Pattern Classification ---
    if metrics['split_delta_seconds'] is not None:
        delta = metrics['split_delta_seconds']
        if delta < -30:
            metrics['pacing_pattern'] = 'Negative Split (Strong)'
        elif delta < 15:
            metrics['pacing_pattern'] = 'Even Pacing'
        elif delta < 60:
            metrics['pacing_pattern'] = 'Mild Positive Split'
        else:
            metrics['pacing_pattern'] = 'Severe Positive Split (Blow-up)'
    else:
        metrics['pacing_pattern'] = 'Insufficient Data'

    # --- Best/Worst Split ---
    if splits:
        valid_splits = [s for s in splits if 'partial' not in s]
        if valid_splits:
            metrics['fastest_split_km'] = min(valid_splits, key=lambda x: x['pace_min_km'])
            metrics['slowest_split_km'] = max(valid_splits, key=lambda x: x['pace_min_km'])
        else:
            metrics['fastest_split_km'] = None
            metrics['slowest_split_km'] = None

    return metrics

def format_time(seconds):
    """Format seconds as HH:MM:SS or MM:SS."""
    if seconds is None:
        return 'N/A'
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def format_pace(pace):
    """Format pace (min/km) as M:SS."""
    if pace is None:
        return 'N/A'
    minutes = int(pace)
    seconds = int((pace - minutes) * 60)
    return f"{minutes}:{seconds:02d}"

def generate_summary(metrics):
    """
    Generate a human-readable analysis summary from calculated metrics.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("           STRAVA RUN ANALYSIS SUMMARY")
    lines.append("=" * 60)
    lines.append("")

    # Overview
    lines.append("📊 OVERVIEW")
    lines.append("-" * 40)
    lines.append(f"  Total Distance:     {metrics['total_distance_km']:.2f} km")
    lines.append(f"  Elapsed Time:       {format_time(metrics['elapsed_time_seconds'])}")
    lines.append(f"  Moving Time:        {format_time(metrics['moving_time_seconds'])}")
    lines.append(f"  Pause Time:         {format_time(metrics['pause_time_seconds'])}")
    lines.append(f"  Pauses Detected:    {metrics['pause_count']}")
    lines.append(f"  Avg Pace:           {format_pace(metrics['avg_pace_min_km'])} min/km")
    if metrics.get('avg_heartrate'):
        lines.append(f"  Avg Heart Rate:     {metrics['avg_heartrate']:.1f} bpm")
        lines.append(f"  Max Heart Rate:     {metrics['max_heartrate']} bpm")
    if metrics.get('avg_cadence'):
        lines.append(f"  Avg Cadence:        {metrics['avg_cadence']:.1f} spm")
    lines.append("")

    # Break / Pause Analysis
    lines.append("🧱 BREAK / PAUSE ANALYSIS")
    lines.append("-" * 40)
    if metrics.get('break_count', 0) > 0:
        lines.append(f"  Breaks:             {metrics['break_count']} | Total Break Time: {format_time(metrics['pause_time_seconds'])}")
        lines.append(f"  Run Segments:       {metrics.get('segment_count', 0)}")
        for idx, seg in enumerate(metrics['break_analysis']['segments'], start=1):
            lines.append(
                f"    Segment {idx}: {seg['distance_km']:.2f} km, {format_time(seg['moving_time_seconds'])}, Pace {format_pace(seg['avg_pace_min_km'])}"
            )
    else:
        lines.append("  No significant breaks detected — continuous run")
    lines.append("")

    # Elevation
    lines.append("🏔️  ELEVATION")
    lines.append("-" * 40)
    lines.append(f"  Total Gain:         {metrics['total_elevation_gain_m']:.1f} m")
    lines.append(f"  Total Loss:         {metrics['total_elevation_loss_m']:.1f} m")
    lines.append(f"  Net Elevation:      {metrics['total_elevation_gain_m'] - metrics['total_elevation_loss_m']:.1f} m")
    lines.append("")

    # Splits
    lines.append("📏 PER-KM SPLITS")
    lines.append("-" * 40)
    hr_hdr = " {'HR':>6}" if metrics.get('avg_heartrate') else ""
    cad_hdr = " {'Cad':>6}" if metrics.get('avg_cadence') else ""
    lines.append(f"  {'KM':>4} {'Dist':>8} {'Time':>10} {'Pace':>10} {'Gain':>8} {'Loss':>8}{hr_hdr}{cad_hdr}")
    lines.append(f"  {'':>4} {'(m)':>8} {'(mm:ss)':>10} {'(min/km)':>10} {'(m)':>8} {'(m)':>8}{' (bpm)':>6 if hr_hdr else 0}{' (spm)':>6 if cad_hdr else 0}")
    lines.append("  " + "-" * (56 + (7 if hr_hdr else 0) + (7 if cad_hdr else 0)))

    for split in metrics['splits']:
        marker = "*" if 'partial' in split else " "
        hr_val = f" {split['avg_heartrate']:>6.0f}" if (hr_hdr and split.get('avg_heartrate')) else ("      " if hr_hdr else "")
        cad_val = f" {split['avg_cadence']:>6.0f}" if (cad_hdr and split.get('avg_cadence')) else ("      " if cad_hdr else "")
        lines.append(
            f"  {marker}{split['km']:>3} "
            f"{split['distance_m']:>7.0f} "
            f"{format_time(split['time_seconds']):>10} "
            f"{format_pace(split['pace_min_km']):>10} "
            f"{split['elevation_gain_m']:>7.1f} "
            f"{split['elevation_loss_m']:>7.1f}"
            f"{hr_val}{cad_val}"
        )
    lines.append("")

    # Half-Split Analysis
    lines.append("⚡ HALF-SPLIT ANALYSIS")
    lines.append("-" * 40)
    if metrics['first_half_pace']:
        lines.append(f"  First Half Pace:    {format_pace(metrics['first_half_pace'])} min/km")
        lines.append(f"  Second Half Pace:   {format_pace(metrics['second_half_pace'])} min/km")
        lines.append(f"  Split Delta:        {metrics['split_delta_seconds']:.0f}s")
        if metrics['negative_split']:
            lines.append(f"  ✅ Negative Split Achieved!")
        else:
            lines.append(f"  ⚠️  Positive Split — faded in second half")
    else:
        lines.append("  Not enough splits for half analysis")
    lines.append("")

    # Pacing Pattern
    lines.append("🎯 PACING PATTERN")
    lines.append("-" * 40)
    lines.append(f"  Classification:     {metrics['pacing_pattern']}")
    lines.append("")

    # Fatigue Analysis
    lines.append("😓 FATIGUE ANALYSIS")
    lines.append("-" * 40)
    if metrics['fatigue_onset_km']:
        lines.append(f"  Fatigue Onset:      KM {metrics['fatigue_onset_km']}")
        lines.append(f"  Pace Drop:          +{format_pace(metrics['fatigue_pace_drop'])} min/km above average")
    else:
        lines.append("  No significant fatigue onset detected")
    lines.append("")

    # Best/Worst
    lines.append("🏆 SPLIT HIGHLIGHTS")
    lines.append("-" * 40)
    if metrics.get('fastest_split_km'):
        fs = metrics['fastest_split_km']
        lines.append(f"  Fastest Split:      KM {fs['km']} @ {format_pace(fs['pace_min_km'])} min/km")
    if metrics.get('slowest_split_km'):
        ss = metrics['slowest_split_km']
        lines.append(f"  Slowest Split:      KM {ss['km']} @ {format_pace(ss['pace_min_km'])} min/km")
    lines.append("")

    # Coaching Notes
    lines.append("💡 COACHING NOTES")
    lines.append("-" * 40)
    notes = []

    if metrics['pause_count'] > 0:
        notes.append(f"  • {metrics['pause_count']} pause(s) detected — consider continuous running for endurance")

    if metrics.get('negative_split'):
        notes.append("  • Excellent negative split — strong finish!")
    elif metrics['split_delta_seconds'] and metrics['split_delta_seconds'] > 60:
        notes.append("  • Significant fade in second half — work on pacing discipline early")

    if metrics['fatigue_onset_km']:
        notes.append(f"  • Fatigue onset at KM {metrics['fatigue_onset_km']} — build aerobic base")

    if metrics['avg_pace_min_km'] and metrics['avg_pace_min_km'] < 5.0:
        notes.append("  • Very fast average pace — ensure adequate recovery")

    if not notes:
        notes.append("  • Solid run! Keep building consistency.")

    lines.extend(notes)
    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)
