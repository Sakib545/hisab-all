from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

def make_pdf(rows, output_path, title):
    output_path=Path(output_path)
    styles=getSampleStyleSheet()
    doc=SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28)
    story=[Paragraph(title, styles['Title']), Spacer(1,12)]
    total=sum(float(r['amount'] or 0) for r in rows)
    story.append(Paragraph(f"Receipts: {len(rows)} | Total: BDT {total:,.2f}", styles['Heading2']))
    story.append(Spacer(1,10))
    data=[["SL","Date","Time","Payment","Receiver Account","Amount"]]
    for i,r in enumerate(rows,1):
        data.append([i,r['transaction_date'],r['transaction_time'],r['payment_code'] or '',r['account_number'],f"{float(r['amount'] or 0):,.2f}"])
    table=Table(data, repeatRows=1, colWidths=[28,68,55,65,155,75])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),0.5,colors.grey),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(-1,1),(-1,-1),'RIGHT'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.whitesmoke])]))
    story.append(table)
    doc.build(story)
    return output_path
