#!/usr/bin/env python3
"""
PS Core KPI Report Generator — Excel Output
=============================================
Generates a multi-sheet Excel report from KPI data files.

Usage:
    python generate_kpi_report.py

Place your KPI Excel files in the 'input/' folder (directly or in a subfolder).
Output: output/PS_KPI_Report_<date_range>.xlsx

Required packages: pip install openpyxl xlrd pandas
"""

import os
import sys
import glob
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, PieChart, Reference
from openpyxl.chart.series import SeriesLabel

SCRIPT_DIR = Path(__file__).parent.resolve()
INPUT_DIR = SCRIPT_DIR / "input"
OUTPUT_DIR = SCRIPT_DIR / "output"

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

HUAWEI_NODES_USN = ["BMR_CloudUSN", "ANB_CloudUSN", "OUG_CloudUSN"]
ERICSSON_NODES_MME = ["MMEMUS1", "MMEORN1", "vMMEORN1", "vMMEBMR1"]
HUAWEI_DGW_NODES = ["BMR_CloudDGW01", "BMR_CloudDGW02", "ANB_CloudDGW", "ANB_CloudDGW02",
                     "OUG_CloudDGW01", "OUG_CloudDGW02"]

DGW_DISPLAY = {
    "ANB-DGW": ["ANB_CloudDGW", "ANB_CloudDGW02"],
    "BMR-DGW": ["BMR_CloudDGW01", "BMR_CloudDGW02"],
    "OUG-DGW": ["OUG_CloudDGW01", "OUG_CloudDGW02"],
}
EPG_DISPLAY = {
    "EPG MUS": ["EPGMUS1"],
    "EPG ORN": ["EPGORN1"],
    "vEPG ORN": ["vEPGORNUP1", "vEPGORNCP1"],
    "vEPG BMR": ["vEPGBMRUP1", "vEPGBMRCP1", "vEPGBMRCORPO1"],
}

KB_TO_TB = 1 / (1024 * 1024 * 1024)
MB_TO_TB = 1 / (1024 * 1024)
MBPS_TO_GBPS = 1 / 1024
KBS_TO_GBPS = 8 / (1024 * 1024)

# Styling
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
HEADER_FILL = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
TITLE_FONT = Font(bold=True, size=14, color="003366")
SUBTITLE_FONT = Font(bold=True, size=11, color="003366")
NUM_FMT = '#,##0'
PCT_FMT = '0.00"%"'
DEC2_FMT = '#,##0.00'
THIN_BORDER = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)


def find_file(kpi_dir, pattern):
    matches = glob.glob(os.path.join(kpi_dir, pattern))
    if not matches:
        return None
    return matches[0]


def find_col(columns, *keywords, exclude=None):
    for c in columns:
        cl = c.lower()
        if all(k.lower() in cl for k in keywords):
            if exclude and any(e.lower() in cl for e in exclude):
                continue
            return c
    return None


def find_cols(columns, *keywords, exclude=None):
    return [c for c in columns if all(k.lower() in c.lower() for k in keywords)
            and not (exclude and any(e.lower() in c.lower() for e in exclude))]


def read_huawei_export(path):
    df = pd.read_excel(path, header=None)
    header_row = 0
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


def read_ericsson_export(path):
    df = pd.read_excel(path, header=None)
    header_row = 3
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


def read_vugw_sr(path):
    df = pd.read_excel(path, header=None)
    header_row = 0
    for i in range(min(10, len(df))):
        row_vals = [str(v).strip() for v in df.iloc[i] if pd.notna(v)]
        if any("Start Time" in v for v in row_vals):
            header_row = i
            break
    df.columns = [str(df.iloc[header_row, c]).strip() for c in range(df.shape[1])]
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    df = df.dropna(subset=["Start Time"])
    df["Start Time"] = pd.to_datetime(df["Start Time"])
    return df


