from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font
from config import EXPORTS_DIR

def make_excel(rows):
    path=EXPORTS_DIR/f"transactions_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    wb=Workbook()
    ws=wb.active
    ws.title="Transactions"
    headers=["ID","Bank/MFS","Receiver","Account","Amount","Date","Time","Reference","Remarks","Created"]
    ws.append(headers)
    for c in ws[1]: c.font=Font(bold=True)
    for r in rows:
        ws.append([r["id"],r["bank_name"],r["receiver_name"],r["account_number"],r["amount"],
                   r["transaction_date"],r["transaction_time"],r["reference_id"],r["remarks"],r["created_at"]])
    ws.freeze_panes="A2"
    ws.auto_filter.ref=ws.dimensions
    wb.save(path)
    return path
