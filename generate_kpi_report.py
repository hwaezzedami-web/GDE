#!/usr/bin/env python3
"""
PS Core KPI Report Generator
=============================
Automates creation of the PS Core Performance Report PowerPoint.

Usage:
    python generate_kpi_report.py

Place your KPI Excel files in the 'input/' folder (directly or in a subfolder).
No separate SAU.xlsx needed - the SAU table is computed from the raw data.

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
from pptx.util import Pt, Emu
from pptx.enum.chart import XL_CHART_TYPE
from pptx.dml.color import RGBColor

SCRIPT_DIR = Path(__file__).parent.resolve()
INPUT_DIR = SCRIPT_DIR / "input"
TEMPLATE_PATH = SCRIPT_DIR / "template.pptx"
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


def find_file(kpi_dir, pattern):
    matches = glob.glob(os.path.join(kpi_dir, pattern))
    if not matches:
        print(f"  WARNING: No file matching '{pattern}' in {kpi_dir}")
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
    result = []
    for c in columns:
        cl = c.lower()
        if all(k.lower() in cl for k in keywords):
            if exclude and any(e.lower() in cl for e in exclude):
                continue
            result.append(c)
    return result


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


def fmt_num(val):
    try:
        n = int(round(float(val)))
        return f"{n:,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(val)


def format_date_long(dt):
    return dt.strftime("%d %B %Y")


def compute_sau_table(df_vusn, df_attach):
    rows = []

    if df_vusn is not None:
        sau_2g_col = find_col(df_vusn.columns, "Gb", "attached", "users")
        sau_3g_col = find_col(df_vusn.columns, "Iu", "attached", "users")
        sau_4g_col = find_col(df_vusn.columns, "maximum attached users", exclude=["Gb", "Iu"])
        pdp_2g_col = find_col(df_vusn.columns, "Gb", "PDP")
        pdp_3g_col = find_col(df_vusn.columns, "Iu", "PDP")
        bearer_4g_col = find_col(df_vusn.columns, "bearer", "S1") or find_col(df_vusn.columns, "Maximum bearer")

        for col in [sau_2g_col, sau_3g_col, sau_4g_col, pdp_2g_col, pdp_3g_col, bearer_4g_col]:
            if col:
                df_vusn[col] = pd.to_numeric(df_vusn[col], errors="coerce")

        for node in HUAWEI_NODES_USN:
            sub = df_vusn[df_vusn["NE Name"] == node]
            if len(sub) == 0:
                continue
            s2g = sub[sau_2g_col].max() if sau_2g_col else 0
            s3g = sub[sau_3g_col].max() if sau_3g_col else 0
            s4g = sub[sau_4g_col].max() if sau_4g_col else 0
            p2g = sub[pdp_2g_col].max() if pdp_2g_col else 0
            p3g = sub[pdp_3g_col].max() if pdp_3g_col else 0
            b4g = sub[bearer_4g_col].max() if bearer_4g_col else 0
            rows.append({
                "Node": node,
                "SAU 2G": s2g, "SAU 3G": s3g, "SAU 4G": s4g,
                "PDP 2G": p2g, "PDP 3G": p3g, "Bearer  4G": b4g,
                "Total SAU": s2g + s3g + s4g,
                "Total PDP/Bearer Context": p2g + p3g + b4g,
            })

    if df_attach is not None:
        name_col = "SGSN Name" if "SGSN Name" in df_attach.columns else "GGSN Name"
        sau_2g = find_col(df_attach.columns, "SAU", "2G")
        sau_3g = find_col(df_attach.columns, "SAU", "3G")
        sau_4g = find_col(df_attach.columns, "SAU", "4G")
        pdp_2g = find_col(df_attach.columns, "PDP", "2G")
        pdp_3g = find_col(df_attach.columns, "PDP", "3G")
        bearer_4g = find_col(df_attach.columns, "Bearer", "4G")

        for col in [sau_2g, sau_3g, sau_4g, pdp_2g, pdp_3g, bearer_4g]:
            if col:
                df_attach[col] = pd.to_numeric(df_attach[col], errors="coerce")

        for node in ERICSSON_NODES_MME:
            sub = df_attach[df_attach[name_col] == node]
            if len(sub) == 0:
                continue
            s2g = sub[sau_2g].max() if sau_2g else 0
            s3g = sub[sau_3g].max() if sau_3g else 0
            s4g = sub[sau_4g].max() if sau_4g else 0
            p2g = sub[pdp_2g].max() if pdp_2g else 0
            p3g = sub[pdp_3g].max() if pdp_3g else 0
            b4g = sub[bearer_4g].max() if bearer_4g else 0
            rows.append({
                "Node": node,
                "SAU 2G": s2g, "SAU 3G": s3g, "SAU 4G": s4g,
                "PDP 2G": p2g, "PDP 3G": p3g, "Bearer  4G": b4g,
                "Total SAU": s2g + s3g + s4g,
                "Total PDP/Bearer Context": p2g + p3g + b4g,
            })

    return pd.DataFrame(rows)


def update_line_chart(chart, categories, series_dict):
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


def remove_images(slide):
    """Remove all picture shapes from a slide."""
    for shape in list(slide.shapes):
        if shape.shape_type == 13:  # PICTURE
            sp = shape._element
            sp.getparent().remove(sp)


def add_chart_to_slide(slide, chart_type, categories, series_dict,
                       left=Emu(645160), top=Emu(2100000),
                       width=Emu(10900000), height=Emu(4400000)):
    """Add a chart to an existing slide."""
    chart_data = CategoryChartData()
    chart_data.categories = categories
    for name, values in series_dict.items():
        chart_data.add_series(name, values)
    chart_frame = slide.shapes.add_chart(
        chart_type, left, top, width, height, chart_data
    )
    chart = chart_frame.chart
    chart.has_legend = True
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(8)
    chart.value_axis.has_title = False
    chart.value_axis.major_gridlines.format.line.color.rgb = RGBColor(220, 220, 220)
    if len(categories) > 50:
        chart.category_axis.tick_labels.font.size = Pt(6)
    return chart


def add_chart_slide(prs, title, subtitle, categories, series_dict, insert_before_idx=None):
    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)

    for shape in list(slide.placeholders):
        sp = shape._element
        sp.getparent().remove(sp)

    if insert_before_idx is not None:
        xml_slides = prs.slides._sldIdLst
        slides_list = list(xml_slides)
        new_slide_elem = slides_list[-1]
        xml_slides.remove(new_slide_elem)
        xml_slides.insert(insert_before_idx, new_slide_elem)

    txBox = slide.shapes.add_textbox(Emu(645160), Emu(266931), Emu(9063892), Emu(548483))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0, 51, 102)

    txBox2 = slide.shapes.add_textbox(Emu(645160), Emu(815414), Emu(9063892), Emu(400000))
    tf2 = txBox2.text_frame
    p2 = tf2.paragraphs[0]
    p2.text = subtitle
    p2.font.size = Pt(12)
    p2.font.color.rgb = RGBColor(100, 100, 100)

    chart_data = CategoryChartData()
    chart_data.categories = categories
    for name, values in series_dict.items():
        chart_data.add_series(name, values)

    chart_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE, Emu(645160), Emu(1300000),
        Emu(10900000), Emu(5200000), chart_data
    )
    chart = chart_frame.chart
    chart.has_legend = True
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(8)
    chart.value_axis.has_title = False
    chart.value_axis.major_gridlines.format.line.color.rgb = RGBColor(220, 220, 220)
    if len(categories) > 50:
        chart.category_axis.tick_labels.font.size = Pt(6)

    return slide


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

    if not TEMPLATE_PATH.exists():
        print(f"ERROR: Template not found at {TEMPLATE_PATH}")
        sys.exit(1)
    if not INPUT_DIR.exists():
        print(f"ERROR: Input directory not found at {INPUT_DIR}")
        sys.exit(1)

    # Extract RAR if found
    for f in os.listdir(INPUT_DIR):
        if f.lower().endswith(".rar"):
            print(f"  Extracting RAR: {f}")
            try:
                import subprocess
                subprocess.run(["unrar", "x", "-o+", os.path.join(INPUT_DIR, f), str(INPUT_DIR) + "/"],
                               check=True, capture_output=True)
            except Exception as e:
                print(f"  WARNING: Could not extract RAR: {e}")
                print("  Please extract it manually into the input/ folder.")

    kpi_dir = find_kpi_folder(INPUT_DIR)
    if not kpi_dir:
        print("ERROR: No KPI data files found in input/")
        sys.exit(1)
    print(f"  KPI folder: {kpi_dir}")

    # Detect date range from folder name
    dirname = os.path.basename(kpi_dir)
    start_date = end_date = None
    m = re.search(r"(\d{2})-(\d{2})\s+(\d{2})-(\d{2})-(\d{4})", dirname)
    if m:
        d1, m1, d2, m2, y = m.groups()
        start_date = datetime(int(y), int(m1), int(d1))
        end_date = datetime(int(y), int(m2), int(d2))

    # Load data files
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

    # Compute SAU table from raw data
    print("\nComputing SAU summary table...")
    sau_df = compute_sau_table(df_vusn, df_attach)
    print(f"  {len(sau_df)} nodes computed")

    df_traffic = None
    traffic_cols = None
    if "vugw_traffic" in files:
        df_raw = read_huawei_export(files["vugw_traffic"])
        for col in df_raw.columns:
            if col not in ["Start Time", "NE Name", "Period (min)", "CGW function", "DGW function"]:
                df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce")
        traffic_cols = {
            "dl_4g": find_col(df_raw.columns, "SGi", "downlink", "traffic", exclude=["peak"]),
            "ul_4g": find_col(df_raw.columns, "SGi", "uplink", "traffic", exclude=["peak"]),
            "dl_4g_peak": find_col(df_raw.columns, "SGi", "downlink", "peak"),
            "ul_4g_peak": find_col(df_raw.columns, "SGi", "uplink", "peak"),
            "dl_23g": find_col(df_raw.columns, "2/3G", "Gi", "downlink", "traffic", exclude=["peak"]),
            "ul_23g": find_col(df_raw.columns, "2/3G", "Gi", "uplink", "traffic", exclude=["peak"]),
            "dl_23g_peak": find_col(df_raw.columns, "2/3G", "Gi", "downlink", "peak"),
            "ul_23g_peak": find_col(df_raw.columns, "2/3G", "Gi", "uplink", "peak"),
        }
        df_traffic = df_raw
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

    # Auto-detect date range from data if not from folder
    if not start_date:
        all_dates = []
        if df_traffic is not None:
            all_dates.extend(df_traffic["Start Time"].dropna().tolist())
        if df_attach is not None:
            all_dates.extend(df_attach["Date"].dropna().tolist())
        if all_dates:
            start_date = min(all_dates)
            end_date = max(all_dates)
            if hasattr(start_date, 'to_pydatetime'):
                start_date = start_date.to_pydatetime()
                end_date = end_date.to_pydatetime()

    if start_date:
        print(f"\n  Date range: {format_date_long(start_date)} - {format_date_long(end_date)}")

    # -----------------------------------------------------------------------
    # Build PowerPoint
    # -----------------------------------------------------------------------
    print("\nGenerating PowerPoint...")
    prs = Presentation(str(TEMPLATE_PATH))

    # Slide 1: Title
    slide1 = prs.slides[0]
    for shape in slide1.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if re.search(r"\d{2}\s+\w+\s+\d{4}", run.text) and start_date and end_date:
                        run.text = re.sub(
                            r"\d{2}\s+\w+\s+\d{4}\s*[–-]\s*\d{2}\s+\w+\s+\d{4}",
                            f"{format_date_long(start_date)} – {format_date_long(end_date)}",
                            run.text
                        )
    print("  Slide 1: Title updated")

    # Slide 4: SAU/PDP Table
    slide4 = prs.slides[3]
    for shape in slide4.shapes:
        if shape.has_table:
            tbl = shape.table
            node_order = ["BMR_CloudUSN", "ANB_CloudUSN", "OUG_CloudUSN",
                          "MMEMUS1", "MMEORN1", "vMMEORN1", "vMMEBMR1"]
            value_cols = ["SAU 2G", "SAU 3G", "SAU 4G", "PDP 2G",
                          "PDP 3G", "Bearer  4G", "Total SAU",
                          "Total PDP/Bearer Context"]
            totals = [0.0] * len(value_cols)
            for r_idx, node_name in enumerate(node_order):
                row_data = sau_df[sau_df["Node"].str.strip() == node_name]
                if len(row_data) == 0:
                    continue
                row = row_data.iloc[0]
                tbl.cell(r_idx + 1, 0).text = node_name
                for c_idx, col_name in enumerate(value_cols):
                    val = row.get(col_name, 0)
                    if pd.isna(val):
                        val = 0
                    tbl.cell(r_idx + 1, c_idx + 1).text = fmt_num(val)
                    totals[c_idx] += float(val)
            total_row_idx = min(len(node_order) + 1, len(tbl.rows) - 1)
            tbl.cell(total_row_idx, 0).text = "Total "
            for c_idx, t in enumerate(totals):
                tbl.cell(total_row_idx, c_idx + 1).text = fmt_num(t)
    print("  Slide 4: SAU/PDP table updated")

    # Slide 5: Dashboard pie charts
    slide5 = prs.slides[4]
    huawei_total_traffic = 0.0
    ericsson_total_traffic = 0.0
    total_4g_traffic = 0.0
    total_23g_traffic = 0.0

    sgi_dl_col = sgi_ul_col = gn_dl_col = gn_ul_col = []

    if df_traffic is not None and traffic_cols:
        for _, row in df_traffic.iterrows():
            dl = float(row.get(traffic_cols["dl_4g"], 0) or 0)
            ul = float(row.get(traffic_cols["ul_4g"], 0) or 0)
            dl23 = float(row.get(traffic_cols["dl_23g"], 0) or 0)
            ul23 = float(row.get(traffic_cols["ul_23g"], 0) or 0)
            huawei_total_traffic += (dl + ul + dl23 + ul23) * KB_TO_TB
            total_4g_traffic += (dl + ul) * KB_TO_TB
            total_23g_traffic += (dl23 + ul23) * KB_TO_TB

    if df_epg is not None:
        sgi_dl_col = find_cols(df_epg.columns, "S5", "Downlink", "Traffic")
        sgi_ul_col = find_cols(df_epg.columns, "S5", "Uplink", "Traffic")
        gn_dl_col = find_cols(df_epg.columns, "Gn", "Downlink", "Traffic")
        gn_ul_col = find_cols(df_epg.columns, "Gn", "Uplink", "Traffic")
        for _, row in df_epg.iterrows():
            sgi_mb = sum(float(row.get(c[0], 0) or 0) for c in [sgi_dl_col, sgi_ul_col] if c)
            gn_mb = sum(float(row.get(c[0], 0) or 0) for c in [gn_dl_col, gn_ul_col] if c)
            ericsson_total_traffic += (sgi_mb + gn_mb) * MB_TO_TB
            total_4g_traffic += sgi_mb * MB_TO_TB
            total_23g_traffic += gn_mb * MB_TO_TB

    # Remove old static images from slide 5
    remove_images(slide5)
    for shape in slide5.shapes:
        try:
            if shape.has_chart:
                ch = shape.chart
                if shape.name == "Graphique 8":
                    update_pie_chart(ch, ["Huawei ", "Ericsson"],
                                     [huawei_total_traffic, ericsson_total_traffic])
                elif "DOUGHNUT" in ch.chart_type.name:
                    update_pie_chart(ch, ["4G ", "2G/3G"],
                                     [total_4g_traffic, total_23g_traffic])
                elif "PIE" in ch.chart_type.name:
                    update_pie_chart(ch, ["Huawei ", "Ericsson"],
                                     [huawei_total_traffic, ericsson_total_traffic])
        except Exception as e:
            print(f"  WARNING: Chart on slide 5: {e}")
    print("  Slide 5: Dashboard charts updated")

    # --- Slides 6-9: Replace static images with real charts ---
    # Build hourly time series for SAU and PDP per node
    all_node_sau_hourly = {}  # {node: {time: {sau_2g, sau_3g, sau_4g, pdp_2g, pdp_3g, bearer_4g}}}
    hourly_times_all = set()

    if df_vusn is not None:
        sau_2g_col = find_col(df_vusn.columns, "Gb", "attached", "users")
        sau_3g_col = find_col(df_vusn.columns, "Iu", "attached", "users")
        sau_4g_col = find_col(df_vusn.columns, "maximum attached users", exclude=["Gb", "Iu"])
        pdp_2g_col = find_col(df_vusn.columns, "Gb", "PDP")
        pdp_3g_col = find_col(df_vusn.columns, "Iu", "PDP")
        bearer_4g_col = find_col(df_vusn.columns, "bearer", "S1") or find_col(df_vusn.columns, "Maximum bearer")

        for col in [sau_2g_col, sau_3g_col, sau_4g_col, pdp_2g_col, pdp_3g_col, bearer_4g_col]:
            if col:
                df_vusn[col] = pd.to_numeric(df_vusn[col], errors="coerce")

        for node in HUAWEI_NODES_USN:
            sub = df_vusn[df_vusn["NE Name"] == node].sort_values("Start Time")
            if len(sub) == 0:
                continue
            times = sub["Start Time"].tolist()
            hourly_times_all.update(times)
            all_node_sau_hourly[node] = {
                "times": times,
                "sau_2g": sub[sau_2g_col].fillna(0).tolist() if sau_2g_col else [],
                "sau_3g": sub[sau_3g_col].fillna(0).tolist() if sau_3g_col else [],
                "sau_4g": sub[sau_4g_col].fillna(0).tolist() if sau_4g_col else [],
                "pdp_2g": sub[pdp_2g_col].fillna(0).tolist() if pdp_2g_col else [],
                "pdp_3g": sub[pdp_3g_col].fillna(0).tolist() if pdp_3g_col else [],
                "bearer_4g": sub[bearer_4g_col].fillna(0).tolist() if bearer_4g_col else [],
            }

    if df_attach is not None:
        a_name_col = "SGSN Name" if "SGSN Name" in df_attach.columns else "GGSN Name"
        a_sau_2g = find_col(df_attach.columns, "SAU", "2G")
        a_sau_3g = find_col(df_attach.columns, "SAU", "3G")
        a_sau_4g = find_col(df_attach.columns, "SAU", "4G")
        a_pdp_2g = find_col(df_attach.columns, "PDP", "2G")
        a_pdp_3g = find_col(df_attach.columns, "PDP", "3G")
        a_bearer_4g = find_col(df_attach.columns, "Bearer", "4G")

        for col in [a_sau_2g, a_sau_3g, a_sau_4g, a_pdp_2g, a_pdp_3g, a_bearer_4g]:
            if col:
                df_attach[col] = pd.to_numeric(df_attach[col], errors="coerce")

        for node in ERICSSON_NODES_MME:
            sub = df_attach[df_attach[a_name_col] == node].sort_values("datetime")
            if len(sub) == 0:
                continue
            times = sub["datetime"].tolist()
            hourly_times_all.update(times)
            all_node_sau_hourly[node] = {
                "times": times,
                "sau_2g": sub[a_sau_2g].fillna(0).tolist() if a_sau_2g else [],
                "sau_3g": sub[a_sau_3g].fillna(0).tolist() if a_sau_3g else [],
                "sau_4g": sub[a_sau_4g].fillna(0).tolist() if a_sau_4g else [],
                "pdp_2g": sub[a_pdp_2g].fillna(0).tolist() if a_pdp_2g else [],
                "pdp_3g": sub[a_pdp_3g].fillna(0).tolist() if a_pdp_3g else [],
                "bearer_4g": sub[a_bearer_4g].fillna(0).tolist() if a_bearer_4g else [],
            }

    if all_node_sau_hourly:
        sorted_times = sorted(hourly_times_all)
        time_cats = [t.strftime("%Y-%m-%d %H:%M") for t in sorted_times]

        def build_node_series(metric):
            series = {}
            for node, data in all_node_sau_hourly.items():
                td = dict(zip(data["times"], data[metric]))
                series[node] = [td.get(t, 0) for t in sorted_times]
            return series

        # Slide 6: Attached Users per Node (SAU 4G per node over time)
        slide6 = prs.slides[5]
        remove_images(slide6)
        add_chart_to_slide(slide6, XL_CHART_TYPE.LINE, time_cats,
                           build_node_series("sau_4g"))
        print("  Slide 6: Attached Users per Node chart added")

        # Slide 7: Active PDP Context per Node (Bearer 4G per node over time)
        slide7 = prs.slides[6]
        remove_images(slide7)
        add_chart_to_slide(slide7, XL_CHART_TYPE.LINE, time_cats,
                           build_node_series("bearer_4g"))
        print("  Slide 7: Active PDP Context per Node chart added")

        # Slide 8: Total Attached Users & Total PDP Context (2 charts side by side)
        slide8 = prs.slides[7]
        remove_images(slide8)
        # Total SAU per node = sau_2g + sau_3g + sau_4g
        total_sau_series = {}
        total_pdp_series = {}
        for node, data in all_node_sau_hourly.items():
            td_2g = dict(zip(data["times"], data["sau_2g"]))
            td_3g = dict(zip(data["times"], data["sau_3g"]))
            td_4g = dict(zip(data["times"], data["sau_4g"]))
            total_sau_series[node] = [td_2g.get(t, 0) + td_3g.get(t, 0) + td_4g.get(t, 0) for t in sorted_times]
            td_p2g = dict(zip(data["times"], data["pdp_2g"]))
            td_p3g = dict(zip(data["times"], data["pdp_3g"]))
            td_b4g = dict(zip(data["times"], data["bearer_4g"]))
            total_pdp_series[node] = [td_p2g.get(t, 0) + td_p3g.get(t, 0) + td_b4g.get(t, 0) for t in sorted_times]

        add_chart_to_slide(slide8, XL_CHART_TYPE.LINE, time_cats, total_sau_series,
                           left=Emu(500000), top=Emu(2200000),
                           width=Emu(5500000), height=Emu(3800000))
        add_chart_to_slide(slide8, XL_CHART_TYPE.LINE, time_cats, total_pdp_series,
                           left=Emu(6200000), top=Emu(2200000),
                           width=Emu(5500000), height=Emu(3800000))
        print("  Slide 8: Total SAU & PDP charts added")

        # Slide 9: Peak Throughput per Node (from vUGW traffic data)
        slide9 = prs.slides[8]
        remove_images(slide9)
        if df_traffic is not None and traffic_cols:
            tp_series = {}
            for node in df_traffic["NE Name"].unique():
                sub = df_traffic[df_traffic["NE Name"] == node].sort_values("Start Time")
                times_n = sub["Start Time"].tolist()
                dl_peak = sub[traffic_cols["dl_4g_peak"]].fillna(0) if traffic_cols["dl_4g_peak"] else 0
                ul_peak = sub[traffic_cols["ul_4g_peak"]].fillna(0) if traffic_cols["ul_4g_peak"] else 0
                dl_23_peak = sub[traffic_cols["dl_23g_peak"]].fillna(0) if traffic_cols["dl_23g_peak"] else 0
                ul_23_peak = sub[traffic_cols["ul_23g_peak"]].fillna(0) if traffic_cols["ul_23g_peak"] else 0
                total_tp = ((dl_peak + ul_peak + dl_23_peak + ul_23_peak) * KBS_TO_GBPS).tolist()
                tp_series[node] = total_tp
            hw_tp_times = df_traffic.sort_values("Start Time")["Start Time"].unique()
            hw_tp_cats = [pd.Timestamp(t).strftime("%Y-%m-%d %H:%M") for t in hw_tp_times]
            # Re-align per node to common time axis
            tp_series_aligned = {}
            for node in df_traffic["NE Name"].unique():
                sub = df_traffic[df_traffic["NE Name"] == node].set_index("Start Time")
                vals = []
                for t in hw_tp_times:
                    t = pd.Timestamp(t)
                    if t in sub.index:
                        r = sub.loc[t]
                        if isinstance(r, pd.DataFrame):
                            r = r.iloc[0]
                        v = sum(float(r.get(traffic_cols[k], 0) or 0) for k in ["dl_4g_peak", "ul_4g_peak", "dl_23g_peak", "ul_23g_peak"] if traffic_cols[k])
                        vals.append(v * KBS_TO_GBPS)
                    else:
                        vals.append(0)
                tp_series_aligned[node] = vals
            add_chart_to_slide(slide9, XL_CHART_TYPE.LINE, hw_tp_cats, tp_series_aligned)
            print("  Slide 9: Peak Throughput per Node chart added")
    else:
        print("  WARNING: No SAU/PDP hourly data available for slides 6-9")

    # Throughput and traffic slides (10-23)
    if df_traffic is not None and traffic_cols and df_epg is not None:
        peak_cols = [traffic_cols[k] for k in ["dl_4g_peak", "ul_4g_peak", "dl_23g_peak", "ul_23g_peak"] if traffic_cols[k]]
        traf_cols_list = [traffic_cols[k] for k in ["dl_4g", "ul_4g", "dl_23g", "ul_23g"] if traffic_cols[k]]

        hw_grouped = df_traffic.groupby("Start Time").agg({c: "sum" for c in peak_cols}).sort_index()
        hw_times = hw_grouped.index.tolist()
        hw_dl = ((hw_grouped[traffic_cols["dl_4g_peak"]] + hw_grouped[traffic_cols["dl_23g_peak"]]) * KBS_TO_GBPS).tolist()
        hw_ul = ((hw_grouped[traffic_cols["ul_4g_peak"]] + hw_grouped[traffic_cols["ul_23g_peak"]]) * KBS_TO_GBPS).tolist()

        # Ericsson throughput
        s5_dl_tp = find_cols(df_epg.columns, "S5", "Downlink") and find_cols(df_epg.columns, "S5", "Downlink", "hrought")
        s5_ul_tp = find_cols(df_epg.columns, "S5", "plink", "hroughput") or find_cols(df_epg.columns, "S5", "Uplink", "hroughput")
        gn_dl_tp = find_cols(df_epg.columns, "Gn", "Downlink", "hroughput")
        gn_ul_tp = find_cols(df_epg.columns, "Gn", "Uplink", "hroughput")

        er_agg = {}
        for cols in [s5_dl_tp, s5_ul_tp, gn_dl_tp, gn_ul_tp]:
            if cols:
                er_agg[cols[0]] = "sum"
        er_grouped = df_epg.groupby("datetime").agg(er_agg).sort_index()
        er_times = er_grouped.index.tolist()

        er_dl = []
        er_ul = []
        for _, row in er_grouped.iterrows():
            dl = sum(float(row.get(c[0], 0) or 0) for c in [s5_dl_tp, gn_dl_tp] if c)
            ul = sum(float(row.get(c[0], 0) or 0) for c in [s5_ul_tp, gn_ul_tp] if c)
            er_dl.append(dl * MBPS_TO_GBPS)
            er_ul.append(ul * MBPS_TO_GBPS)

        all_times = sorted(set(hw_times) | set(er_times))
        hw_dl_d = dict(zip(hw_times, hw_dl))
        hw_ul_d = dict(zip(hw_times, hw_ul))
        er_dl_d = dict(zip(er_times, er_dl))
        er_ul_d = dict(zip(er_times, er_ul))

        cats_str = [t.strftime("%Y-%m-%d %H:%M:%S") for t in all_times]
        hw_cats = [t.strftime("%Y-%m-%d %H:%M:%S") for t in hw_times]
        er_cats = [t.strftime("%Y-%m-%d %H:%M:%S") for t in er_times]

        net_dl = [hw_dl_d.get(t, 0) + er_dl_d.get(t, 0) for t in all_times]
        net_ul = [hw_ul_d.get(t, 0) + er_ul_d.get(t, 0) for t in all_times]

        def update_slide_chart(slide_idx, series):
            slide = prs.slides[slide_idx]
            for shape in slide.shapes:
                try:
                    if shape.has_chart:
                        update_line_chart(shape.chart, series[0], series[1])
                except:
                    pass

        # Slide 10: Network throughput
        update_slide_chart(9, (cats_str, {"DL Throughput": net_dl, " UL Throughput": net_ul}))
        print("  Slide 10: Network throughput updated")

        # Slide 11: Huawei throughput
        update_slide_chart(10, (hw_cats, {"DL Throughput": hw_dl, "UL Throughput": hw_ul}))
        print("  Slide 11: Huawei throughput updated")

        # Slide 12: Ericsson throughput
        update_slide_chart(11, (er_cats, {"DL Throughput": er_dl, "UL Throughput": er_ul}))
        print("  Slide 12: Ericsson throughput updated")

        # Slide 13: Throughput per pool
        hw_tot = [hw_dl_d.get(t, 0) + hw_ul_d.get(t, 0) for t in all_times]
        er_tot = [er_dl_d.get(t, 0) + er_ul_d.get(t, 0) for t in all_times]
        update_slide_chart(12, (cats_str, {"Huawei": hw_tot, "Ericsson": er_tot}))
        print("  Slide 13: Throughput per pool updated")

        # Slide 14: Per-node Huawei throughput
        dgw_series = {}
        for dn, nodes in DGW_DISPLAY.items():
            sub = df_traffic[df_traffic["NE Name"].isin(nodes)]
            g = sub.groupby("Start Time").agg({c: "sum" for c in peak_cols}).sort_index()
            dgw_series[dn] = (sum(g[c] for c in peak_cols) * KBS_TO_GBPS).tolist()
        update_slide_chart(13, (hw_cats, dgw_series))
        print("  Slide 14: Huawei per-node throughput updated")

        # Slide 15: Per-node Ericsson throughput
        name_col_epg = "GGSN Name" if "GGSN Name" in df_epg.columns else "GGSN"
        epg_series = {}
        tp_agg = {c[0]: "sum" for c in [s5_dl_tp, s5_ul_tp, gn_dl_tp, gn_ul_tp] if c}
        for dn, nodes in EPG_DISPLAY.items():
            sub = df_epg[df_epg[name_col_epg].isin(nodes)]
            if not tp_agg:
                continue
            g = sub.groupby("datetime").agg(tp_agg).sort_index()
            epg_series[dn + " TP"] = (sum(g[c] for c in tp_agg) * MBPS_TO_GBPS).tolist()
        update_slide_chart(14, (er_cats, epg_series))
        print("  Slide 15: Ericsson per-node throughput updated")

        # Traffic in TB
        hw_traf_grouped = df_traffic.groupby("Start Time").agg({c: "sum" for c in traf_cols_list}).sort_index()
        hw_dl_tb = ((hw_traf_grouped[traffic_cols["dl_4g"]] + hw_traf_grouped[traffic_cols["dl_23g"]]) * KB_TO_TB).tolist()
        hw_ul_tb = ((hw_traf_grouped[traffic_cols["ul_4g"]] + hw_traf_grouped[traffic_cols["ul_23g"]]) * KB_TO_TB).tolist()

        er_traf_agg = {}
        for cols in [sgi_dl_col, sgi_ul_col, gn_dl_col, gn_ul_col]:
            if cols:
                er_traf_agg[cols[0]] = "sum"
        er_traf_grouped = df_epg.groupby("datetime").agg(er_traf_agg).sort_index()

        er_dl_tb = []
        er_ul_tb = []
        er_sgi_tb = []
        er_gi_tb = []
        for _, row in er_traf_grouped.iterrows():
            dl = sum(float(row.get(c[0], 0) or 0) for c in [sgi_dl_col, gn_dl_col] if c)
            ul = sum(float(row.get(c[0], 0) or 0) for c in [sgi_ul_col, gn_ul_col] if c)
            sgi = sum(float(row.get(c[0], 0) or 0) for c in [sgi_dl_col, sgi_ul_col] if c)
            gi = sum(float(row.get(c[0], 0) or 0) for c in [gn_dl_col, gn_ul_col] if c)
            er_dl_tb.append(dl * MB_TO_TB)
            er_ul_tb.append(ul * MB_TO_TB)
            er_sgi_tb.append(sgi * MB_TO_TB)
            er_gi_tb.append(gi * MB_TO_TB)

        hw_dl_t_d = dict(zip(hw_traf_grouped.index.tolist(), hw_dl_tb))
        hw_ul_t_d = dict(zip(hw_traf_grouped.index.tolist(), hw_ul_tb))
        er_dl_t_d = dict(zip(er_traf_grouped.index.tolist(), er_dl_tb))
        er_ul_t_d = dict(zip(er_traf_grouped.index.tolist(), er_ul_tb))

        # Slide 16-18: Network/Huawei/Ericsson traffic
        net_dl_t = [hw_dl_t_d.get(t, 0) + er_dl_t_d.get(t, 0) for t in all_times]
        net_ul_t = [hw_ul_t_d.get(t, 0) + er_ul_t_d.get(t, 0) for t in all_times]
        update_slide_chart(15, (cats_str, {" DL Traffic ": net_dl_t, "UL Traffic": net_ul_t}))
        print("  Slide 16: Network traffic updated")
        update_slide_chart(16, (hw_cats, {"DL Traffic": hw_dl_tb, "UL Traffic": hw_ul_tb}))
        print("  Slide 17: Huawei traffic updated")
        update_slide_chart(17, (er_cats, {"DL Traffic": er_dl_tb, "UL Traffic": er_ul_tb}))
        print("  Slide 18: Ericsson traffic updated")

        # Slide 19: Traffic per pool
        hw_total_t = [hw_dl_t_d.get(t, 0) + hw_ul_t_d.get(t, 0) for t in all_times]
        er_total_t = [er_dl_t_d.get(t, 0) + er_ul_t_d.get(t, 0) for t in all_times]
        update_slide_chart(18, (cats_str, {"Huawei Traffic in TB": hw_total_t, "Ericsson Traffic in TB": er_total_t}))
        print("  Slide 19: Traffic per pool updated")

        # SGi/Gi
        hw_sgi = ((hw_traf_grouped[traffic_cols["dl_4g"]] + hw_traf_grouped[traffic_cols["ul_4g"]]) * KB_TO_TB).tolist()
        hw_gi = ((hw_traf_grouped[traffic_cols["dl_23g"]] + hw_traf_grouped[traffic_cols["ul_23g"]]) * KB_TO_TB).tolist()
        hw_sgi_d = dict(zip(hw_traf_grouped.index.tolist(), hw_sgi))
        hw_gi_d = dict(zip(hw_traf_grouped.index.tolist(), hw_gi))
        er_sgi_d = dict(zip(er_traf_grouped.index.tolist(), er_sgi_tb))
        er_gi_d = dict(zip(er_traf_grouped.index.tolist(), er_gi_tb))

        net_sgi = [hw_sgi_d.get(t, 0) + er_sgi_d.get(t, 0) for t in all_times]
        net_gi = [hw_gi_d.get(t, 0) + er_gi_d.get(t, 0) for t in all_times]
        net_total = [s + g for s, g in zip(net_sgi, net_gi)]

        # Slide 20-21
        update_slide_chart(19, (cats_str, {"SGI Traffic ": net_sgi, "GI Traffic ": net_gi, "Traffic ": net_total}))
        print("  Slide 20: SGi/Gi network traffic updated")

        slide21 = prs.slides[20]
        chart_idx = 0
        for shape in slide21.shapes:
            try:
                if shape.has_chart:
                    if chart_idx == 0:
                        update_line_chart(shape.chart, cats_str,
                                         {"Huawei SGI": [hw_sgi_d.get(t, 0) for t in all_times],
                                          "Ericsson SGI": [er_sgi_d.get(t, 0) for t in all_times]})
                    else:
                        update_line_chart(shape.chart, cats_str,
                                         {"Huawei GI": [hw_gi_d.get(t, 0) for t in all_times],
                                          "Ericsson GI": [er_gi_d.get(t, 0) for t in all_times]})
                    chart_idx += 1
            except:
                pass
        print("  Slide 21: SGi/Gi per pool updated")

        # Daily traffic (slides 22-23)
        daily_hw = hw_traf_grouped.copy()
        daily_hw.index = daily_hw.index.date
        daily_hw = daily_hw.groupby(daily_hw.index).sum()
        daily_er = er_traf_grouped.copy()
        daily_er.index = daily_er.index.date
        daily_er = daily_er.groupby(daily_er.index).sum()
        all_days = sorted(set(daily_hw.index) | set(daily_er.index))
        day_cats = [d.strftime("%d-%b").lower() for d in all_days]

        daily_sgi = []; daily_gi = []; daily_total = []
        d_hw_sgi = []; d_hw_gi = []; d_er_sgi = []; d_er_gi = []
        for d in all_days:
            hw_s = hw_g = er_s = er_g = 0
            if d in daily_hw.index:
                r = daily_hw.loc[d]
                hw_s = (r[traffic_cols["dl_4g"]] + r[traffic_cols["ul_4g"]]) * KB_TO_TB
                hw_g = (r[traffic_cols["dl_23g"]] + r[traffic_cols["ul_23g"]]) * KB_TO_TB
            if d in daily_er.index:
                r = daily_er.loc[d]
                for c in [sgi_dl_col, sgi_ul_col]:
                    if c: er_s += float(r.get(c[0], 0) or 0) * MB_TO_TB
                for c in [gn_dl_col, gn_ul_col]:
                    if c: er_g += float(r.get(c[0], 0) or 0) * MB_TO_TB
            daily_sgi.append(hw_s + er_s)
            daily_gi.append(hw_g + er_g)
            daily_total.append(hw_s + er_s + hw_g + er_g)
            d_hw_sgi.append(hw_s); d_hw_gi.append(hw_g)
            d_er_sgi.append(er_s); d_er_gi.append(er_g)

        update_slide_chart(21, (day_cats, {" SGI Traffic": daily_sgi, " GI Traffic ": daily_gi, "Total Traffic ": daily_total}))
        print("  Slide 22: Daily network traffic updated")

        slide23 = prs.slides[22]
        chart_idx = 0
        for shape in slide23.shapes:
            try:
                if shape.has_chart:
                    if chart_idx == 0:
                        update_line_chart(shape.chart, day_cats,
                                         {"Huawei SGI": d_hw_sgi, " Ericsson SGI": d_er_sgi})
                    else:
                        update_line_chart(shape.chart, day_cats,
                                         {" Huawei GI": d_hw_gi, "Ericsson GI": d_er_gi})
                    chart_idx += 1
            except:
                pass
        print("  Slide 23: Daily per vendor traffic updated")

    # PDP/Bearer Success Rate slides
    conclusion_idx = len(prs.slides) - 1

    if df_pdp_sr_vepg is not None:
        print("  Adding Ericsson PDP/Bearer SR slides...")
        name_col = "SGSN Name" if "SGSN Name" in df_pdp_sr_vepg.columns else "GGSN Name"
        nodes = df_pdp_sr_vepg[name_col].dropna().unique().tolist()

        sr_2g = find_col(df_pdp_sr_vepg.columns, "SR", "2G", exclude=["Bearer", "LTE"])
        if not sr_2g:
            sr_2g = find_col(df_pdp_sr_vepg.columns, "Pdp", "2G")
        sr_3g = find_col(df_pdp_sr_vepg.columns, "SR", "3G", exclude=["Bearer", "LTE"])
        if not sr_3g:
            sr_3g = find_col(df_pdp_sr_vepg.columns, "Pdp", "3G")
        sr_4g = find_col(df_pdp_sr_vepg.columns, "Bearer", "SR") or \
                find_col(df_pdp_sr_vepg.columns, "Bearer", "activation") or \
                find_col(df_pdp_sr_vepg.columns, "LTE", "Bearer")

        sr_pairs = [(c, l) for c, l in [(sr_2g, "PDP SR 2G"), (sr_3g, "PDP SR 3G"), (sr_4g, "4G Bearer Activation SR")] if c]
        for sr_col, sr_label in sr_pairs:
            df_pdp_sr_vepg[sr_col] = pd.to_numeric(df_pdp_sr_vepg[sr_col], errors="coerce")
            series = {}
            cats = None
            for node in nodes:
                sub = df_pdp_sr_vepg[df_pdp_sr_vepg[name_col] == node].sort_values("datetime")
                if cats is None:
                    cats = [t.strftime("%Y-%m-%d %H:%M") for t in sub["datetime"]]
                series[node] = sub[sr_col].fillna(0).tolist()
            if cats:
                add_chart_slide(prs, f"Ericsson {sr_label} per Node (%)",
                                "Accessibility - Success Rate",
                                cats, series, insert_before_idx=conclusion_idx)
                conclusion_idx += 1
        print(f"  Added {len(sr_pairs)} Ericsson SR slides")

    if df_pdp_sr_vugw is not None:
        print("  Adding Huawei PDP/Bearer SR slides...")
        pdp_sr = find_col(df_pdp_sr_vugw.columns, "PDP", "success", "ratio")
        br_sr = find_col(df_pdp_sr_vugw.columns, "bearer", "success", "ratio")
        hw_sr_nodes = df_pdp_sr_vugw["NE Name"].unique().tolist()

        for sr_col, sr_label in [(pdp_sr, "PDP Context SR (2G/3G)"), (br_sr, "Bearer Context SR (4G)")]:
            if not sr_col:
                continue
            df_pdp_sr_vugw[sr_col] = pd.to_numeric(df_pdp_sr_vugw[sr_col], errors="coerce")
            series = {}
            cats = None
            for node in hw_sr_nodes:
                sub = df_pdp_sr_vugw[df_pdp_sr_vugw["NE Name"] == node].sort_values("Start Time")
                if cats is None:
                    cats = [t.strftime("%Y-%m-%d %H:%M") for t in sub["Start Time"]]
                series[node] = sub[sr_col].fillna(0).tolist()
            if cats:
                add_chart_slide(prs, f"Huawei {sr_label} per Node (%)",
                                "Accessibility - Success Rate",
                                cats, series, insert_before_idx=conclusion_idx)
                conclusion_idx += 1
        print("  Added Huawei SR slides")

    # Conclusion
    slide_conclusion = prs.slides[conclusion_idx]
    if start_date and end_date:
        for shape in slide_conclusion.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        run.text = re.sub(
                            r"from \d{2} \w+\s*\d{0,4}\s*to \d{2} \w+ \d{4}",
                            f"from {format_date_long(start_date)} to {format_date_long(end_date)}",
                            run.text
                        )
    print("  Conclusion slide updated")

    # Save
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
