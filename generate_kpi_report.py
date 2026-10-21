#!/usr/bin/env python3
"""
PS Core KPI Report Generator
=============================
Automates creation of the PS Core Performance Report PowerPoint.

Usage:
    python generate_kpi_report.py

Place your input files in the 'input/' folder:
    - A folder containing KPI Excel files (the ZIP contents)
    - SAU.xlsx

The script uses 'template.pptx' as the base template and outputs
the report to 'output/PS_KPI_Report_<date_range>.pptx'.

Required packages: pip install python-pptx openpyxl xlrd pandas
"""

import os
import sys
import glob
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
INPUT_DIR = SCRIPT_DIR / "input"
TEMPLATE_PATH = SCRIPT_DIR / "template.pptx"
OUTPUT_DIR = SCRIPT_DIR / "output"

# File pattern matchers for the KPI folder
FILE_PATTERNS = {
    "attach_pdp": "Attach and PDP*",
    "epg_orn": "EPG ORN*",
    "ggsn_pdp_number": "GGSN PDP Number*",
    "ggsn_pdp_sr_vepg": "GGSN PDP SR per vEPG*",
    "ggsn_epg_pdp": "GGSN-EPG PDP new*",
    "pdp_br_sr_vugw": "PDP and BR SR per vUGW*",
    "vanb_bmr_pdp": "vANB-BMR PDP Context*",
    "vugw_traffic": "vUGW Traffic*",
    "vusn_sau_pdp": "vUSN SAU_PDP*",
}

# Node groupings
HUAWEI_NODES_USN = ["BMR_CloudUSN", "ANB_CloudUSN", "OUG_CloudUSN"]
ERICSSON_NODES_MME = ["MMEMUS1", "MMEORN1", "vMMEORN1", "vMMEBMR1"]

HUAWEI_DGW_NODES = ["BMR_CloudDGW01", "BMR_CloudDGW02", "ANB_CloudDGW", "ANB_CloudDGW02",
                     "OUG_CloudDGW01", "OUG_CloudDGW02"]
ERICSSON_EPG_NODES = ["EPGMUS1", "EPGORN1", "vEPGBMRUP1", "vEPGORNUP1",
                       "vEPGBMRCP1", "vEPGORNCP1", "vEPGBMRCORPO1"]

# Huawei DGW node groups for per-node charts
DGW_DISPLAY = {
    "ANB-DGW": ["ANB_CloudDGW", "ANB_CloudDGW02"],
    "BMR-DGW": ["BMR_CloudDGW01", "BMR_CloudDGW02"],
    "OUG-DGW": ["OUG_CloudDGW01", "OUG_CloudDGW02"],
}

# Ericsson EPG display groups for per-node charts
EPG_DISPLAY = {
    "EPG MUS": ["EPGMUS1"],
    "EPG ORN": ["EPGORN1"],
    "vEPG ORN": ["vEPGORNUP1", "vEPGORNCP1"],
    "vEPG BMR": ["vEPGBMRUP1", "vEPGBMRCP1", "vEPGBMRCORPO1"],
}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def find_file(kpi_dir, pattern):
    matches = glob.glob(os.path.join(kpi_dir, pattern))
    if not matches:
        print(f"  WARNING: No file matching '{pattern}' in {kpi_dir}")
        return None
    return matches[0]


def read_huawei_export(path, header_row=10):
    """Read Huawei U2020/iManager export (header at row 10 typically)."""
    df = pd.read_excel(path, header=None)
    # Auto-detect header row by looking for 'Start Time'
    for i in range(min(20, len(df))):
        row_vals = [str(v).strip() for v in df.iloc[i] if pd.notna(v)]
        if any("Start Time" in v for v in row_vals):
            header_row = i
            break
    df.columns = [str(df.iloc[header_row, c]).strip() for c in range(df.shape[1])]
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    df = df.dropna(subset=["Start Time"])
    df["Start Time"] = pd.to_datetime(df["Start Time"])
    return df


def read_ericsson_export(path, header_row=3):
    """Read Ericsson ENM export (header at row 3 typically)."""
    df = pd.read_excel(path, header=None)
    for i in range(min(20, len(df))):
        row_vals = [str(v).strip() for v in df.iloc[i] if pd.notna(v)]
        if any("Date" in v for v in row_vals) and any("Hour" in v for v in row_vals):
            header_row = i
            break
    df.columns = [str(df.iloc[header_row, c]).strip() for c in range(df.shape[1])]
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    df = df.dropna(subset=["Date"])
    df["Date"] = pd.to_datetime(df["Date"])
    df["Hour"] = pd.to_numeric(df["Hour"], errors="coerce")
    df["datetime"] = df["Date"] + pd.to_timedelta(df["Hour"], unit="h")
    return df


def load_sau_data(sau_path):
    """Load the SAU.xlsx summary table."""
    df = pd.read_excel(sau_path)
    df.columns = [c.strip() for c in df.columns]
    # Take only the main data rows (first block before NaN rows)
    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.iloc[0]):
            break
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Number formatting (French style with spaces)
# ---------------------------------------------------------------------------

def fmt_num(val):
    """Format number with space thousands separator, rounded to int."""
    try:
        n = int(round(float(val)))
        return f"{n:,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(val)


# ---------------------------------------------------------------------------
# Chart update helpers
# ---------------------------------------------------------------------------

