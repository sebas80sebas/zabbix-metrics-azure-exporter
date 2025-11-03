import datetime
import io
import os
import pandas as pd
from azure.storage.blob import BlobServiceClient
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.chart import BarChart, LineChart, Reference

# 🎨 Colors
HEADER_FILL = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
CPU_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
MEM_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")


def generate_excel():
    # 📡 Blob connection
    connect_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connect_str:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is not configured")
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    container_name = "metrics"
    container_client = blob_service_client.get_container_client(container_name)

    try:
        container_client.create_container()
    except:
        pass  # Already exists


    host_count = 0

    # 📥 Download CSVs
    csv_data = {}
    for blob in container_client.list_blobs():
        if blob.name.endswith(".csv"):
            blob_client = container_client.get_blob_client(blob.name)
            stream = io.StringIO(blob_client.download_blob().content_as_text())
            csv_data[blob.name] = pd.read_csv(stream)
            host_count += 1

    # 📊 Create Excel
    wb = Workbook()
    ws_all = wb.active
    ws_all.title = "All Hosts"
    headers = ["Host", "Metric", "Min", "Max", "Avg", "Samples"]
    ws_all.append(headers)

    for col in range(1, len(headers)+1):
        cell = ws_all.cell(1, col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    row_count = 2
    cpu_data = []
    mem_data = []

    # 🔸 Fill main sheet and collect Top 10 metrics
    for csv_name, df in csv_data.items():
        host_name = csv_name.replace(".csv", "")
        for _, row in df.iterrows():
            ws_all.append([
                host_name,
                row['Metric'],
                row['Min'],
                row['Max'],
                row['Avg'],
                row['Samples']
            ])
            metric_cell = ws_all.cell(row_count, 2)
            if 'cpu' in row['Metric'].lower():
                metric_cell.fill = CPU_FILL
                cpu_data.append((host_name, row['Avg']))
            elif 'mem' in row['Metric'].lower():
                metric_cell.fill = MEM_FILL
                mem_data.append((host_name, row['Avg']))
            row_count += 1
            

    # 📊 Main dashboard
    ws_dashboard = wb.create_sheet("Dashboard", 0)
    ws_dashboard['B2'] = "ZABBIX MONITORING REPORT"
    ws_dashboard['B2'].font = Font(size=15, bold=True, color="2E75B6")
    ws_dashboard.merge_cells('B2:F2')
    ws_dashboard['B3'] = f"Generated: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}"

    stats = [
        ["Total Hosts", host_count],
        ["Total Metrics", row_count-2],
        ["Period", "Last 30 days"]
    ]
    for i, row in enumerate(stats, start=5):
        ws_dashboard.cell(i, 2, row[0])
        ws_dashboard.cell(i, 3, row[1])

    # 🧠 Top 10 CPU
    ws_dashboard['B9'] = "Top 10 CPU Avg"
    ws_dashboard['B9'].font = Font(bold=True)
    cpu_data_sorted = sorted(cpu_data, key=lambda x: x[1], reverse=True)[:10]
    for i, (host, avg) in enumerate(cpu_data_sorted, start=10):
        ws_dashboard.cell(i, 2, host)
        cell = ws_dashboard.cell(i, 3, avg)
        cell.number_format = '0.00'
        if avg > 80:
            cell.fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
            cell.font = Font(color="FFFFFF", bold=True)
        elif avg > 60:
            cell.fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")

    # 🧠 Top 10 Memory
    ws_dashboard['E9'] = "Top 10 Memory Avg"
    ws_dashboard['E9'].font = Font(bold=True)
    mem_data_sorted = sorted(mem_data, key=lambda x: x[1], reverse=True)[:10]
    for i, (host, avg) in enumerate(mem_data_sorted, start=10):
        ws_dashboard.cell(i, 5, host)
        cell = ws_dashboard.cell(i, 6, avg)
        cell.number_format = '0.00'
        if avg > 80:
            cell.fill = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")
            cell.font = Font(color="FFFFFF", bold=True)
        elif avg > 60:
            cell.fill = PatternFill(start_color="FFC000", end_color="FFC000", fill_type="solid")

    # 📊 Top 10 CPU Chart
    cpu_chart = BarChart()
    cpu_chart.title = "Top 10 CPU Usage (%)"
    cpu_chart.y_axis.title = "CPU Avg (%)"
    cpu_chart.x_axis.title = "Host"
    cpu_values = Reference(ws_dashboard, min_col=3, min_row=10, max_row=19)
    cpu_categories = Reference(ws_dashboard, min_col=2, min_row=10, max_row=19)
    cpu_chart.add_data(cpu_values, titles_from_data=False)
    cpu_chart.set_categories(cpu_categories)
    cpu_chart.shape = 4
    cpu_chart.legend = None
    ws_dashboard.add_chart(cpu_chart, "H9")
    

    # 📊 Top 10 Memory Chart
    mem_chart = BarChart()
    mem_chart.title = "Top 10 Memory Usage (%)"
    mem_chart.y_axis.title = "Memory Avg (%)"
    mem_chart.x_axis.title = "Host"
    mem_values = Reference(ws_dashboard, min_col=6, min_row=10, max_row=19)
    mem_categories = Reference(ws_dashboard, min_col=5, min_row=10, max_row=19)
    mem_chart.add_data(mem_values, titles_from_data=False)
    mem_chart.set_categories(mem_categories)
    mem_chart.shape = 4
    mem_chart.legend = None
    ws_dashboard.add_chart(mem_chart, "H25")

    # 📈 Create one sheet per host with charts
    for csv_name, df in csv_data.items():
        host_name = csv_name.replace(".csv", "")
        ws_host = wb.create_sheet(title=host_name[:30])  # 31 chars limit
        ws_host.append(df.columns.tolist())
        for _, r in df.iterrows():
            ws_host.append(r.tolist())

        # Apply header styles
        for col in range(1, len(df.columns)+1):
            cell = ws_host.cell(1, col)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center")

        # CPU Chart
        cpu_rows = df[df['Metric'].str.contains('cpu', case=False)]
        if not cpu_rows.empty:
            chart = LineChart()
            chart.title = f"CPU Avg - {host_name}"
            chart.y_axis.title = "CPU Avg (%)"
            chart.x_axis.title = "Metric"
            data_col = df.columns.get_loc('Avg') + 1
            data = Reference(ws_host, min_col=data_col, min_row=2, max_row=ws_host.max_row)
            cats = Reference(ws_host, min_col=1, min_row=2, max_row=ws_host.max_row)
            chart.add_data(data, titles_from_data=False)
            chart.set_categories(cats)
            chart.legend = None
            ws_host.add_chart(chart, "H2")

        # Memory Chart
        mem_rows = df[df['Metric'].str.contains('mem', case=False)]
        if not mem_rows.empty:
            chart = LineChart()
            chart.title = f"Memory Avg - {host_name}"
            chart.y_axis.title = "Memory Avg (%)"
            chart.x_axis.title = "Metric"
            data_col = df.columns.get_loc('Avg') + 1
            data = Reference(ws_host, min_col=data_col, min_row=2, max_row=ws_host.max_row)
            cats = Reference(ws_host, min_col=1, min_row=2, max_row=ws_host.max_row)
            chart.add_data(data, titles_from_data=False)
            chart.set_categories(cats)
            chart.legend = None
            ws_host.add_chart(chart, "H20")

    # 📤 Save and upload
    excel_output = io.BytesIO()
    wb.save(excel_output)
    filename = f"Zabbix_Report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    excel_blob_client = container_client.get_blob_client(filename)
    excel_blob_client.upload_blob(excel_output.getvalue(), overwrite=True)

    print(f"✅ Excel '{filename}' uploaded with Dashboard and individual sheets per host")


if __name__ == "__main__":
    generate_excel()