def style_header_row(ws, row, max_col):
    for col in range(1, max_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
        cell.border = THIN_BORDER


def style_data_area(ws, start_row, end_row, max_col, num_fmt=NUM_FMT):
    for row in range(start_row, end_row + 1):
        for col in range(1, max_col + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal='center')
            if col > 1 and num_fmt:
                cell.number_format = num_fmt


def auto_width(ws, max_col, min_width=12, max_width=22):
    for col in range(1, max_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = max(min_width, min(max_width, 15))


def add_line_chart(ws, title, min_col, max_col, min_row, max_row, cat_col,
                   target_cell="A1", width=28, height=14):
    chart = LineChart()
    chart.title = title
    chart.style = 10
    chart.width = width
    chart.height = height
    chart.y_axis.title = None
    chart.x_axis.title = None

    data = Reference(ws, min_col=min_col, max_col=max_col, min_row=min_row, max_row=max_row)
    cats = Reference(ws, min_col=cat_col, min_row=min_row + 1, max_row=max_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)

    for s in chart.series:
        s.graphicalProperties.line.width = 20000

    ws.add_chart(chart, target_cell)
    return chart


def find_kpi_folder(input_dir):
    for item in os.listdir(input_dir):
        path = os.path.join(input_dir, item)
        if os.path.isdir(path):
            for pattern in FILE_PATTERNS.values():
                if glob.glob(os.path.join(path, pattern)):
                    return path
    for pattern in FILE_PATTERNS.values():
        if glob.glob(os.path.join(input_dir, pattern)):
            return str(input_dir)
    return None


def generate_report():
    print("=" * 60)
    print("PS Core KPI Report Generator")
    print("=" * 60)

    if not INPUT_DIR.exists():
        print(f"ERROR: Input directory not found at {INPUT_DIR}")
        sys.exit(1)

    # Extract RAR if found
    for f in os.listdir(INPUT_DIR):
        if f.lower().endswith(".rar"):
            try:
                import subprocess
                subprocess.run(["unrar", "x", "-o+", os.path.join(INPUT_DIR, f), str(INPUT_DIR) + "/"],
                               check=True, capture_output=True)
            except Exception:
                print(f"  WARNING: Could not extract {f}. Please extract manually.")

    kpi_dir = find_kpi_folder(INPUT_DIR)
    if not kpi_dir:
        print("ERROR: No KPI data files found in input/")
        sys.exit(1)
    print(f"  KPI folder: {kpi_dir}")

    # Load files
    print("\nLoading data files...")
    files = {}
    for key, pattern in FILE_PATTERNS.items():
        path = find_file(kpi_dir, pattern)
        if path:
            files[key] = path
            print(f"  {key}: {os.path.basename(path)}")

    print("\nProcessing data...")

    df_vusn = read_huawei_export(files["vusn_sau_pdp"]) if "vusn_sau_pdp" in files else None
    df_attach = read_ericsson_export(files["attach_pdp"]) if "attach_pdp" in files else None

    df_traffic = None
    traffic_cols = None
    if "vugw_traffic" in files:
        df_traffic = read_huawei_export(files["vugw_traffic"])
        for col in df_traffic.columns:
            if col not in ["Start Time", "NE Name", "Period (min)", "CGW function", "DGW function"]:
                df_traffic[col] = pd.to_numeric(df_traffic[col], errors="coerce")
        traffic_cols = {
            "dl_4g": find_col(df_traffic.columns, "SGi", "downlink", "traffic", exclude=["peak"]),
            "ul_4g": find_col(df_traffic.columns, "SGi", "uplink", "traffic", exclude=["peak"]),
            "dl_4g_peak": find_col(df_traffic.columns, "SGi", "downlink", "peak"),
            "ul_4g_peak": find_col(df_traffic.columns, "SGi", "uplink", "peak"),
            "dl_23g": find_col(df_traffic.columns, "2/3G", "Gi", "downlink", "traffic", exclude=["peak"]),
            "ul_23g": find_col(df_traffic.columns, "2/3G", "Gi", "uplink", "traffic", exclude=["peak"]),
            "dl_23g_peak": find_col(df_traffic.columns, "2/3G", "Gi", "downlink", "peak"),
            "ul_23g_peak": find_col(df_traffic.columns, "2/3G", "Gi", "uplink", "peak"),
        }
        print(f"  vUGW Traffic: {len(df_traffic)} records")

    df_epg = None
    if "epg_orn" in files:
        df_epg = read_ericsson_export(files["epg_orn"])
        for col in df_epg.columns:
            if col not in ["Date", "Hour", "GGSN Name", "GGSN", "datetime"]:
                df_epg[col] = pd.to_numeric(df_epg[col], errors="coerce")
        print(f"  EPG ORN: {len(df_epg)} records")

    df_pdp_sr_vugw = read_vugw_sr(files["pdp_br_sr_vugw"]) if "pdp_br_sr_vugw" in files else None
    df_pdp_sr_vepg = read_ericsson_export(files["ggsn_pdp_sr_vepg"]) if "ggsn_pdp_sr_vepg" in files else None
    df_ggsn_epg = read_ericsson_export(files["ggsn_epg_pdp"]) if "ggsn_epg_pdp" in files else None
    df_ggsn_pdp_num = read_huawei_export(files["ggsn_pdp_number"]) if "ggsn_pdp_number" in files else None
    df_vanb = read_huawei_export(files["vanb_bmr_pdp"]) if "vanb_bmr_pdp" in files else None

    # Detect date range
    all_dates = []
    if df_traffic is not None:
        all_dates.extend(df_traffic["Start Time"].dropna().tolist())
    if df_attach is not None:
        all_dates.extend(df_attach["Date"].dropna().tolist())
    if df_vusn is not None:
        all_dates.extend(df_vusn["Start Time"].dropna().tolist())

    start_date = end_date = None
    dirname = os.path.basename(kpi_dir)
    m = re.search(r"(\d{2})-(\d{2})\s+(\d{2})-(\d{2})-(\d{4})", dirname)
    if m:
        d1, m1, d2, m2, y = m.groups()
        start_date = datetime(int(y), int(m1), int(d1))
        end_date = datetime(int(y), int(m2), int(d2))
    elif all_dates:
        start_date = min(all_dates)
        end_date = max(all_dates)
        if hasattr(start_date, 'to_pydatetime'):
            start_date = start_date.to_pydatetime()
            end_date = end_date.to_pydatetime()

    if start_date:
        print(f"  Date range: {start_date.strftime('%d %B %Y')} - {end_date.strftime('%d %B %Y')}")

    # ===================================================================
    # Build Excel workbook
    # ===================================================================
    print("\nGenerating Excel report...")
    from openpyxl import Workbook
    wb = Workbook()

    # ---- Sheet 1: SAU Summary ----
    ws_sau = wb.active
    ws_sau.title = "SAU Summary"
    ws_sau.cell(1, 1, "PS Core Performance Report").font = TITLE_FONT
    if start_date:
        ws_sau.cell(2, 1, f"Period: {start_date.strftime('%d %B %Y')} – {end_date.strftime('%d %B %Y')}").font = SUBTITLE_FONT

    headers = ["Node", "SAU 2G", "SAU 3G", "SAU 4G", "PDP 2G", "PDP 3G",
               "Bearer 4G", "Total SAU", "Total PDP/Bearer"]
    for c, h in enumerate(headers, 1):
        ws_sau.cell(4, c, h)
    style_header_row(ws_sau, 4, len(headers))

    node_order = HUAWEI_NODES_USN + ERICSSON_NODES_MME
    row = 5
    totals = [0.0] * 8

    # Huawei USN
    if df_vusn is not None:
        s2g = find_col(df_vusn.columns, "Gb", "attached", "users")
        s3g = find_col(df_vusn.columns, "Iu", "attached", "users")
        s4g = find_col(df_vusn.columns, "maximum attached users", exclude=["Gb", "Iu"])
        p2g = find_col(df_vusn.columns, "Gb", "PDP")
        p3g = find_col(df_vusn.columns, "Iu", "PDP")
        b4g = find_col(df_vusn.columns, "bearer", "S1") or find_col(df_vusn.columns, "Maximum bearer")
        for col in [s2g, s3g, s4g, p2g, p3g, b4g]:
            if col:
                df_vusn[col] = pd.to_numeric(df_vusn[col], errors="coerce")
        for node in HUAWEI_NODES_USN:
            sub = df_vusn[df_vusn["NE Name"] == node]
            if len(sub) == 0:
                continue
            vals = [sub[c].max() if c else 0 for c in [s2g, s3g, s4g, p2g, p3g, b4g]]
            ws_sau.cell(row, 1, node)
            for i, v in enumerate(vals):
                v = float(v) if pd.notna(v) else 0
                ws_sau.cell(row, i + 2, v)
                totals[i] += v
            total_sau = sum(vals[:3])
            total_pdp = sum(vals[3:])
            ws_sau.cell(row, 8, total_sau)
            ws_sau.cell(row, 9, total_pdp)
            totals[6] += total_sau
            totals[7] += total_pdp
            row += 1

    # Ericsson MME
    if df_attach is not None:
        nc = "SGSN Name" if "SGSN Name" in df_attach.columns else "GGSN Name"
        as2g = find_col(df_attach.columns, "SAU", "2G")
        as3g = find_col(df_attach.columns, "SAU", "3G")
        as4g = find_col(df_attach.columns, "SAU", "4G")
        ap2g = find_col(df_attach.columns, "PDP", "2G")
        ap3g = find_col(df_attach.columns, "PDP", "3G")
        ab4g = find_col(df_attach.columns, "Bearer", "4G")
        for col in [as2g, as3g, as4g, ap2g, ap3g, ab4g]:
            if col:
                df_attach[col] = pd.to_numeric(df_attach[col], errors="coerce")
        for node in ERICSSON_NODES_MME:
            sub = df_attach[df_attach[nc] == node]
            if len(sub) == 0:
                continue
            vals = [sub[c].max() if c else 0 for c in [as2g, as3g, as4g, ap2g, ap3g, ab4g]]
            ws_sau.cell(row, 1, node)
            for i, v in enumerate(vals):
                v = float(v) if pd.notna(v) else 0
                ws_sau.cell(row, i + 2, v)
                totals[i] += v
            total_sau = sum(vals[:3])
            total_pdp = sum(vals[3:])
            ws_sau.cell(row, 8, total_sau)
            ws_sau.cell(row, 9, total_pdp)
            totals[6] += total_sau
            totals[7] += total_pdp
            row += 1

    # Total row
    ws_sau.cell(row, 1, "TOTAL").font = Font(bold=True)
    for i, t in enumerate(totals):
        ws_sau.cell(row, i + 2, t).font = Font(bold=True)

    style_data_area(ws_sau, 5, row, len(headers))
    auto_width(ws_sau, len(headers))
    ws_sau.column_dimensions['A'].width = 18
    print("  Sheet: SAU Summary")

    # ---- Sheet 2: Attached Users Hourly ----
    ws_sau_h = wb.create_sheet("Attached Users Hourly")
    all_nodes = []
    node_sau_data = {}

    if df_vusn is not None:
        for node in HUAWEI_NODES_USN:
            sub = df_vusn[df_vusn["NE Name"] == node].sort_values("Start Time")
            if len(sub) == 0:
                continue
            all_nodes.append(node)
            node_sau_data[node] = {
                "times": sub["Start Time"].tolist(),
                "sau_4g": sub[s4g].fillna(0).tolist() if s4g else [],
            }
    if df_attach is not None:
        for node in ERICSSON_NODES_MME:
            sub = df_attach[df_attach[nc] == node].sort_values("datetime")
            if len(sub) == 0:
                continue
            all_nodes.append(node)
            node_sau_data[node] = {
                "times": sub["datetime"].tolist(),
                "sau_4g": sub[as4g].fillna(0).tolist() if as4g else [],
            }

    if node_sau_data:
        all_t = sorted(set(t for d in node_sau_data.values() for t in d["times"]))
        ws_sau_h.cell(1, 1, "Attached Users (4G) per Node - Hourly").font = TITLE_FONT
        ws_sau_h.cell(3, 1, "Time")
        for i, n in enumerate(all_nodes):
            ws_sau_h.cell(3, i + 2, n)
        style_header_row(ws_sau_h, 3, len(all_nodes) + 1)

        for r, t in enumerate(all_t, 4):
            ws_sau_h.cell(r, 1, t).number_format = 'YYYY-MM-DD HH:MM'
            for i, n in enumerate(all_nodes):
                td = dict(zip(node_sau_data[n]["times"], node_sau_data[n]["sau_4g"]))
                ws_sau_h.cell(r, i + 2, td.get(t, 0)).number_format = NUM_FMT

        auto_width(ws_sau_h, len(all_nodes) + 1)
        ws_sau_h.column_dimensions['A'].width = 18

        if len(all_t) > 0:
            add_line_chart(ws_sau_h, "Attached Users (4G) per Node",
                           min_col=2, max_col=len(all_nodes) + 1,
                           min_row=3, max_row=3 + len(all_t),
                           cat_col=1, target_cell=f"A{4 + len(all_t) + 2}")
        print("  Sheet: Attached Users Hourly")

    # ---- Sheet 3: PDP Context Hourly ----
    ws_pdp_h = wb.create_sheet("PDP Context Hourly")
    node_pdp_data = {}

    if df_vusn is not None:
        for node in HUAWEI_NODES_USN:
            sub = df_vusn[df_vusn["NE Name"] == node].sort_values("Start Time")
            if len(sub) == 0:
                continue
            node_pdp_data[node] = {
                "times": sub["Start Time"].tolist(),
                "bearer_4g": sub[b4g].fillna(0).tolist() if b4g else [],
            }
    if df_attach is not None:
        for node in ERICSSON_NODES_MME:
            sub = df_attach[df_attach[nc] == node].sort_values("datetime")
            if len(sub) == 0:
                continue
            node_pdp_data[node] = {
                "times": sub["datetime"].tolist(),
                "bearer_4g": sub[ab4g].fillna(0).tolist() if ab4g else [],
            }

    if node_pdp_data:
        pdp_nodes = list(node_pdp_data.keys())
        all_t2 = sorted(set(t for d in node_pdp_data.values() for t in d["times"]))
        ws_pdp_h.cell(1, 1, "Active PDP/Bearer Context (4G) per Node - Hourly").font = TITLE_FONT
        ws_pdp_h.cell(3, 1, "Time")
        for i, n in enumerate(pdp_nodes):
            ws_pdp_h.cell(3, i + 2, n)
        style_header_row(ws_pdp_h, 3, len(pdp_nodes) + 1)

        for r, t in enumerate(all_t2, 4):
            ws_pdp_h.cell(r, 1, t).number_format = 'YYYY-MM-DD HH:MM'
            for i, n in enumerate(pdp_nodes):
                td = dict(zip(node_pdp_data[n]["times"], node_pdp_data[n]["bearer_4g"]))
                ws_pdp_h.cell(r, i + 2, td.get(t, 0)).number_format = NUM_FMT

        auto_width(ws_pdp_h, len(pdp_nodes) + 1)
        ws_pdp_h.column_dimensions['A'].width = 18
        if len(all_t2) > 0:
            add_line_chart(ws_pdp_h, "Active PDP/Bearer Context (4G) per Node",
                           min_col=2, max_col=len(pdp_nodes) + 1,
                           min_row=3, max_row=3 + len(all_t2),
                           cat_col=1, target_cell=f"A{4 + len(all_t2) + 2}")
        print("  Sheet: PDP Context Hourly")

    # ---- Sheet 4: Throughput (Gbps) ----
    if df_traffic is not None and traffic_cols and df_epg is not None:
        ws_tp = wb.create_sheet("Throughput Gbps")
        ws_tp.cell(1, 1, "Network DL & UL Throughput (Gbps)").font = TITLE_FONT

        peak_keys = ["dl_4g_peak", "ul_4g_peak", "dl_23g_peak", "ul_23g_peak"]
        peak_cols = [traffic_cols[k] for k in peak_keys if traffic_cols[k]]

        hw_grouped = df_traffic.groupby("Start Time").agg({c: "sum" for c in peak_cols}).sort_index()
        hw_times = hw_grouped.index.tolist()
        hw_dl = ((hw_grouped[traffic_cols["dl_4g_peak"]] + hw_grouped[traffic_cols["dl_23g_peak"]]) * KBS_TO_GBPS).tolist()
        hw_ul = ((hw_grouped[traffic_cols["ul_4g_peak"]] + hw_grouped[traffic_cols["ul_23g_peak"]]) * KBS_TO_GBPS).tolist()

        s5_dl_tp = find_cols(df_epg.columns, "S5", "Downlink", "hrought")
        s5_ul_tp = find_cols(df_epg.columns, "S5", "plink", "hroughput") or find_cols(df_epg.columns, "S5", "Uplink", "hroughput")
        gn_dl_tp = find_cols(df_epg.columns, "Gn", "Downlink", "hroughput")
        gn_ul_tp = find_cols(df_epg.columns, "Gn", "Uplink", "hroughput")

        er_agg = {c[0]: "sum" for c in [s5_dl_tp, s5_ul_tp, gn_dl_tp, gn_ul_tp] if c}
        er_grouped = df_epg.groupby("datetime").agg(er_agg).sort_index()
        er_times = er_grouped.index.tolist()
        er_dl = [sum(float(row.get(c[0], 0) or 0) for c in [s5_dl_tp, gn_dl_tp] if c) * MBPS_TO_GBPS for _, row in er_grouped.iterrows()]
        er_ul = [sum(float(row.get(c[0], 0) or 0) for c in [s5_ul_tp, gn_ul_tp] if c) * MBPS_TO_GBPS for _, row in er_grouped.iterrows()]

        all_times = sorted(set(hw_times) | set(er_times))
        hw_dl_d = dict(zip(hw_times, hw_dl))
        hw_ul_d = dict(zip(hw_times, hw_ul))
        er_dl_d = dict(zip(er_times, er_dl))
        er_ul_d = dict(zip(er_times, er_ul))

        tp_headers = ["Time", "Network DL", "Network UL", "Huawei DL", "Huawei UL", "Ericsson DL", "Ericsson UL"]
        for c, h in enumerate(tp_headers, 1):
            ws_tp.cell(3, c, h)
        style_header_row(ws_tp, 3, len(tp_headers))

        for r, t in enumerate(all_times, 4):
            ws_tp.cell(r, 1, t).number_format = 'YYYY-MM-DD HH:MM'
            h_dl = hw_dl_d.get(t, 0); h_ul = hw_ul_d.get(t, 0)
            e_dl = er_dl_d.get(t, 0); e_ul = er_ul_d.get(t, 0)
            ws_tp.cell(r, 2, h_dl + e_dl).number_format = DEC2_FMT
            ws_tp.cell(r, 3, h_ul + e_ul).number_format = DEC2_FMT
            ws_tp.cell(r, 4, h_dl).number_format = DEC2_FMT
            ws_tp.cell(r, 5, h_ul).number_format = DEC2_FMT
            ws_tp.cell(r, 6, e_dl).number_format = DEC2_FMT
            ws_tp.cell(r, 7, e_ul).number_format = DEC2_FMT

        auto_width(ws_tp, len(tp_headers))
        ws_tp.column_dimensions['A'].width = 18

        if all_times:
            add_line_chart(ws_tp, "Network Throughput (Gbps)",
                           min_col=2, max_col=3, min_row=3, max_row=3 + len(all_times),
                           cat_col=1, target_cell=f"A{4 + len(all_times) + 2}")
            add_line_chart(ws_tp, "Huawei vs Ericsson Throughput (Gbps)",
                           min_col=4, max_col=7, min_row=3, max_row=3 + len(all_times),
                           cat_col=1, target_cell=f"A{4 + len(all_times) + 18}")
        print("  Sheet: Throughput Gbps")

        # ---- Sheet 5: Traffic (TB) ----
        ws_traf = wb.create_sheet("Traffic TB")
        ws_traf.cell(1, 1, "Network Traffic Volume (TB)").font = TITLE_FONT

        traf_keys = ["dl_4g", "ul_4g", "dl_23g", "ul_23g"]
        traf_cols_list = [traffic_cols[k] for k in traf_keys if traffic_cols[k]]

        hw_traf_g = df_traffic.groupby("Start Time").agg({c: "sum" for c in traf_cols_list}).sort_index()
        hw_dl_tb = ((hw_traf_g[traffic_cols["dl_4g"]] + hw_traf_g[traffic_cols["dl_23g"]]) * KB_TO_TB).tolist()
        hw_ul_tb = ((hw_traf_g[traffic_cols["ul_4g"]] + hw_traf_g[traffic_cols["ul_23g"]]) * KB_TO_TB).tolist()

        sgi_dl = find_cols(df_epg.columns, "S5", "Downlink", "Traffic")
        sgi_ul = find_cols(df_epg.columns, "S5", "Uplink", "Traffic")
        gn_dl = find_cols(df_epg.columns, "Gn", "Downlink", "Traffic")
        gn_ul = find_cols(df_epg.columns, "Gn", "Uplink", "Traffic")
        er_traf_agg = {c[0]: "sum" for c in [sgi_dl, sgi_ul, gn_dl, gn_ul] if c}
        er_traf_g = df_epg.groupby("datetime").agg(er_traf_agg).sort_index()

        er_dl_tb = [sum(float(row.get(c[0], 0) or 0) for c in [sgi_dl, gn_dl] if c) * MB_TO_TB for _, row in er_traf_g.iterrows()]
        er_ul_tb = [sum(float(row.get(c[0], 0) or 0) for c in [sgi_ul, gn_ul] if c) * MB_TO_TB for _, row in er_traf_g.iterrows()]

        hw_dl_td = dict(zip(hw_traf_g.index.tolist(), hw_dl_tb))
        hw_ul_td = dict(zip(hw_traf_g.index.tolist(), hw_ul_tb))
        er_dl_td = dict(zip(er_traf_g.index.tolist(), er_dl_tb))
        er_ul_td = dict(zip(er_traf_g.index.tolist(), er_ul_tb))

        traf_headers = ["Time", "Network DL (TB)", "Network UL (TB)", "Huawei DL", "Huawei UL",
                        "Ericsson DL", "Ericsson UL", "SGi/S5 (4G)", "Gi/Gn (2G/3G)", "Total"]
        for c, h in enumerate(traf_headers, 1):
            ws_traf.cell(3, c, h)
        style_header_row(ws_traf, 3, len(traf_headers))

        for r, t in enumerate(all_times, 4):
            ws_traf.cell(r, 1, t).number_format = 'YYYY-MM-DD HH:MM'
            h_dl = hw_dl_td.get(t, 0); h_ul = hw_ul_td.get(t, 0)
            e_dl = er_dl_td.get(t, 0); e_ul = er_ul_td.get(t, 0)

            # SGi = 4G, Gi = 2G/3G
            hw_sgi_v = 0; hw_gi_v = 0
            if t in hw_traf_g.index:
                rr = hw_traf_g.loc[t]
                hw_sgi_v = (rr[traffic_cols["dl_4g"]] + rr[traffic_cols["ul_4g"]]) * KB_TO_TB
                hw_gi_v = (rr[traffic_cols["dl_23g"]] + rr[traffic_cols["ul_23g"]]) * KB_TO_TB
            er_sgi_v = sum(float(er_traf_g.loc[t].get(c[0], 0) or 0) for c in [sgi_dl, sgi_ul] if c) * MB_TO_TB if t in er_traf_g.index else 0
            er_gi_v = sum(float(er_traf_g.loc[t].get(c[0], 0) or 0) for c in [gn_dl, gn_ul] if c) * MB_TO_TB if t in er_traf_g.index else 0

            ws_traf.cell(r, 2, h_dl + e_dl).number_format = DEC2_FMT
            ws_traf.cell(r, 3, h_ul + e_ul).number_format = DEC2_FMT
            ws_traf.cell(r, 4, h_dl).number_format = DEC2_FMT
            ws_traf.cell(r, 5, h_ul).number_format = DEC2_FMT
            ws_traf.cell(r, 6, e_dl).number_format = DEC2_FMT
            ws_traf.cell(r, 7, e_ul).number_format = DEC2_FMT
            ws_traf.cell(r, 8, hw_sgi_v + er_sgi_v).number_format = DEC2_FMT
            ws_traf.cell(r, 9, hw_gi_v + er_gi_v).number_format = DEC2_FMT
            ws_traf.cell(r, 10, h_dl + h_ul + e_dl + e_ul).number_format = DEC2_FMT

        auto_width(ws_traf, len(traf_headers))
        ws_traf.column_dimensions['A'].width = 18

        if all_times:
            add_line_chart(ws_traf, "Network Traffic (TB)",
                           min_col=2, max_col=3, min_row=3, max_row=3 + len(all_times),
                           cat_col=1, target_cell=f"A{4 + len(all_times) + 2}")
            add_line_chart(ws_traf, "SGi (4G) vs Gi (2G/3G) Traffic (TB)",
                           min_col=8, max_col=10, min_row=3, max_row=3 + len(all_times),
                           cat_col=1, target_cell=f"A{4 + len(all_times) + 18}")
        print("  Sheet: Traffic TB")

        # ---- Sheet 6: Daily Traffic Summary ----
        ws_daily = wb.create_sheet("Daily Traffic")
        ws_daily.cell(1, 1, "Daily Traffic Summary (TB)").font = TITLE_FONT

        daily_hw = hw_traf_g.copy()
        daily_hw.index = daily_hw.index.date
        daily_hw = daily_hw.groupby(daily_hw.index).sum()
        daily_er = er_traf_g.copy()
        daily_er.index = daily_er.index.date
        daily_er = daily_er.groupby(daily_er.index).sum()
        all_days = sorted(set(daily_hw.index) | set(daily_er.index))

        d_headers = ["Date", "Huawei SGi (4G)", "Huawei Gi (2G/3G)", "Ericsson S5 (4G)",
                     "Ericsson Gn (2G/3G)", "Total SGi/S5", "Total Gi/Gn", "Grand Total"]
        for c, h in enumerate(d_headers, 1):
            ws_daily.cell(3, c, h)
        style_header_row(ws_daily, 3, len(d_headers))

        for r, d in enumerate(all_days, 4):
            ws_daily.cell(r, 1, d.strftime("%d-%b-%Y"))
            hw_s = hw_g = er_s = er_g = 0
            if d in daily_hw.index:
                rr = daily_hw.loc[d]
                hw_s = (rr[traffic_cols["dl_4g"]] + rr[traffic_cols["ul_4g"]]) * KB_TO_TB
                hw_g = (rr[traffic_cols["dl_23g"]] + rr[traffic_cols["ul_23g"]]) * KB_TO_TB
            if d in daily_er.index:
                rr = daily_er.loc[d]
                for c in [sgi_dl, sgi_ul]:
                    if c: er_s += float(rr.get(c[0], 0) or 0) * MB_TO_TB
                for c in [gn_dl, gn_ul]:
                    if c: er_g += float(rr.get(c[0], 0) or 0) * MB_TO_TB
            ws_daily.cell(r, 2, hw_s).number_format = DEC2_FMT
            ws_daily.cell(r, 3, hw_g).number_format = DEC2_FMT
            ws_daily.cell(r, 4, er_s).number_format = DEC2_FMT
            ws_daily.cell(r, 5, er_g).number_format = DEC2_FMT
            ws_daily.cell(r, 6, hw_s + er_s).number_format = DEC2_FMT
            ws_daily.cell(r, 7, hw_g + er_g).number_format = DEC2_FMT
            ws_daily.cell(r, 8, hw_s + hw_g + er_s + er_g).number_format = DEC2_FMT

        style_data_area(ws_daily, 4, 3 + len(all_days), len(d_headers), num_fmt=DEC2_FMT)
        auto_width(ws_daily, len(d_headers))

        if all_days:
            add_line_chart(ws_daily, "Daily Traffic (TB)",
                           min_col=6, max_col=8, min_row=3, max_row=3 + len(all_days),
                           cat_col=1, target_cell=f"A{4 + len(all_days) + 2}")
        print("  Sheet: Daily Traffic")

    # ---- Sheet 7: Ericsson PDP SR ----
    if df_pdp_sr_vepg is not None:
        ws_sr_e = wb.create_sheet("Ericsson PDP SR")
        ws_sr_e.cell(1, 1, "Ericsson PDP/Bearer Success Rate (%)").font = TITLE_FONT

        nc_sr = "SGSN Name" if "SGSN Name" in df_pdp_sr_vepg.columns else "GGSN Name"
        sr_nodes = df_pdp_sr_vepg[nc_sr].dropna().unique().tolist()

        sr_2g = find_col(df_pdp_sr_vepg.columns, "SR", "2G", exclude=["Bearer", "LTE"]) or \
                find_col(df_pdp_sr_vepg.columns, "Pdp", "2G")
        sr_3g = find_col(df_pdp_sr_vepg.columns, "SR", "3G", exclude=["Bearer", "LTE"]) or \
                find_col(df_pdp_sr_vepg.columns, "Pdp", "3G")
        sr_4g = find_col(df_pdp_sr_vepg.columns, "Bearer", "SR") or \
                find_col(df_pdp_sr_vepg.columns, "Bearer", "activation") or \
                find_col(df_pdp_sr_vepg.columns, "LTE", "Bearer")

        sr_cols_found = [(c, l) for c, l in [(sr_2g, "PDP SR 2G"), (sr_3g, "PDP SR 3G"), (sr_4g, "4G Bearer SR")] if c]
        for c, _ in sr_cols_found:
            df_pdp_sr_vepg[c] = pd.to_numeric(df_pdp_sr_vepg[c], errors="coerce")

        # One block per SR metric
        block_row = 3
        for sr_col, sr_label in sr_cols_found:
            ws_sr_e.cell(block_row, 1, sr_label).font = SUBTITLE_FONT
            block_row += 1
            ws_sr_e.cell(block_row, 1, "Time")
            for i, n in enumerate(sr_nodes):
                ws_sr_e.cell(block_row, i + 2, n)
            style_header_row(ws_sr_e, block_row, len(sr_nodes) + 1)

            sorted_data = df_pdp_sr_vepg.sort_values("datetime")
            times = sorted(sorted_data["datetime"].unique())
            data_start = block_row + 1
            for r, t in enumerate(times, data_start):
                ws_sr_e.cell(r, 1, t).number_format = 'YYYY-MM-DD HH:MM'
                for i, n in enumerate(sr_nodes):
                    sub = df_pdp_sr_vepg[(df_pdp_sr_vepg[nc_sr] == n) & (df_pdp_sr_vepg["datetime"] == t)]
                    v = sub[sr_col].iloc[0] if len(sub) > 0 else 0
                    ws_sr_e.cell(r, i + 2, float(v) if pd.notna(v) else 0).number_format = '0.00'

            end_data = data_start + len(times) - 1
            if len(times) > 0:
                add_line_chart(ws_sr_e, f"{sr_label} per Node (%)",
                               min_col=2, max_col=len(sr_nodes) + 1,
                               min_row=block_row, max_row=end_data,
                               cat_col=1, target_cell=f"{get_column_letter(len(sr_nodes) + 3)}{block_row}")
            block_row = end_data + 3

        auto_width(ws_sr_e, len(sr_nodes) + 1)
        ws_sr_e.column_dimensions['A'].width = 18
        print("  Sheet: Ericsson PDP SR")

    # ---- Sheet 8: Huawei PDP SR ----
    if df_pdp_sr_vugw is not None:
        ws_sr_h = wb.create_sheet("Huawei PDP SR")
        ws_sr_h.cell(1, 1, "Huawei PDP/Bearer Success Rate (%)").font = TITLE_FONT

        pdp_sr = find_col(df_pdp_sr_vugw.columns, "PDP", "success", "ratio")
        br_sr = find_col(df_pdp_sr_vugw.columns, "bearer", "success", "ratio")
        hw_sr_nodes = df_pdp_sr_vugw["NE Name"].unique().tolist()

        block_row = 3
        for sr_col, sr_label in [(pdp_sr, "PDP Context SR (2G/3G)"), (br_sr, "Bearer Context SR (4G)")]:
            if not sr_col:
                continue
            df_pdp_sr_vugw[sr_col] = pd.to_numeric(df_pdp_sr_vugw[sr_col], errors="coerce")

            ws_sr_h.cell(block_row, 1, sr_label).font = SUBTITLE_FONT
            block_row += 1
            ws_sr_h.cell(block_row, 1, "Time")
            for i, n in enumerate(hw_sr_nodes):
                ws_sr_h.cell(block_row, i + 2, n)
            style_header_row(ws_sr_h, block_row, len(hw_sr_nodes) + 1)

            times = sorted(df_pdp_sr_vugw["Start Time"].unique())
            data_start = block_row + 1
            for r, t in enumerate(times, data_start):
                ws_sr_h.cell(r, 1, t).number_format = 'YYYY-MM-DD HH:MM'
                for i, n in enumerate(hw_sr_nodes):
                    sub = df_pdp_sr_vugw[(df_pdp_sr_vugw["NE Name"] == n) & (df_pdp_sr_vugw["Start Time"] == t)]
                    v = sub[sr_col].iloc[0] if len(sub) > 0 else 0
                    ws_sr_h.cell(r, i + 2, float(v) if pd.notna(v) else 0).number_format = '0.000'

            end_data = data_start + len(times) - 1
            if len(times) > 0:
                add_line_chart(ws_sr_h, f"{sr_label} per Node (%)",
                               min_col=2, max_col=len(hw_sr_nodes) + 1,
                               min_row=block_row, max_row=end_data,
                               cat_col=1, target_cell=f"{get_column_letter(len(hw_sr_nodes) + 3)}{block_row}")
            block_row = end_data + 3

        auto_width(ws_sr_h, len(hw_sr_nodes) + 1)
        ws_sr_h.column_dimensions['A'].width = 18
        print("  Sheet: Huawei PDP SR")

    # ---- Save ----
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if start_date and end_date:
        date_str = f"{start_date.strftime('%d-%m')}_{end_date.strftime('%d-%m-%Y')}"
    else:
        date_str = datetime.now().strftime("%Y%m%d")
    output_path = OUTPUT_DIR / f"PS_KPI_{date_str}.xlsx"
    wb.save(str(output_path))

    print(f"\n{'=' * 60}")
    print(f"Report saved: {output_path}")
    print(f"{'=' * 60}")
    return str(output_path)


if __name__ == "__main__":
    generate_report()
