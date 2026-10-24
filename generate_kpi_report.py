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
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, Reference
from openpyxl.chart.label import DataLabelList

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

HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
HEADER_FILL = PatternFill(start_color="003366", end_color="003366", fill_type="solid")
TITLE_FONT = Font(bold=True, size=14, color="003366")
SUBTITLE_FONT = Font(bold=True, size=11, color="003366")
NUM_FMT = '#,##0'
DEC2_FMT = '#,##0.00'
DEC3_FMT = '#,##0.000'
THIN_BORDER = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)


def find_file(kpi_dir, pattern):
    matches = glob.glob(os.path.join(kpi_dir, pattern))
    return matches[0] if matches else None


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
    df["_date"] = df["Start Time"].dt.date
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
    df["_date"] = df["Date"].dt.date
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
    df["_date"] = df["Start Time"].dt.date
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
    chart.x_axis.tickLblPos = "low"
    chart.x_axis.delete = False
    chart.x_axis.numFmt = 'DD-MMM'
    chart.x_axis.majorTickMark = "out"

    data = Reference(ws, min_col=min_col, max_col=max_col, min_row=min_row, max_row=max_row)
    cats = Reference(ws, min_col=cat_col, min_row=min_row + 1, max_row=max_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)

    for s in chart.series:
        s.graphicalProperties.line.width = 22000
        s.smooth = True

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


def fmt_date(d):
    """Format a date object as 'DD-Mon' string for chart categories."""
    if hasattr(d, 'strftime'):
        return d.strftime("%d-%b")
    return str(d)


def write_daily_table(ws, title, start_row, days, col_names, data_dict, num_fmt=DEC2_FMT):
    """Write a daily table with string date column + numeric columns.
    data_dict: {col_name: {date: value, ...}, ...}
    Returns the row after the last data row.
    """
    ws.cell(start_row, 1, title).font = SUBTITLE_FONT
    header_row = start_row + 1
    ws.cell(header_row, 1, "Date")
    for i, name in enumerate(col_names):
        ws.cell(header_row, i + 2, name)
    style_header_row(ws, header_row, len(col_names) + 1)

    for r, d in enumerate(days, header_row + 1):
        ws.cell(r, 1, fmt_date(d))
        for i, name in enumerate(col_names):
            v = data_dict.get(name, {}).get(d, 0)
            v = float(v) if pd.notna(v) else 0
            ws.cell(r, i + 2, v).number_format = num_fmt

    end_row = header_row + len(days)
    style_data_area(ws, header_row + 1, end_row, len(col_names) + 1, num_fmt=num_fmt)
    return header_row, end_row