def update_line_chart(chart, categories, series_dict):
    """Update a line chart with new data.
    categories: list of datetime or string labels
    series_dict: OrderedDict of {name: [values]}
    """
    chart_data = CategoryChartData()
    chart_data.categories = categories
    for name, values in series_dict.items():
        chart_data.add_series(name, values)
    chart.replace_data(chart_data)


def update_pie_chart(chart, categories, values):
    chart_data = CategoryChartData()
    chart_data.categories = categories
    chart_data.add_series("Series 1", values)
    chart.replace_data(chart_data)


def update_table(table, data_rows):
    """Update table cells. data_rows is list of lists matching table dimensions."""
    for r_idx, row_data in enumerate(data_rows):
        for c_idx, val in enumerate(row_data):
            if r_idx < len(table.rows) and c_idx < len(table.columns):
                cell = table.cell(r_idx, c_idx)
                cell.text = str(val)
                # Preserve basic formatting
                for paragraph in cell.text_frame.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(9)


# ---------------------------------------------------------------------------
# Traffic computation helpers
# ---------------------------------------------------------------------------

KB_TO_GBPS = 8 / (3600 * 1024 * 1024)  # KB per hour -> Gbps
KB_TO_TB = 1 / (1024 * 1024 * 1024)     # KB -> TB
MB_TO_TB = 1 / (1024 * 1024)            # MB -> TB
MBPS_TO_GBPS = 1 / 1024                 # Mbps -> Gbps


