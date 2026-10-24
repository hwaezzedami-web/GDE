#!/bin/bash
echo "============================================"
echo "  PS Core KPI Report Generator"
echo "============================================"
echo

cd "$(dirname "$0")"
pip install openpyxl xlrd pandas -q 2>/dev/null
python3 generate_kpi_report.py

echo
if [ $? -eq 0 ]; then
    echo "Done! Check the output/ folder."
else
    echo "ERROR: Report generation failed!"
fi