def generate_report():
    print("=" * 60)
    print("PS Core KPI Report Generator")
    print("=" * 60)

    if not INPUT_DIR.exists():
        print(f"ERROR: Input directory not found at {INPUT_DIR}")
        sys.exit(1)

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
            if col not in ["Start Time", "NE Name", "Period (min)", "CGW function", "DGW function", "_date"]:
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
            if col not in ["Date", "Hour", "GGSN Name", "GGSN", "datetime", "_date"]:
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
    # Build Excel workbook — all charts use DAILY aggregation
    # ===================================================================
    print("\nGenerating Excel report...")
    from openpyxl import Workbook
    wb = Workbook()

    # Identify column names for SAU/PDP
    s2g = s3g = s4g = p2g = p3g = b4g = None
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

    nc = None
    as2g = as3g = as4g = ap2g = ap3g = ab4g = None
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

    # ---- Sheet 1: SAU Summary (MAX per node over entire period) ----
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

    row = 5
    totals = [0.0] * 8

    if df_vusn is not None:
        for node in HUAWEI_NODES_USN:
            sub = df_vusn[df_vusn["NE Name"] == node]
            if len(sub) == 0:
                continue
            vals = [float(sub[c].max()) if c and pd.notna(sub[c].max()) else 0 for c in [s2g, s3g, s4g, p2g, p3g, b4g]]
            ws_sau.cell(row, 1, node)
            for i, v in enumerate(vals):
                ws_sau.cell(row, i + 2, v)
                totals[i] += v
            total_sau = sum(vals[:3])
            total_pdp = sum(vals[3:])
            ws_sau.cell(row, 8, total_sau)
            ws_sau.cell(row, 9, total_pdp)
            totals[6] += total_sau
            totals[7] += total_pdp
            row += 1

    if df_attach is not None:
        for node in ERICSSON_NODES_MME:
            sub = df_attach[df_attach[nc] == node]
            if len(sub) == 0:
                continue
            vals = [float(sub[c].max()) if c and pd.notna(sub[c].max()) else 0 for c in [as2g, as3g, as4g, ap2g, ap3g, ab4g]]
            ws_sau.cell(row, 1, node)
            for i, v in enumerate(vals):
                ws_sau.cell(row, i + 2, v)
                totals[i] += v
            total_sau = sum(vals[:3])
            total_pdp = sum(vals[3:])
            ws_sau.cell(row, 8, total_sau)
            ws_sau.cell(row, 9, total_pdp)
            totals[6] += total_sau
            totals[7] += total_pdp
            row += 1

    ws_sau.cell(row, 1, "TOTAL").font = Font(bold=True)
    for i, t in enumerate(totals):
        ws_sau.cell(row, i + 2, t).font = Font(bold=True)
    style_data_area(ws_sau, 5, row, len(headers))
    auto_width(ws_sau, len(headers))
    ws_sau.column_dimensions['A'].width = 18
    print("  Sheet: SAU Summary")

    # ---- Sheet 2: Attached Users Daily (MAX per day per node) ----
    ws_sau_d = wb.create_sheet("Attached Users Daily")
    ws_sau_d.cell(1, 1, "Attached Users (4G) per Node — Daily MAX").font = TITLE_FONT

    all_nodes = []
    node_daily_sau = {}

    if df_vusn is not None and s4g:
        for node in HUAWEI_NODES_USN:
            sub = df_vusn[df_vusn["NE Name"] == node]
            if len(sub) == 0:
                continue
            all_nodes.append(node)
            daily = sub.groupby("_date")[s4g].max()
            node_daily_sau[node] = daily.to_dict()

    if df_attach is not None and as4g:
        for node in ERICSSON_NODES_MME:
            sub = df_attach[df_attach[nc] == node]
            if len(sub) == 0:
                continue
            all_nodes.append(node)
            daily = sub.groupby("_date")[as4g].max()
            node_daily_sau[node] = daily.to_dict()

    if node_daily_sau:
        all_days = sorted(set(d for dd in node_daily_sau.values() for d in dd.keys()))
        header_row_sau, end_row_sau = write_daily_table(
            ws_sau_d, "", 2, all_days, all_nodes,
            {n: dd for n, dd in node_daily_sau.items()}, num_fmt=NUM_FMT)

        auto_width(ws_sau_d, len(all_nodes) + 1)
        ws_sau_d.column_dimensions['A'].width = 14

        if len(all_days) > 1:
            add_line_chart(ws_sau_d, "Attached Users (4G) per Node — Daily MAX",
                           min_col=2, max_col=len(all_nodes) + 1,
                           min_row=header_row_sau, max_row=end_row_sau,
                           cat_col=1, target_cell=f"A{end_row_sau + 2}")
        print("  Sheet: Attached Users Daily")

    # ---- Sheet 3: PDP/Bearer Context Daily ----
    ws_pdp_d = wb.create_sheet("PDP Context Daily")
    ws_pdp_d.cell(1, 1, "Active PDP/Bearer Context (4G) per Node — Daily MAX").font = TITLE_FONT

    pdp_nodes = []
    node_daily_pdp = {}

    if df_vusn is not None and b4g:
        for node in HUAWEI_NODES_USN:
            sub = df_vusn[df_vusn["NE Name"] == node]
            if len(sub) == 0:
                continue
            pdp_nodes.append(node)
            daily = sub.groupby("_date")[b4g].max()
            node_daily_pdp[node] = daily.to_dict()

    if df_attach is not None and ab4g:
        for node in ERICSSON_NODES_MME:
            sub = df_attach[df_attach[nc] == node]
            if len(sub) == 0:
                continue
            pdp_nodes.append(node)
            daily = sub.groupby("_date")[ab4g].max()
            node_daily_pdp[node] = daily.to_dict()

    if node_daily_pdp:
        all_days_pdp = sorted(set(d for dd in node_daily_pdp.values() for d in dd.keys()))
        header_row_pdp, end_row_pdp = write_daily_table(
            ws_pdp_d, "", 2, all_days_pdp, pdp_nodes,
            {n: dd for n, dd in node_daily_pdp.items()}, num_fmt=NUM_FMT)

        auto_width(ws_pdp_d, len(pdp_nodes) + 1)
        ws_pdp_d.column_dimensions['A'].width = 14

        if len(all_days_pdp) > 1:
            add_line_chart(ws_pdp_d, "Active PDP/Bearer Context (4G) — Daily MAX",
                           min_col=2, max_col=len(pdp_nodes) + 1,
                           min_row=header_row_pdp, max_row=end_row_pdp,
                           cat_col=1, target_cell=f"A{end_row_pdp + 2}")
        print("  Sheet: PDP Context Daily")

    # ---- Sheet 4: Throughput (Gbps) — Daily MAX ----
    if df_traffic is not None and traffic_cols and df_epg is not None:
        ws_tp = wb.create_sheet("Throughput Gbps")
        ws_tp.cell(1, 1, "Peak Throughput (Gbps) — Daily MAX").font = TITLE_FONT

        # Huawei: sum across nodes per hour, then daily MAX
        hw_peak_agg = {}
        for k in ["dl_4g_peak", "ul_4g_peak", "dl_23g_peak", "ul_23g_peak"]:
            if traffic_cols[k]:
                hw_peak_agg[traffic_cols[k]] = "sum"
        hw_hourly = df_traffic.groupby("Start Time").agg(hw_peak_agg)
        hw_hourly["_date"] = hw_hourly.index.date
        hw_daily = hw_hourly.groupby("_date").max()

        # Ericsson: find throughput columns
        s5_dl_tp = find_cols(df_epg.columns, "S5", "Downlink", "hrought")
        s5_ul_tp = find_cols(df_epg.columns, "S5", "plink", "hroughput") or find_cols(df_epg.columns, "S5", "Uplink", "hroughput")
        gn_dl_tp = find_cols(df_epg.columns, "Gn", "Downlink", "hroughput")
        gn_ul_tp = find_cols(df_epg.columns, "Gn", "Uplink", "hroughput")

        er_tp_agg = {}
        for cl in [s5_dl_tp, s5_ul_tp, gn_dl_tp, gn_ul_tp]:
            if cl:
                er_tp_agg[cl[0]] = "sum"
        er_hourly = df_epg.groupby("datetime").agg(er_tp_agg)
        er_hourly["_date"] = er_hourly.index.date
        er_daily = er_hourly.groupby("_date").max()

        all_days_tp = sorted(set(hw_daily.index) | set(er_daily.index))

        tp_col_names = ["Network DL", "Network UL", "Huawei DL", "Huawei UL", "Ericsson DL", "Ericsson UL"]
        tp_data = {n: {} for n in tp_col_names}

        for d in all_days_tp:
            h_dl = h_ul = e_dl = e_ul = 0
            if d in hw_daily.index:
                rr = hw_daily.loc[d]
                h_dl = (float(rr.get(traffic_cols["dl_4g_peak"], 0) or 0) + float(rr.get(traffic_cols["dl_23g_peak"], 0) or 0)) * KBS_TO_GBPS
                h_ul = (float(rr.get(traffic_cols["ul_4g_peak"], 0) or 0) + float(rr.get(traffic_cols["ul_23g_peak"], 0) or 0)) * KBS_TO_GBPS
            if d in er_daily.index:
                rr = er_daily.loc[d]
                e_dl = sum(float(rr.get(c[0], 0) or 0) for c in [s5_dl_tp, gn_dl_tp] if c) * MBPS_TO_GBPS
                e_ul = sum(float(rr.get(c[0], 0) or 0) for c in [s5_ul_tp, gn_ul_tp] if c) * MBPS_TO_GBPS
            tp_data["Network DL"][d] = h_dl + e_dl
            tp_data["Network UL"][d] = h_ul + e_ul
            tp_data["Huawei DL"][d] = h_dl
            tp_data["Huawei UL"][d] = h_ul
            tp_data["Ericsson DL"][d] = e_dl
            tp_data["Ericsson UL"][d] = e_ul

        h_row_tp, e_row_tp = write_daily_table(ws_tp, "", 2, all_days_tp, tp_col_names, tp_data, num_fmt=DEC2_FMT)
        auto_width(ws_tp, len(tp_col_names) + 1)
        ws_tp.column_dimensions['A'].width = 14

        if len(all_days_tp) > 1:
            add_line_chart(ws_tp, "Network Peak Throughput (Gbps)",
                           min_col=2, max_col=3, min_row=h_row_tp, max_row=e_row_tp,
                           cat_col=1, target_cell=f"A{e_row_tp + 2}")
            add_line_chart(ws_tp, "Huawei vs Ericsson Throughput (Gbps)",
                           min_col=4, max_col=7, min_row=h_row_tp, max_row=e_row_tp,
                           cat_col=1, target_cell=f"A{e_row_tp + 18}")
        print("  Sheet: Throughput Gbps")

        # ---- Sheet 5: Traffic (TB) — Daily SUM ----
        ws_traf = wb.create_sheet("Traffic TB")
        ws_traf.cell(1, 1, "Daily Traffic Volume (TB)").font = TITLE_FONT

        traf_agg = {}
        for k in ["dl_4g", "ul_4g", "dl_23g", "ul_23g"]:
            if traffic_cols[k]:
                traf_agg[traffic_cols[k]] = "sum"
        hw_traf_daily = df_traffic.groupby("_date").agg(traf_agg)

        er_traf_agg = {}
        sgi_dl = find_cols(df_epg.columns, "S5", "Downlink", "Traffic")
        sgi_ul = find_cols(df_epg.columns, "S5", "Uplink", "Traffic")
        gn_dl = find_cols(df_epg.columns, "Gn", "Downlink", "Traffic")
        gn_ul = find_cols(df_epg.columns, "Gn", "Uplink", "Traffic")
        for cl in [sgi_dl, sgi_ul, gn_dl, gn_ul]:
            if cl:
                er_traf_agg[cl[0]] = "sum"
        er_traf_daily = df_epg.groupby("_date").agg(er_traf_agg)

        all_days_traf = sorted(set(hw_traf_daily.index) | set(er_traf_daily.index))

        traf_col_names = ["Huawei SGi (4G)", "Huawei Gi (2G/3G)", "Ericsson S5 (4G)",
                          "Ericsson Gn (2G/3G)", "Total SGi/S5", "Total Gi/Gn", "Grand Total"]
        traf_data = {n: {} for n in traf_col_names}

        for d in all_days_traf:
            hw_s = hw_g = er_s = er_g = 0
            if d in hw_traf_daily.index:
                rr = hw_traf_daily.loc[d]
                hw_s = (float(rr.get(traffic_cols["dl_4g"], 0) or 0) + float(rr.get(traffic_cols["ul_4g"], 0) or 0)) * KB_TO_TB
                hw_g = (float(rr.get(traffic_cols["dl_23g"], 0) or 0) + float(rr.get(traffic_cols["ul_23g"], 0) or 0)) * KB_TO_TB
            if d in er_traf_daily.index:
                rr = er_traf_daily.loc[d]
                for c in [sgi_dl, sgi_ul]:
                    if c: er_s += float(rr.get(c[0], 0) or 0) * MB_TO_TB
                for c in [gn_dl, gn_ul]:
                    if c: er_g += float(rr.get(c[0], 0) or 0) * MB_TO_TB
            traf_data["Huawei SGi (4G)"][d] = hw_s
            traf_data["Huawei Gi (2G/3G)"][d] = hw_g
            traf_data["Ericsson S5 (4G)"][d] = er_s
            traf_data["Ericsson Gn (2G/3G)"][d] = er_g
            traf_data["Total SGi/S5"][d] = hw_s + er_s
            traf_data["Total Gi/Gn"][d] = hw_g + er_g
            traf_data["Grand Total"][d] = hw_s + hw_g + er_s + er_g

        h_row_tr, e_row_tr = write_daily_table(ws_traf, "", 2, all_days_traf, traf_col_names, traf_data, num_fmt=DEC2_FMT)
        auto_width(ws_traf, len(traf_col_names) + 1)
        ws_traf.column_dimensions['A'].width = 14

        if len(all_days_traf) > 1:
            add_line_chart(ws_traf, "Daily Traffic (TB)",
                           min_col=6, max_col=8, min_row=h_row_tr, max_row=e_row_tr,
                           cat_col=1, target_cell=f"A{e_row_tr + 2}")
            add_line_chart(ws_traf, "Huawei vs Ericsson Daily Traffic (TB)",
                           min_col=2, max_col=5, min_row=h_row_tr, max_row=e_row_tr,
                           cat_col=1, target_cell=f"A{e_row_tr + 18}")
        print("  Sheet: Traffic TB")

    # ---- Sheet 6: Ericsson PDP SR — Daily AVG ----
    if df_pdp_sr_vepg is not None:
        ws_sr_e = wb.create_sheet("Ericsson PDP SR")
        ws_sr_e.cell(1, 1, "Ericsson PDP/Bearer Success Rate (%) — Daily Average").font = TITLE_FONT

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

        block_row = 3
        for sr_col, sr_label in sr_cols_found:
            sr_data = {}
            for node in sr_nodes:
                sub = df_pdp_sr_vepg[df_pdp_sr_vepg[nc_sr] == node]
                daily = sub.groupby("_date")[sr_col].mean()
                sr_data[node] = daily.to_dict()

            all_days_sr = sorted(set(d for dd in sr_data.values() for d in dd.keys()))
            h_r, e_r = write_daily_table(ws_sr_e, sr_label, block_row, all_days_sr, sr_nodes, sr_data, num_fmt='0.00')
            if len(all_days_sr) > 1:
                add_line_chart(ws_sr_e, f"{sr_label} per Node (%)",
                               min_col=2, max_col=len(sr_nodes) + 1,
                               min_row=h_r, max_row=e_r,
                               cat_col=1,
                               target_cell=f"{get_column_letter(len(sr_nodes) + 3)}{h_r}")
            block_row = e_r + 3

        auto_width(ws_sr_e, len(sr_nodes) + 1)
        ws_sr_e.column_dimensions['A'].width = 14
        print("  Sheet: Ericsson PDP SR")

    # ---- Sheet 7: Huawei PDP SR — Daily AVG ----
    if df_pdp_sr_vugw is not None:
        ws_sr_h = wb.create_sheet("Huawei PDP SR")
        ws_sr_h.cell(1, 1, "Huawei PDP/Bearer Success Rate (%) — Daily Average").font = TITLE_FONT

        pdp_sr = find_col(df_pdp_sr_vugw.columns, "PDP", "success", "ratio")
        br_sr = find_col(df_pdp_sr_vugw.columns, "bearer", "success", "ratio")
        hw_sr_nodes = df_pdp_sr_vugw["NE Name"].unique().tolist()

        block_row = 3
        for sr_col, sr_label in [(pdp_sr, "PDP Context SR (2G/3G)"), (br_sr, "Bearer Context SR (4G)")]:
            if not sr_col:
                continue
            df_pdp_sr_vugw[sr_col] = pd.to_numeric(df_pdp_sr_vugw[sr_col], errors="coerce")

            sr_data = {}
            for node in hw_sr_nodes:
                sub = df_pdp_sr_vugw[df_pdp_sr_vugw["NE Name"] == node]
                daily = sub.groupby("_date")[sr_col].mean()
                sr_data[node] = daily.to_dict()

            all_days_sr = sorted(set(d for dd in sr_data.values() for d in dd.keys()))
            h_r, e_r = write_daily_table(ws_sr_h, sr_label, block_row, all_days_sr, hw_sr_nodes, sr_data, num_fmt='0.000')
            if len(all_days_sr) > 1:
                add_line_chart(ws_sr_h, f"{sr_label} per Node (%)",
                               min_col=2, max_col=len(hw_sr_nodes) + 1,
                               min_row=h_r, max_row=e_r,
                               cat_col=1,
                               target_cell=f"{get_column_letter(len(hw_sr_nodes) + 3)}{h_r}")
            block_row = e_r + 3

        auto_width(ws_sr_h, len(hw_sr_nodes) + 1)
        ws_sr_h.column_dimensions['A'].width = 14
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