def compute_hourly_traffic_huawei(df_traffic):
    """Compute hourly DL/UL throughput and traffic from vUGW traffic data."""
    df = df_traffic.copy()
    for col in df.columns:
        if col not in ["Start Time", "NE Name", "Period (min)", "CGW function", "DGW function"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Identify columns
    dl_4g_col = [c for c in df.columns if "SGi downlink user traffic in KB" in c and "peak" not in c.lower()][0]
    ul_4g_col = [c for c in df.columns if "SGi uplink user traffic in KB" in c and "peak" not in c.lower()][0]
    dl_4g_peak = [c for c in df.columns if "SGi downlink" in c and "peak" in c.lower()][0]
    ul_4g_peak = [c for c in df.columns if "SGi uplink" in c and "peak" in c.lower()][0]
    dl_23g_col = [c for c in df.columns if "2/3G Gi downlink traffic" in c and "peak" not in c.lower()][0]
    ul_23g_col = [c for c in df.columns if "2/3G Gi uplink traffic" in c and "peak" not in c.lower()][0]
    dl_23g_peak = [c for c in df.columns if "2/3G Gi downlink peak" in c][0]
    ul_23g_peak = [c for c in df.columns if "2/3G Gi uplink peak" in c][0]

    return df, {
        "dl_4g": dl_4g_col, "ul_4g": ul_4g_col,
        "dl_4g_peak": dl_4g_peak, "ul_4g_peak": ul_4g_peak,
        "dl_23g": dl_23g_col, "ul_23g": ul_23g_col,
        "dl_23g_peak": dl_23g_peak, "ul_23g_peak": ul_23g_peak,
    }


def compute_hourly_traffic_ericsson(df_epg):
    """Compute hourly traffic from EPG ORN data."""
    df = df_epg.copy()
    for col in df.columns:
        if col not in ["Date", "Hour", "GGSN Name", "GGSN", "datetime"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Main report generation
# ---------------------------------------------------------------------------

def detect_date_range(kpi_dir):
    """Detect date range from folder name or data."""
    dirname = os.path.basename(kpi_dir)
    # Try to parse from folder name like "KPI 01-10 12-10-2026"
    m = re.search(r"(\d{2})-(\d{2})\s+(\d{2})-(\d{2})-(\d{4})", dirname)
    if m:
        day_start, month_start, day_end, month_end, year = m.groups()
        start = datetime(int(year), int(month_start), int(day_start))
        end = datetime(int(year), int(month_end), int(day_end))
        return start, end
    return None, None


def format_date_long(dt):
    return dt.strftime("%d %B %Y")


def find_kpi_folder(input_dir):
    """Find the KPI data folder inside input_dir."""
    for item in os.listdir(input_dir):
        path = os.path.join(input_dir, item)
        if os.path.isdir(path) and "KPI" in item.upper():
            return path
    # Check if KPI files are directly in input_dir
    for pattern in FILE_PATTERNS.values():
        if glob.glob(os.path.join(input_dir, pattern)):
            return str(input_dir)
    return None


def generate_report():
    print("=" * 60)
    print("PS Core KPI Report Generator")
    print("=" * 60)

    # Validate inputs
    if not TEMPLATE_PATH.exists():
        print(f"ERROR: Template not found at {TEMPLATE_PATH}")
        print("Place the template PPTX as 'template.pptx' in the script directory.")
        sys.exit(1)

    if not INPUT_DIR.exists():
        print(f"ERROR: Input directory not found at {INPUT_DIR}")
        print("Create an 'input/' folder with your data files.")
        sys.exit(1)

    # Find SAU.xlsx
    sau_path = None
    for f in os.listdir(INPUT_DIR):
        if f.upper().startswith("SAU") and f.endswith(".xlsx"):
            sau_path = os.path.join(INPUT_DIR, f)
            break
    if not sau_path:
        print("ERROR: SAU.xlsx not found in input/")
        sys.exit(1)
    print(f"  SAU file: {sau_path}")

    # Find KPI data folder
    kpi_dir = find_kpi_folder(INPUT_DIR)
    if not kpi_dir:
        print("ERROR: No KPI data folder found in input/")
        sys.exit(1)
    print(f"  KPI folder: {kpi_dir}")

    # Detect date range
    start_date, end_date = detect_date_range(kpi_dir)
    if not start_date:
        print("WARNING: Could not detect date range from folder name.")
        print("  Using first/last dates from data files.")

    # Load data files
    print("\nLoading data files...")
    files = {}
    for key, pattern in FILE_PATTERNS.items():
        path = find_file(kpi_dir, pattern)
        if path:
            files[key] = path
            print(f"  {key}: {os.path.basename(path)}")

    # Load SAU
    print("\nProcessing SAU data...")
    sau_df = load_sau_data(sau_path)
    print(f"  {len(sau_df)} nodes loaded")

    # Load Huawei vUGW traffic
    print("Processing vUGW traffic data...")
    df_traffic = None
    traffic_cols = None
    if "vugw_traffic" in files:
        df_traffic, traffic_cols = compute_hourly_traffic_huawei(
            read_huawei_export(files["vugw_traffic"])
        )
        print(f"  {len(df_traffic)} hourly records")

    # Load Ericsson EPG data
    print("Processing EPG data...")
    df_epg = None
    if "epg_orn" in files:
        df_epg = compute_hourly_traffic_ericsson(
            read_ericsson_export(files["epg_orn"])
        )
        print(f"  {len(df_epg)} hourly records")

    # Load GGSN-EPG PDP data
    df_ggsn_epg = None
    if "ggsn_epg_pdp" in files:
        df_ggsn_epg = read_ericsson_export(files["ggsn_epg_pdp"])

    # Load Attach & PDP
    df_attach = None
    if "attach_pdp" in files:
        df_attach = read_ericsson_export(files["attach_pdp"])

    # Load vUSN SAU_PDP
    df_vusn = None
    if "vusn_sau_pdp" in files:
        df_vusn = read_huawei_export(files["vusn_sau_pdp"])

    # Load GGSN PDP Number
    df_ggsn_pdp_num = None
    if "ggsn_pdp_number" in files:
        df_ggsn_pdp_num = read_huawei_export(files["ggsn_pdp_number"])

    # Load vANB-BMR PDP Context
    df_vanb = None
    if "vanb_bmr_pdp" in files:
        df_vanb = read_huawei_export(files["vanb_bmr_pdp"])

    # Load PDP and BR SR per vUGW
    df_pdp_sr_vugw = None
    if "pdp_br_sr_vugw" in files:
        df_pdp_sr_vugw = pd.read_excel(files["pdp_br_sr_vugw"])

    # Load GGSN PDP SR per vEPG
    df_pdp_sr_vepg = None
    if "ggsn_pdp_sr_vepg" in files:
        df_pdp_sr_vepg = read_ericsson_export(files["ggsn_pdp_sr_vepg"])

    # Detect date range from data if not from folder
    if not start_date and df_traffic is not None:
        start_date = df_traffic["Start Time"].min()
        end_date = df_traffic["Start Time"].max()

    # Generate hourly timestamps for charts
    if start_date and end_date:
        n_hours = int((end_date - start_date).total_seconds() / 3600) + 24
        hourly_times = [start_date + timedelta(hours=h) for h in range(n_hours)]
    else:
        hourly_times = []

    # -----------------------------------------------------------------------
    # Build the presentation
    # -----------------------------------------------------------------------
    print("\nGenerating PowerPoint...")
    prs = Presentation(str(TEMPLATE_PATH))

    # --- Slide 1: Title page ---
    slide1 = prs.slides[0]
    for shape in slide1.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if "01 October" in run.text or "01 october" in run.text.lower():
                        if start_date and end_date:
                            run.text = f"{format_date_long(start_date)} – {format_date_long(end_date)}"
    print("  Slide 1: Title updated")

    # --- Slide 4: SAU/PDP Table ---
    slide4 = prs.slides[3]
    for shape in slide4.shapes:
        if shape.has_table:
            tbl = shape.table
            # Node order in the table
            node_order = ["BMR_CloudUSN", "ANB_CloudUSN", "OUG_CloudUSN",
                          "MMEMUS1", "MMEORN1", "vMMEORN1", "vMMEBMR1"]
            col_names = ["Node", "SAU 2G", "SAU 3G", "SAU 4G", "PDP 2G",
                         "PDP 3G", "Bearer  4G", "Total SAU",
                         "Total PDP/Bearer Context"]
            # Map SAU data columns
            sau_col_map = {
                "SAU 2G": "SAU 2G",
                "SAU 3G": "SAU 3G",
                "SAU 4G": "SAU 4G",
                "PDP 2G": "PDP 2G",
                "PDP 3G": "PDP 3G",
                "Bearer  4G": "Bearer  4G",
                "Total SAU": "Total SAU",
                "Total PDP/Bearer Context": "Total PDP/Bearer Context",
            }
            totals = [0] * 8
            for r_idx, node_name in enumerate(node_order):
                row_data = sau_df[sau_df["Node"].str.strip() == node_name]
                if len(row_data) == 0:
                    continue
                row = row_data.iloc[0]
                tbl.cell(r_idx + 1, 0).text = node_name
                for c_idx, (display, src) in enumerate(sau_col_map.items()):
                    matching_cols = [c for c in sau_df.columns if src.strip() in c]
                    if matching_cols:
                        val = row[matching_cols[0]]
                        tbl.cell(r_idx + 1, c_idx + 1).text = fmt_num(val)
                        totals[c_idx] += float(val) if pd.notna(val) else 0

            # Total row
            for c_idx, t in enumerate(totals):
                tbl.cell(8, c_idx + 1).text = fmt_num(t)
            tbl.cell(8, 0).text = "Total "
    print("  Slide 4: SAU/PDP table updated")

    # --- Slide 5: Dashboard pie/doughnut charts ---
    slide5 = prs.slides[4]
    # Compute Huawei vs Ericsson total traffic for pie charts
    huawei_total_traffic = 0
    ericsson_total_traffic = 0

    if df_traffic is not None and traffic_cols:
        for _, row in df_traffic.iterrows():
            dl = float(row.get(traffic_cols["dl_4g"], 0) or 0)
            ul = float(row.get(traffic_cols["ul_4g"], 0) or 0)
            dl_23 = float(row.get(traffic_cols["dl_23g"], 0) or 0)
            ul_23 = float(row.get(traffic_cols["ul_23g"], 0) or 0)
            total_kb = dl + ul + dl_23 + ul_23
            total_tb = total_kb * KB_TO_TB
            huawei_total_traffic += total_tb

    if df_epg is not None:
        # Sum Ericsson traffic from EPG data
        sgi_dl_col = [c for c in df_epg.columns if "S5 Downlink Traffic" in c]
        sgi_ul_col = [c for c in df_epg.columns if "S5 Uplink Traffic" in c]
        gn_dl_col = [c for c in df_epg.columns if "Gn Downlink Traffic" in c]
        gn_ul_col = [c for c in df_epg.columns if "Gn Uplink Traffic" in c]
        for _, row in df_epg.iterrows():
            total_mb = 0
            for cols in [sgi_dl_col, sgi_ul_col, gn_dl_col, gn_ul_col]:
                if cols:
                    total_mb += float(row.get(cols[0], 0) or 0)
            ericsson_total_traffic += total_mb * MB_TO_TB

    # Compute 4G vs 2G/3G split
    total_4g_traffic = 0
    total_23g_traffic = 0
    if df_traffic is not None and traffic_cols:
        for _, row in df_traffic.iterrows():
            dl4 = float(row.get(traffic_cols["dl_4g"], 0) or 0)
            ul4 = float(row.get(traffic_cols["ul_4g"], 0) or 0)
            total_4g_traffic += (dl4 + ul4) * KB_TO_TB
            dl23 = float(row.get(traffic_cols["dl_23g"], 0) or 0)
            ul23 = float(row.get(traffic_cols["ul_23g"], 0) or 0)
            total_23g_traffic += (dl23 + ul23) * KB_TO_TB
    if df_epg is not None:
        for _, row in df_epg.iterrows():
            sgi_total = 0
            gn_total = 0
            for cols in [sgi_dl_col, sgi_ul_col]:
                if cols:
                    sgi_total += float(row.get(cols[0], 0) or 0)
            for cols in [gn_dl_col, gn_ul_col]:
                if cols:
                    gn_total += float(row.get(cols[0], 0) or 0)
            total_4g_traffic += sgi_total * MB_TO_TB
            total_23g_traffic += gn_total * MB_TO_TB

    for shape in slide5.shapes:
        try:
            if shape.has_chart:
                ch = shape.chart
                if ch.chart_type.name == "PIE" and shape.name == "Graphique 8":
                    update_pie_chart(ch, ["Huawei ", "Ericsson"],
                                     [huawei_total_traffic, ericsson_total_traffic])
                elif "DOUGHNUT" in ch.chart_type.name:
                    update_pie_chart(ch, ["4G ", "2G/3G"],
                                     [total_23g_traffic, total_4g_traffic])
        except Exception as e:
            print(f"  WARNING: Could not update chart on slide 5: {e}")
    print("  Slide 5: Dashboard charts updated")

    # --- Helper: build hourly time series ---
    def build_huawei_hourly(df, ne_names, value_cols, agg="sum", convert=1.0):
        """Aggregate Huawei data by hour for given NE names and value columns."""
        mask = df["NE Name"].isin(ne_names)
        sub = df[mask].copy()
        for c in value_cols:
            sub[c] = pd.to_numeric(sub[c], errors="coerce").fillna(0)
        grouped = sub.groupby("Start Time")[value_cols].sum()
        grouped = grouped.sort_index()
        result = {}
        for c in value_cols:
            result[c] = (grouped[c] * convert).tolist()
        times = grouped.index.tolist()
        return times, result

    def build_ericsson_hourly(df, ggsn_names, value_cols, agg="sum", convert=1.0):
        """Aggregate Ericsson data by datetime for given GGSN names."""
        mask = True
        name_col = "GGSN Name" if "GGSN Name" in df.columns else "GGSN"
        if ggsn_names:
            mask = df[name_col].isin(ggsn_names)
        sub = df[mask].copy() if not isinstance(mask, bool) else df.copy()
        for c in value_cols:
            sub[c] = pd.to_numeric(sub[c], errors="coerce").fillna(0)
        grouped = sub.groupby("datetime")[value_cols].sum()
        grouped = grouped.sort_index()
        result = {}
        for c in value_cols:
            result[c] = (grouped[c] * convert).tolist()
        times = grouped.index.tolist()
        return times, result

    # --- Slides 10-12: Network/Huawei/Ericsson Throughput ---
    if df_traffic is not None and traffic_cols and df_epg is not None:
        # Network DL&UP Throughput (slide 10) = Huawei + Ericsson combined
        hw_times, hw_tp = build_huawei_hourly(
            df_traffic, HUAWEI_DGW_NODES,
            [traffic_cols["dl_4g_peak"], traffic_cols["ul_4g_peak"],
             traffic_cols["dl_23g_peak"], traffic_cols["ul_23g_peak"]]
        )
        # Huawei throughput: peak values are in KB/s, convert to Gbps
        KBS_TO_GBPS = 8 / (1024 * 1024)
        hw_dl_gbps = [(r.get(traffic_cols["dl_4g_peak"], 0) + r.get(traffic_cols["dl_23g_peak"], 0))
                       for _, r in df_traffic.groupby("Start Time")[[
                           traffic_cols["dl_4g_peak"], traffic_cols["dl_23g_peak"]
                       ]].sum().iterrows()]
        hw_ul_gbps = [(r.get(traffic_cols["ul_4g_peak"], 0) + r.get(traffic_cols["ul_23g_peak"], 0))
                       for _, r in df_traffic.groupby("Start Time")[[
                           traffic_cols["ul_4g_peak"], traffic_cols["ul_23g_peak"]
                       ]].sum().iterrows()]

        hw_grouped = df_traffic.groupby("Start Time").agg({
            traffic_cols["dl_4g_peak"]: "sum",
            traffic_cols["ul_4g_peak"]: "sum",
            traffic_cols["dl_23g_peak"]: "sum",
            traffic_cols["ul_23g_peak"]: "sum",
        }).sort_index()
        hw_times_sorted = hw_grouped.index.tolist()
        hw_dl = ((hw_grouped[traffic_cols["dl_4g_peak"]] + hw_grouped[traffic_cols["dl_23g_peak"]]) * KBS_TO_GBPS).tolist()
        hw_ul = ((hw_grouped[traffic_cols["ul_4g_peak"]] + hw_grouped[traffic_cols["ul_23g_peak"]]) * KBS_TO_GBPS).tolist()

        # Ericsson throughput from EPG: "Total Throughput Gi PGW" is in Gbps already
        tp_col = [c for c in df_epg.columns if "Total Throughput Gi PGW" in c]
        er_dl_col = [c for c in df_epg.columns if "Downlink Throughput (Mbps)" in c]
        er_ul_col = [c for c in df_epg.columns if "Uplink Throughput (Mbps)" in c]
        s5_dl_tp = [c for c in df_epg.columns if "S5 Downlink Throughtput" in c or "S5 Downlink Throughput" in c]
        s5_ul_tp = [c for c in df_epg.columns if "S5 uplink Throughput" in c or "S5 Uplink Throughput" in c]
        gn_dl_tp = [c for c in df_epg.columns if "Gn Downlink throughput" in c or "Gn Downlink Throughput" in c]
        gn_ul_tp = [c for c in df_epg.columns if "Gn Uplink Throughput" in c]

        # EPG throughput: S5 + Gn, in Mbps -> Gbps
        er_grouped = df_epg.groupby("datetime").agg({
            **(({s5_dl_tp[0]: "sum"}) if s5_dl_tp else {}),
            **(({s5_ul_tp[0]: "sum"}) if s5_ul_tp else {}),
            **(({gn_dl_tp[0]: "sum"}) if gn_dl_tp else {}),
            **(({gn_ul_tp[0]: "sum"}) if gn_ul_tp else {}),
        }).sort_index()
        er_times = er_grouped.index.tolist()

        er_dl = []
        er_ul = []
        for _, row in er_grouped.iterrows():
            dl = 0
            ul = 0
            if s5_dl_tp:
                dl += float(row.get(s5_dl_tp[0], 0) or 0)
            if gn_dl_tp:
                dl += float(row.get(gn_dl_tp[0], 0) or 0)
            if s5_ul_tp:
                ul += float(row.get(s5_ul_tp[0], 0) or 0)
            if gn_ul_tp:
                ul += float(row.get(gn_ul_tp[0], 0) or 0)
            er_dl.append(dl * MBPS_TO_GBPS)
            er_ul.append(ul * MBPS_TO_GBPS)

        # Merge Huawei and Ericsson on common timestamps
        all_times = sorted(set(hw_times_sorted) | set(er_times))
        hw_dl_dict = dict(zip(hw_times_sorted, hw_dl))
        hw_ul_dict = dict(zip(hw_times_sorted, hw_ul))
        er_dl_dict = dict(zip(er_times, er_dl))
        er_ul_dict = dict(zip(er_times, er_ul))

        net_dl = [hw_dl_dict.get(t, 0) + er_dl_dict.get(t, 0) for t in all_times]
        net_ul = [hw_ul_dict.get(t, 0) + er_ul_dict.get(t, 0) for t in all_times]
        cats_str = [t.strftime("%Y-%m-%d %H:%M:%S") for t in all_times]

        # Slide 10: Network throughput
        slide10 = prs.slides[9]
        for shape in slide10.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, cats_str,
                                     {"DL Throughput": net_dl, " UL Throughput": net_ul})
            except:
                pass
        print("  Slide 10: Network throughput updated")

        # Slide 11: Huawei throughput
        hw_cats = [t.strftime("%Y-%m-%d %H:%M:%S") for t in hw_times_sorted]
        slide11 = prs.slides[10]
        for shape in slide11.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, hw_cats,
                                     {"DL Throughput": hw_dl, "UL Throughput": hw_ul})
            except:
                pass
        print("  Slide 11: Huawei throughput updated")

        # Slide 12: Ericsson throughput
        er_cats = [t.strftime("%Y-%m-%d %H:%M:%S") for t in er_times]
        slide12 = prs.slides[11]
        for shape in slide12.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, er_cats,
                                     {"DL Throughput": er_dl, "UL Throughput": er_ul})
            except:
                pass
        print("  Slide 12: Ericsson throughput updated")

        # --- Slide 13: Throughput per Pool (Huawei vs Ericsson) ---
        slide13 = prs.slides[12]
        hw_total = [hw_dl_dict.get(t, 0) + hw_ul_dict.get(t, 0) for t in all_times]
        er_total = [er_dl_dict.get(t, 0) + er_ul_dict.get(t, 0) for t in all_times]
        for shape in slide13.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, cats_str,
                                     {"Huawei": hw_total, "Ericsson": er_total})
            except:
                pass
        print("  Slide 13: Throughput per pool updated")

        # --- Slide 14: Throughput per Node Huawei ---
        slide14 = prs.slides[13]
        dgw_series = {}
        for display_name, nodes in DGW_DISPLAY.items():
            sub = df_traffic[df_traffic["NE Name"].isin(nodes)].copy()
            grouped = sub.groupby("Start Time").agg({
                traffic_cols["dl_4g_peak"]: "sum",
                traffic_cols["ul_4g_peak"]: "sum",
                traffic_cols["dl_23g_peak"]: "sum",
                traffic_cols["ul_23g_peak"]: "sum",
            }).sort_index()
            total_tp = ((grouped[traffic_cols["dl_4g_peak"]] + grouped[traffic_cols["dl_23g_peak"]] +
                         grouped[traffic_cols["ul_4g_peak"]] + grouped[traffic_cols["ul_23g_peak"]]) * KBS_TO_GBPS)
            dgw_series[display_name] = total_tp.tolist()

        for shape in slide14.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, hw_cats, dgw_series)
            except:
                pass
        print("  Slide 14: Huawei per-node throughput updated")

        # --- Slide 15: Throughput per Node Ericsson ---
        slide15 = prs.slides[14]
        epg_series = {}
        for display_name, nodes in EPG_DISPLAY.items():
            sub = df_epg[df_epg[("GGSN Name" if "GGSN Name" in df_epg.columns else "GGSN")].isin(nodes)].copy()
            agg_cols = {}
            if s5_dl_tp:
                agg_cols[s5_dl_tp[0]] = "sum"
            if s5_ul_tp:
                agg_cols[s5_ul_tp[0]] = "sum"
            if gn_dl_tp:
                agg_cols[gn_dl_tp[0]] = "sum"
            if gn_ul_tp:
                agg_cols[gn_ul_tp[0]] = "sum"
            if not agg_cols:
                continue
            grouped = sub.groupby("datetime").agg(agg_cols).sort_index()
            total = pd.Series(0, index=grouped.index, dtype=float)
            for c in agg_cols:
                total += grouped[c]
            epg_series[display_name + " Throughput"] = (total * MBPS_TO_GBPS).tolist()

        epg_cats = er_cats
        for shape in slide15.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, epg_cats, epg_series)
            except:
                pass
        print("  Slide 15: Ericsson per-node throughput updated")

        # --- Slides 16-18: Traffic in TB ---
        # Slide 16: Network DL&UP Traffic
        hw_traffic_grouped = df_traffic.groupby("Start Time").agg({
            traffic_cols["dl_4g"]: "sum",
            traffic_cols["ul_4g"]: "sum",
            traffic_cols["dl_23g"]: "sum",
            traffic_cols["ul_23g"]: "sum",
        }).sort_index()
        hw_dl_traffic_tb = ((hw_traffic_grouped[traffic_cols["dl_4g"]] + hw_traffic_grouped[traffic_cols["dl_23g"]]) * KB_TO_TB).tolist()
        hw_ul_traffic_tb = ((hw_traffic_grouped[traffic_cols["ul_4g"]] + hw_traffic_grouped[traffic_cols["ul_23g"]]) * KB_TO_TB).tolist()

        # Ericsson traffic
        er_traffic_cols_dl = []
        er_traffic_cols_ul = []
        sgi_dl_traffic = [c for c in df_epg.columns if "S5 Downlink Traffic" in c]
        sgi_ul_traffic = [c for c in df_epg.columns if "S5 Uplink Traffic" in c]
        gn_dl_traffic = [c for c in df_epg.columns if "Gn Downlink Traffic" in c]
        gn_ul_traffic = [c for c in df_epg.columns if "Gn Uplink Traffic" in c]
        er_traffic_agg = {}
        for cols in [sgi_dl_traffic, sgi_ul_traffic, gn_dl_traffic, gn_ul_traffic]:
            if cols:
                er_traffic_agg[cols[0]] = "sum"
        er_traffic_grouped = df_epg.groupby("datetime").agg(er_traffic_agg).sort_index()

        er_dl_traffic_tb = []
        er_ul_traffic_tb = []
        for _, row in er_traffic_grouped.iterrows():
            dl = 0
            ul = 0
            if sgi_dl_traffic:
                dl += float(row.get(sgi_dl_traffic[0], 0) or 0)
            if gn_dl_traffic:
                dl += float(row.get(gn_dl_traffic[0], 0) or 0)
            if sgi_ul_traffic:
                ul += float(row.get(sgi_ul_traffic[0], 0) or 0)
            if gn_ul_traffic:
                ul += float(row.get(gn_ul_traffic[0], 0) or 0)
            er_dl_traffic_tb.append(dl * MB_TO_TB)
            er_ul_traffic_tb.append(ul * MB_TO_TB)

        hw_dl_t_dict = dict(zip(hw_traffic_grouped.index.tolist(), hw_dl_traffic_tb))
        hw_ul_t_dict = dict(zip(hw_traffic_grouped.index.tolist(), hw_ul_traffic_tb))
        er_dl_t_dict = dict(zip(er_traffic_grouped.index.tolist(), er_dl_traffic_tb))
        er_ul_t_dict = dict(zip(er_traffic_grouped.index.tolist(), er_ul_traffic_tb))

        net_dl_traffic = [hw_dl_t_dict.get(t, 0) + er_dl_t_dict.get(t, 0) for t in all_times]
        net_ul_traffic = [hw_ul_t_dict.get(t, 0) + er_ul_t_dict.get(t, 0) for t in all_times]

        slide16 = prs.slides[15]
        for shape in slide16.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, cats_str,
                                     {" DL Traffic ": net_dl_traffic, "UL Traffic": net_ul_traffic})
            except:
                pass
        print("  Slide 16: Network traffic updated")

        # Slide 17: Huawei traffic
        slide17 = prs.slides[16]
        for shape in slide17.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, hw_cats,
                                     {"DL Traffic": hw_dl_traffic_tb, "UL Traffic": hw_ul_traffic_tb})
            except:
                pass
        print("  Slide 17: Huawei traffic updated")

        # Slide 18: Ericsson traffic
        slide18 = prs.slides[17]
        for shape in slide18.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, er_cats,
                                     {"DL Traffic": er_dl_traffic_tb, "UL Traffic": er_ul_traffic_tb})
            except:
                pass
        print("  Slide 18: Ericsson traffic updated")

        # Slide 19: Traffic per Pool (Huawei vs Ericsson) in TB
        slide19 = prs.slides[18]
        hw_total_traffic = [hw_dl_t_dict.get(t, 0) + hw_ul_t_dict.get(t, 0) for t in all_times]
        er_total_traffic = [er_dl_t_dict.get(t, 0) + er_ul_t_dict.get(t, 0) for t in all_times]
        for shape in slide19.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, cats_str,
                                     {"Huawei Traffic in TB": hw_total_traffic,
                                      "Ericsson Traffic in TB": er_total_traffic})
            except:
                pass
        print("  Slide 19: Traffic per pool updated")

        # --- Slides 20-21: SGi/Gi Traffic ---
        # SGi = 4G (S5 for Ericsson, SGi for Huawei)
        # Gi = 2G/3G (Gn for Ericsson, Gi for Huawei)
        hw_sgi = [(hw_traffic_grouped.iloc[i][traffic_cols["dl_4g"]] +
                    hw_traffic_grouped.iloc[i][traffic_cols["ul_4g"]]) * KB_TO_TB
                   for i in range(len(hw_traffic_grouped))]
        hw_gi = [(hw_traffic_grouped.iloc[i][traffic_cols["dl_23g"]] +
                   hw_traffic_grouped.iloc[i][traffic_cols["ul_23g"]]) * KB_TO_TB
                  for i in range(len(hw_traffic_grouped))]

        er_sgi = []
        er_gi = []
        for _, row in er_traffic_grouped.iterrows():
            sgi = 0
            gi = 0
            if sgi_dl_traffic:
                sgi += float(row.get(sgi_dl_traffic[0], 0) or 0)
            if sgi_ul_traffic:
                sgi += float(row.get(sgi_ul_traffic[0], 0) or 0)
            if gn_dl_traffic:
                gi += float(row.get(gn_dl_traffic[0], 0) or 0)
            if gn_ul_traffic:
                gi += float(row.get(gn_ul_traffic[0], 0) or 0)
            er_sgi.append(sgi * MB_TO_TB)
            er_gi.append(gi * MB_TO_TB)

        hw_sgi_dict = dict(zip(hw_traffic_grouped.index.tolist(), hw_sgi))
        hw_gi_dict = dict(zip(hw_traffic_grouped.index.tolist(), hw_gi))
        er_sgi_dict = dict(zip(er_traffic_grouped.index.tolist(), er_sgi))
        er_gi_dict = dict(zip(er_traffic_grouped.index.tolist(), er_gi))

        net_sgi = [hw_sgi_dict.get(t, 0) + er_sgi_dict.get(t, 0) for t in all_times]
        net_gi = [hw_gi_dict.get(t, 0) + er_gi_dict.get(t, 0) for t in all_times]
        net_total = [s + g for s, g in zip(net_sgi, net_gi)]

        # Slide 20: SGi/Gi Network Traffic
        slide20 = prs.slides[19]
        for shape in slide20.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, cats_str,
                                     {"SGI Traffic ": net_sgi, "GI Traffic ": net_gi,
                                      "Traffic ": net_total})
            except:
                pass
        print("  Slide 20: SGi/Gi network traffic updated")

        # Slide 21: SGi/Gi per Pool
        slide21 = prs.slides[20]
        hw_sgi_list = [hw_sgi_dict.get(t, 0) for t in all_times]
        er_sgi_list = [er_sgi_dict.get(t, 0) for t in all_times]
        hw_gi_list = [hw_gi_dict.get(t, 0) for t in all_times]
        er_gi_list = [er_gi_dict.get(t, 0) for t in all_times]

        chart_idx = 0
        for shape in slide21.shapes:
            try:
                if shape.has_chart:
                    if chart_idx == 0:
                        update_line_chart(shape.chart, cats_str,
                                         {"Huawei SGI": hw_sgi_list, "Ericsson SGI": er_sgi_list})
                    else:
                        update_line_chart(shape.chart, cats_str,
                                         {"Huawei GI": hw_gi_list, "Ericsson GI": er_gi_list})
                    chart_idx += 1
            except:
                pass
        print("  Slide 21: SGi/Gi per pool updated")

        # --- Slides 22-23: Daily Traffic ---
        # Aggregate to daily
        daily_times_hw = hw_traffic_grouped.copy()
        daily_times_hw.index = daily_times_hw.index.date
        daily_hw = daily_times_hw.groupby(daily_times_hw.index).sum()

        daily_er = er_traffic_grouped.copy()
        daily_er.index = daily_er.index.date
        daily_er = daily_er.groupby(daily_er.index).sum()

        all_days = sorted(set(daily_hw.index) | set(daily_er.index))
        day_cats = [d.strftime("%d-%b").lower() for d in all_days]

        # Daily SGi, Gi, Total
        daily_sgi = []
        daily_gi = []
        daily_total = []
        for d in all_days:
            sgi = 0
            gi = 0
            if d in daily_hw.index:
                r = daily_hw.loc[d]
                sgi += (r[traffic_cols["dl_4g"]] + r[traffic_cols["ul_4g"]]) * KB_TO_TB
                gi += (r[traffic_cols["dl_23g"]] + r[traffic_cols["ul_23g"]]) * KB_TO_TB
            if d in daily_er.index:
                r = daily_er.loc[d]
                if sgi_dl_traffic:
                    sgi += float(r.get(sgi_dl_traffic[0], 0) or 0) * MB_TO_TB
                if sgi_ul_traffic:
                    sgi += float(r.get(sgi_ul_traffic[0], 0) or 0) * MB_TO_TB
                if gn_dl_traffic:
                    gi += float(r.get(gn_dl_traffic[0], 0) or 0) * MB_TO_TB
                if gn_ul_traffic:
                    gi += float(r.get(gn_ul_traffic[0], 0) or 0) * MB_TO_TB
            daily_sgi.append(sgi)
            daily_gi.append(gi)
            daily_total.append(sgi + gi)

        # Slide 22: Daily SGi/Gi Network
        slide22 = prs.slides[21]
        for shape in slide22.shapes:
            try:
                if shape.has_chart:
                    update_line_chart(shape.chart, day_cats,
                                     {" SGI Traffic": daily_sgi, " GI Traffic ": daily_gi,
                                      "Total Traffic ": daily_total})
            except:
                pass
        print("  Slide 22: Daily network traffic updated")

        # Slide 23: Daily per vendor
        daily_hw_sgi = []
        daily_hw_gi = []
        daily_er_sgi = []
        daily_er_gi = []
        for d in all_days:
            hw_s = hw_g = er_s = er_g = 0
            if d in daily_hw.index:
                r = daily_hw.loc[d]
                hw_s = (r[traffic_cols["dl_4g"]] + r[traffic_cols["ul_4g"]]) * KB_TO_TB
                hw_g = (r[traffic_cols["dl_23g"]] + r[traffic_cols["ul_23g"]]) * KB_TO_TB
            if d in daily_er.index:
                r = daily_er.loc[d]
                if sgi_dl_traffic:
                    er_s += float(r.get(sgi_dl_traffic[0], 0) or 0) * MB_TO_TB
                if sgi_ul_traffic:
                    er_s += float(r.get(sgi_ul_traffic[0], 0) or 0) * MB_TO_TB
                if gn_dl_traffic:
                    er_g += float(r.get(gn_dl_traffic[0], 0) or 0) * MB_TO_TB
                if gn_ul_traffic:
                    er_g += float(r.get(gn_ul_traffic[0], 0) or 0) * MB_TO_TB
            daily_hw_sgi.append(hw_s)
            daily_hw_gi.append(hw_g)
            daily_er_sgi.append(er_s)
            daily_er_gi.append(er_g)

        slide23 = prs.slides[22]
        chart_idx = 0
        for shape in slide23.shapes:
            try:
                if shape.has_chart:
                    if chart_idx == 0:
                        update_line_chart(shape.chart, day_cats,
                                         {"Huawei SGI": daily_hw_sgi, " Ericsson SGI": daily_er_sgi})
                    else:
                        update_line_chart(shape.chart, day_cats,
                                         {" Huawei GI": daily_hw_gi, "Ericsson GI": daily_er_gi})
                    chart_idx += 1
            except:
                pass
        print("  Slide 23: Daily per vendor traffic updated")

    # --- Slide 24: Conclusion ---
    slide24 = prs.slides[23]
    if start_date and end_date:
        for shape in slide24.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        # Update date references in conclusion
                        run.text = re.sub(
                            r"from \d{2} \w+ to \d{2} \w+ \d{4}",
                            f"from {format_date_long(start_date)} to {format_date_long(end_date)}",
                            run.text
                        )
                        run.text = re.sub(
                            r"from \d{2} October to \d{2} October \d{4}",
                            f"from {format_date_long(start_date)} to {format_date_long(end_date)}",
                            run.text
                        )
    print("  Slide 24: Conclusion updated")

    # --- Save output ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if start_date and end_date:
        date_str = f"{start_date.strftime('%d-%m')}_{end_date.strftime('%d-%m-%Y')}"
    else:
        date_str = datetime.now().strftime("%Y%m%d")
    output_path = OUTPUT_DIR / f"PS_KPI_{date_str}.pptx"
    prs.save(str(output_path))

    print(f"\n{'=' * 60}")
    print(f"Report saved: {output_path}")
    print(f"{'=' * 60}")
    return str(output_path)


if __name__ == "__main__":
    generate_report()
