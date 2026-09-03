#!/usr/bin/env python3
"""rail_invoice_parse - 铁路电子客票发票解析模块"""
import sys
import xml.etree.ElementTree as ET
from pypdf import PdfReader


def extract_embedded_xml(pdf_path):
    reader = PdfReader(pdf_path)
    catalog = reader.trailer["/Root"]
    if "/Names" not in catalog or "/EmbeddedFiles" not in catalog["/Names"]:
        return None
    ef_names = catalog["/Names"]["/EmbeddedFiles"].get_object()["/Names"]
    for i in range(0, len(ef_names), 2):
        filespec = ef_names[i + 1].get_object()
        ef_dict = filespec.get("/EF", {}).get_object()
        for stream_key in ["/F", "/UF"]:
            if stream_key in ef_dict:
                return ef_dict[stream_key].get_object().get_data()
    return None


def local_name(tag):
    return tag.split("}")[-1]


def parse_rail_pdf(pdf_path):
    xml_bytes = extract_embedded_xml(pdf_path)
    if xml_bytes is None:
        raise ValueError("PDF 中没有嵌入的电子客票 XML")
    root = ET.fromstring(xml_bytes)
    data = {}
    for elem in root.iter():
        tag = local_name(elem.tag)
        text = (elem.text or "").strip()
        if text:
            data.setdefault(tag, text)

    def pick(*keys):
        for k in keys:
            if k in data and data[k]:
                return data[k]
        return None

    return {
        "发票类型": pick("TypeOfVoucher"),
        "发票号码": pick("ElectronicInvoiceRailwayETicketNumber", "ETicketNumber"),
        "开票日期": pick("DateOfIssue"),
        "乘车人": pick("Name"),
        "身份证号": pick("IdNumber"),
        "出发站": pick("DepartureStation"),
        "到达站": pick("DestinationStation"),
        "车次": pick("TrainNumber"),
        "乘车日期": pick("TravelDate"),
        "出发时间": pick("DepartureTime"),
        "座位等级": pick("SeatLevel"),
        "车厢座位": pick("Carriage", "Seat"),
        "票价(含税)": pick("Fare"),
        "不含税金额": pick("TotalAmountExcludingTax"),
        "税率": pick("TaxRate"),
        "税额": pick("TaxAmount"),
        "购买方名称": pick("NameOfPurchaser"),
        "购买方信用代码": pick("UnifiedSocialCreditCodeOfPurchaser"),
        "业务类型": pick("TypeOfBusiness"),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python rail_invoice_parse.pyt <pdf>")
        sys.exit(1)
    import json
    info = parse_rail_pdf(sys.argv[1])
    print(json.dumps(info, ensure_ascii=False, indent=2))
